import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import torch

from scripts.prepare_medical_rag_corpus import prepare_local_dense_corpus


class PrepareMedicalRagCorpusTests(unittest.TestCase):
    def test_prepare_local_dense_corpus_shards_embeddings_and_writes_lookup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "source"
            output_dir = root / "prepared"
            source_dir.mkdir()
            df = pd.DataFrame(
                [
                    {
                        "doc_id": "a",
                        "title": "Alpha",
                        "text": "Alpha text",
                        "source": "medquad",
                        "category": "faq",
                    },
                    {
                        "doc_id": "b",
                        "title": "Beta",
                        "text": "Beta text",
                        "source": "pubmed",
                        "category": "abstract",
                    },
                ]
            )
            df.to_pickle(source_dir / "final_corpus.pkl")
            torch.save(
                torch.tensor([[1.0, 0.0], [0.0, 1.0]], dtype=torch.float32),
                source_dir / "dense_embeddings.pt",
            )

            prepare_local_dense_corpus(source_dir, output_dir, shard_size=1)

            self.assertTrue((output_dir / "embedding_shards" / "embeddings_000000_000001.pt").exists())
            self.assertTrue((output_dir / "embedding_shards" / "embeddings_000001_000002.pt").exists())
            with sqlite3.connect(output_dir / "medical_rag.sqlite") as connection:
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
                rows = connection.execute(
                    """
                    SELECT embedding_index, id, title, text, source, category, dataset_id
                    FROM documents
                    ORDER BY embedding_index
                    """
                ).fetchall()
            self.assertEqual(
                rows,
                [
                    (
                        0,
                        "a",
                        "Alpha",
                        "Alpha text",
                        "medical-rag-corpus",
                        "faq",
                        "Sagarika-Singh-99/medical-rag-corpus",
                    ),
                    (
                        1,
                        "b",
                        "Beta",
                        "Beta text",
                        "medical-rag-corpus",
                        "abstract",
                        "Sagarika-Singh-99/medical-rag-corpus",
                    ),
                ],
            )


if __name__ == "__main__":
    unittest.main()
