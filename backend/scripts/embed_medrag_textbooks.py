from __future__ import annotations

import argparse
import json
import pickle
import re
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATASET_ID = "MedRAG/textbooks"
ARTICLE_ENCODER_ID = "ncbi/MedCPT-Article-Encoder"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data" / "medrag-textbooks"


def build_corpus_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    title = str(row.get("title") or "").strip()
    content = str(row.get("content") or "").strip()
    text = str(row.get("contents") or "").strip()
    if not text:
        text = f"{title}. {content}".strip(". ")
    return {
        "id": str(row.get("id") or f"medrag-textbooks-{index}"),
        "text": text,
        "title": title,
        "source": DATASET_ID,
        "category": "textbook",
    }


def write_corpus(rows: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "final_corpus.pkl").open("wb") as handle:
        pickle.dump(rows, handle, protocol=pickle.HIGHEST_PROTOCOL)
    metadata = {
        "dataset_id": DATASET_ID,
        "document_count": len(rows),
        "embedding_model": ARTICLE_ENCODER_ID,
        "embedding_file": "dense_embeddings.pt",
        "corpus_file": "final_corpus.pkl",
        "bm25_file": "bm25_tokenized.pkl",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")


def write_bm25_tokens(rows: list[dict[str, Any]], output_dir: Path) -> None:
    tokenized = [
        re.findall(r"[a-z0-9]+", row["text"].lower())
        for row in rows
    ]
    with (output_dir / "bm25_tokenized.pkl").open("wb") as handle:
        pickle.dump(tokenized, handle, protocol=pickle.HIGHEST_PROTOCOL)


def write_sqlite_index(rows: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    sqlite_path = output_dir / "textbooks.sqlite"
    with sqlite3.connect(sqlite_path) as connection:
        connection.execute("DROP TABLE IF EXISTS textbooks")
        connection.execute("DROP TABLE IF EXISTS documents_fts")
        connection.execute("DROP TABLE IF EXISTS documents")
        connection.execute(
            """
            CREATE TABLE documents (
                embedding_index INTEGER PRIMARY KEY,
                id TEXT NOT NULL,
                text TEXT NOT NULL,
                title TEXT,
                source TEXT NOT NULL,
                category TEXT,
                dataset_id TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE VIRTUAL TABLE documents_fts USING fts5(
                id,
                text,
                title,
                source,
                category,
                dataset_id,
                content='documents',
                content_rowid='embedding_index'
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO documents
            (embedding_index, id, text, title, source, category, dataset_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    index,
                    row.get("id", ""),
                    row.get("text", ""),
                    row.get("title", ""),
                    row.get("source", DATASET_ID),
                    row.get("category", "textbook"),
                    DATASET_ID,
                )
                for index, row in enumerate(rows)
            ),
        )
        connection.execute(
            """
            INSERT INTO documents_fts(rowid, id, text, title, source, category, dataset_id)
            SELECT embedding_index, id, text, title, source, category, dataset_id
            FROM documents
            """
        )
        connection.commit()


def load_corpus_pickle(output_dir: Path) -> list[dict[str, Any]]:
    with (output_dir / "final_corpus.pkl").open("rb") as handle:
        return pickle.load(handle)


def batched(items: list[Any], batch_size: int) -> Iterable[list[Any]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def load_medrag_rows(limit: int | None = None) -> list[dict[str, Any]]:
    from datasets import load_dataset

    dataset = load_dataset(DATASET_ID, split="train")
    if limit is not None:
        dataset = dataset.select(range(min(limit, len(dataset))))
    return [build_corpus_row(row, index) for index, row in enumerate(dataset)]


def next_embedding_start(shard_dir: Path) -> int:
    starts_at = 0
    for path in shard_dir.glob("embeddings_*.pt"):
        match = re.fullmatch(r"embeddings_(\d{6})_(\d{6})\.pt", path.name)
        if match:
            starts_at = max(starts_at, int(match.group(2)))
    return starts_at


def embed_rows(
    rows: list[dict[str, Any]],
    output_dir: Path,
    batch_size: int,
    save_every: int,
    combine_shards: bool,
) -> None:
    import torch
    from transformers import AutoModel, AutoTokenizer

    device = _best_device(torch)
    tokenizer = AutoTokenizer.from_pretrained(ARTICLE_ENCODER_ID)
    model = AutoModel.from_pretrained(ARTICLE_ENCODER_ID).to(device)
    model.eval()

    shard_dir = output_dir / "embedding_shards"
    shard_dir.mkdir(parents=True, exist_ok=True)
    pending_embeddings = []
    pending_start = 0

    with torch.no_grad():
        for batch_index, batch in enumerate(batched(rows, batch_size)):
            texts = [[row["title"], row["text"]] for row in batch]
            encoded = tokenizer(
                texts,
                truncation=True,
                padding=True,
                return_tensors="pt",
                max_length=512,
            )
            encoded = {key: value.to(device) for key, value in encoded.items()}
            embeddings = model(**encoded).last_hidden_state[:, 0, :].detach().cpu()
            if not pending_embeddings:
                pending_start = batch_index * batch_size
            pending_embeddings.append(embeddings)
            processed = min((batch_index + 1) * batch_size, len(rows))
            if processed % save_every == 0 or processed == len(rows):
                shard_path = shard_dir / f"embeddings_{pending_start:06d}_{processed:06d}.pt"
                torch.save(torch.cat(pending_embeddings, dim=0), shard_path)
                pending_embeddings = []
                print(f"saved {shard_path.name} ({processed}/{len(rows)})", flush=True)

    shards = sorted(shard_dir.glob("embeddings_*.pt"))
    if combine_shards:
        embeddings = torch.cat([torch.load(path, map_location="cpu") for path in shards], dim=0)
        torch.save(embeddings, output_dir / "dense_embeddings.pt")


def embed_rows_low_memory(
    output_dir: Path,
    batch_size: int,
    save_every: int,
    limit: int | None,
    combine_shards: bool,
) -> None:
    import torch
    from datasets import load_dataset
    from transformers import AutoModel, AutoTokenizer

    device = _best_device(torch)
    tokenizer = AutoTokenizer.from_pretrained(ARTICLE_ENCODER_ID)
    model = AutoModel.from_pretrained(ARTICLE_ENCODER_ID).to(device)
    model.eval()

    shard_dir = output_dir / "embedding_shards"
    shard_dir.mkdir(parents=True, exist_ok=True)
    start_at = next_embedding_start(shard_dir)
    if start_at:
        print(f"resuming after {start_at} existing embeddings", flush=True)

    dataset = load_dataset(DATASET_ID, split="train", streaming=True)
    pending_embeddings = []
    pending_start = start_at
    processed = start_at
    batch_rows: list[dict[str, Any]] = []

    with torch.no_grad():
        for index, raw_row in enumerate(dataset):
            if index < start_at:
                continue
            if limit is not None and index >= limit:
                break
            batch_rows.append(build_corpus_row(raw_row, index))
            if len(batch_rows) < batch_size:
                continue

            pending_embeddings.append(_embed_batch(batch_rows, tokenizer, model, device))
            processed += len(batch_rows)
            batch_rows = []
            if processed - pending_start >= save_every:
                _write_pending_shard(shard_dir, pending_start, processed, pending_embeddings, torch)
                pending_embeddings = []
                pending_start = processed

        if batch_rows:
            pending_embeddings.append(_embed_batch(batch_rows, tokenizer, model, device))
            processed += len(batch_rows)
        if pending_embeddings:
            _write_pending_shard(shard_dir, pending_start, processed, pending_embeddings, torch)

    if combine_shards:
        shards = sorted(shard_dir.glob("embeddings_*.pt"))
        embeddings = torch.cat([torch.load(path, map_location="cpu") for path in shards], dim=0)
        torch.save(embeddings, output_dir / "dense_embeddings.pt")


def _embed_batch(
    rows: list[dict[str, Any]],
    tokenizer: Any,
    model: Any,
    device: str,
) -> Any:
    texts = [[row["title"], row["text"]] for row in rows]
    encoded = tokenizer(
        texts,
        truncation=True,
        padding=True,
        return_tensors="pt",
        max_length=512,
    )
    encoded = {key: value.to(device) for key, value in encoded.items()}
    return model(**encoded).last_hidden_state[:, 0, :].detach().cpu()


def _write_pending_shard(
    shard_dir: Path,
    start: int,
    end: int,
    pending_embeddings: list[Any],
    torch_module: Any,
) -> None:
    shard_path = shard_dir / f"embeddings_{start:06d}_{end:06d}.pt"
    torch_module.save(torch_module.cat(pending_embeddings, dim=0), shard_path)
    print(f"saved {shard_path.name} ({end})", flush=True)


def _best_device(torch_module: Any) -> str:
    if torch_module.cuda.is_available():
        return "cuda"
    if getattr(torch_module.backends, "mps", None) and torch_module.backends.mps.is_available():
        return "mps"
    return "cpu"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Embed MedRAG/textbooks with ncbi/MedCPT-Article-Encoder."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--save-every", type=int, default=512)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--combine-shards",
        action="store_true",
        help="Also write dense_embeddings.pt by loading and concatenating every shard.",
    )
    parser.add_argument(
        "--low-memory",
        action="store_true",
        help="Stream dataset rows, resume from existing shards, and avoid corpus list allocation.",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Only write corpus and BM25 artifacts.",
    )
    parser.add_argument(
        "--build-sqlite-index",
        action="store_true",
        help="Build textbooks.sqlite from final_corpus.pkl and exit.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.build_sqlite_index:
        write_sqlite_index(load_corpus_pickle(args.output_dir), args.output_dir)
        return

    if args.low_memory:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        if not args.skip_embeddings:
            embed_rows_low_memory(
                output_dir=args.output_dir,
                batch_size=args.batch_size,
                save_every=args.save_every,
                limit=args.limit,
                combine_shards=args.combine_shards,
            )
        return

    rows = load_medrag_rows(limit=args.limit)
    write_corpus(rows, args.output_dir)
    write_bm25_tokens(rows, args.output_dir)
    write_sqlite_index(rows, args.output_dir)
    if not args.skip_embeddings:
        embed_rows(
            rows=rows,
            output_dir=args.output_dir,
            batch_size=args.batch_size,
            save_every=args.save_every,
            combine_shards=args.combine_shards,
        )


if __name__ == "__main__":
    main()
