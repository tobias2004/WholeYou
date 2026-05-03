import json
import pickle
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.embed_medrag_textbooks import (
    build_corpus_row,
    next_embedding_start,
    write_corpus,
    write_sqlite_index,
)


class MedragTextbooksEmbeddingTests(unittest.TestCase):
    def test_build_corpus_row_preserves_medical_rag_corpus_style_fields(self):
        row = build_corpus_row(
            {
                "id": "Anatomy_Gray_0",
                "title": "Anatomy_Gray",
                "content": "What is anatomy?",
                "contents": "Anatomy_Gray. What is anatomy?",
            },
            index=0,
        )

        self.assertEqual(row["id"], "Anatomy_Gray_0")
        self.assertEqual(row["title"], "Anatomy_Gray")
        self.assertEqual(row["text"], "Anatomy_Gray. What is anatomy?")
        self.assertEqual(row["source"], "MedRAG/textbooks")
        self.assertEqual(row["category"], "textbook")

    def test_write_corpus_creates_pickle_and_jsonl_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            rows = [
                build_corpus_row(
                    {
                        "id": "doc-1",
                        "title": "Title",
                        "content": "Content",
                        "contents": "Title. Content",
                    },
                    index=0,
                )
            ]

            write_corpus(rows, output_dir)

            with (output_dir / "final_corpus.pkl").open("rb") as handle:
                self.assertEqual(pickle.load(handle), rows)
            metadata = json.loads((output_dir / "metadata.json").read_text())
            self.assertEqual(metadata["dataset_id"], "MedRAG/textbooks")
            self.assertEqual(metadata["document_count"], 1)

    def test_next_embedding_start_resumes_after_last_complete_shard(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            shard_dir = Path(tmpdir)
            (shard_dir / "embeddings_000000_000128.pt").touch()
            (shard_dir / "embeddings_000128_000256.pt").touch()
            (shard_dir / "unrelated.pt").touch()

            self.assertEqual(next_embedding_start(shard_dir), 256)

    def test_write_sqlite_index_creates_searchable_textbooks_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            rows = [
                {
                    "id": "doc-1",
                    "title": "Harrison",
                    "text": "Hypertension evaluation uses repeated blood pressure readings.",
                    "source": "MedRAG/textbooks",
                }
            ]

            write_sqlite_index(rows, output_dir)

            with sqlite3.connect(output_dir / "textbooks.sqlite") as connection:
                columns = [
                    (row[1], row[2], row[5])
                    for row in connection.execute("PRAGMA table_info(documents)")
                ]
                self.assertEqual(
                    columns,
                    [
                        ("embedding_index", "INTEGER", 1),
                        ("id", "TEXT", 0),
                        ("text", "TEXT", 0),
                        ("title", "TEXT", 0),
                        ("source", "TEXT", 0),
                        ("category", "TEXT", 0),
                        ("dataset_id", "TEXT", 0),
                    ],
                )
                matches = connection.execute(
                    """
                    SELECT documents.id
                    FROM documents_fts
                    JOIN documents ON documents_fts.rowid = documents.embedding_index
                    WHERE documents_fts MATCH ?
                    """,
                    ("hypertension",),
                ).fetchall()
            self.assertEqual(matches, [("doc-1",)])


if __name__ == "__main__":
    unittest.main()
