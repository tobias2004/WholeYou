from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATASET_ID = "Sagarika-Singh-99/medical-rag-corpus"
ARTICLE_ENCODER_ID = "ncbi/MedCPT-Article-Encoder"
DEFAULT_SOURCE_DIR = Path(__file__).resolve().parents[2] / "data" / "medical-rag-corpus" / "source"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data" / "medical-rag-corpus"


def prepare_local_dense_corpus(
    source_dir: Path,
    output_dir: Path,
    shard_size: int = 2048,
) -> None:
    import pandas as pd
    import torch

    corpus = pd.read_pickle(source_dir / "final_corpus.pkl")
    embeddings = torch.load(source_dir / "dense_embeddings.pt", map_location="cpu").float()
    if len(corpus) != embeddings.shape[0]:
        raise ValueError(
            f"Corpus row count ({len(corpus)}) does not match embeddings ({embeddings.shape[0]})."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    write_sqlite_lookup(corpus, output_dir)
    write_embedding_shards(embeddings, output_dir / "embedding_shards", shard_size)
    write_metadata(corpus, embeddings, output_dir, shard_size)


def write_sqlite_lookup(corpus: Any, output_dir: Path) -> None:
    sqlite_path = output_dir / "medical_rag.sqlite"
    with sqlite3.connect(sqlite_path) as connection:
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
            (_sqlite_row(index, row) for index, row in corpus.iterrows()),
        )
        connection.execute(
            """
            INSERT INTO documents_fts(rowid, id, text, title, source, category, dataset_id)
            SELECT embedding_index, id, text, title, source, category, dataset_id
            FROM documents
            """
        )
        connection.commit()


def write_embedding_shards(embeddings: Any, shard_dir: Path, shard_size: int) -> None:
    import torch

    shard_dir.mkdir(parents=True, exist_ok=True)
    for old_shard in shard_dir.glob("embeddings_*.pt"):
        old_shard.unlink()
    total = embeddings.shape[0]
    for start in range(0, total, shard_size):
        end = min(start + shard_size, total)
        shard_path = shard_dir / f"embeddings_{start:06d}_{end:06d}.pt"
        torch.save(embeddings[start:end].clone().contiguous(), shard_path)
        print(f"saved {shard_path.name} ({end}/{total})", flush=True)


def write_metadata(corpus: Any, embeddings: Any, output_dir: Path, shard_size: int) -> None:
    metadata = {
        "dataset_id": DATASET_ID,
        "document_count": int(len(corpus)),
        "embedding_model": ARTICLE_ENCODER_ID,
        "embedding_shape": list(embeddings.shape),
        "embedding_dtype": str(embeddings.dtype),
        "source_embedding_file": "source/dense_embeddings.pt",
        "source_corpus_file": "source/final_corpus.pkl",
        "sqlite_file": "medical_rag.sqlite",
        "embedding_shards_dir": "embedding_shards",
        "shard_size": shard_size,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")


def _sqlite_row(index: int, row: Any) -> tuple[int, str, str, str, str, str, str]:
    doc_id = str(row.get("doc_id", ""))
    title = str(row.get("title", ""))
    text = str(row.get("text", ""))
    category = str(row.get("category", ""))
    return index, doc_id, text, title, "medical-rag-corpus", category, DATASET_ID


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize medical-rag-corpus into local dense shard + SQLite lookup format."
    )
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--shard-size", type=int, default=2048)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    prepare_local_dense_corpus(args.source_dir, args.output_dir, args.shard_size)


if __name__ == "__main__":
    main()
