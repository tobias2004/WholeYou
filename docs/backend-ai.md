# Backend AI

WholeYou now runs AI generation through backend orchestration instead of a browser-local Transformers.js model. The frontend requests lightweight data availability metadata, lets the user select categories or documents, and sends only selected IDs plus the prompt and optional image attachment to the backend.

## Runtime

- LLM provider: OpenRouter via the OpenAI Python SDK.
- LLM model: `nvidia/nemotron-3-super-120b-a12b:free` by default.
- Reasoning: enabled with `extra_body={"reasoning": {"enabled": True}}`.
- Rerank provider: NVIDIA hosted rerank endpoint.
- Rerank model: `nvidia/llama-nemotron-rerank-1b-v2`.
- Medical RAG corpora: `Sagarika-Singh-99/medical-rag-corpus` and local `MedRAG/textbooks`.
- Dense retrieval: MedCPT Query Encoder over MedCPT Article Encoder embedding shards.

Configure these backend environment variables:

```bash
OPENROUTER_API_KEY=
NVIDIA_API_KEY=
OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b:free
```

## Tool Boundary

The backend exposes these tools to Nemotron 3 Super:

- `data_with_rerank`: fetches MyChart and wearable candidate snippets, then reranks them with NVIDIA.
- `rag_with_rerank`: searches both medical RAG corpora with MedCPT dense retrieval, pools candidates, then reranks the combined set with NVIDIA. Local retrieval uses the MedCPT Query Encoder against stored MedCPT Article Encoder embedding shards, with SQLite used for text lookup.
- `mychart_data`: lists or fetches MyChart top-level categories and selected raw data.
- `wearables_data`: lists or fetches wearable top-level categories and selected raw data.
- `translate_text`: translates selected-language prompts, final answers, or short excerpts through the configured NVIDIA-compatible translation endpoint.

The browser no longer downloads model weights or owns WebGPU memory. Raw health data remains backend-owned until a backend tool fetches it for a specific answer.

## RAG Artifact Layout

RAG artifacts live under `data/`, which is ignored by git:

```text
data/
  medical-rag-corpus/
    medical_rag.sqlite
    embedding_shards/*.pt
    source/final_corpus.pkl
    source/dense_embeddings.pt
  medrag-textbooks/
    textbooks.sqlite
    embedding_shards/*.pt
```

Both corpora use the same canonical SQLite table:

```text
documents(
  embedding_index INTEGER PRIMARY KEY,
  id TEXT NOT NULL,
  text TEXT NOT NULL,
  title TEXT,
  source TEXT NOT NULL,
  category TEXT,
  dataset_id TEXT NOT NULL
)
```

Each database also has a `documents_fts` external-content FTS table for fallback
text search. Runtime dense retrieval is the primary path when local embedding
shards are present. The backend embeds the user query with the MedCPT Query
Encoder, scans MedCPT Article Encoder embedding shards for each corpus, fetches
matched rows from SQLite, pools candidates from both datasets, then sends the
pooled candidates to NVIDIA rerank.

## Skill Runtime

`SKILLS.md` is runtime guidance, not static copy. When the user selects a skill,
the backend injects the matching workflow into the model system prompt. Skills
tell the model which tools to call, which order to prefer, and when to branch to
RAG, personal-data rerank, MyChart data, wearable data, translation, or the Open
Wearables Health AI Engine behavior.

## Privacy Boundary

Selected prompt, health snippets, RAG snippets, and image attachments may be sent by the backend to OpenRouter and NVIDIA hosted APIs during generation. This is a cloud AI privacy boundary, not a browser-local AI boundary.

Production should add per-user auth, durable encrypted storage, explicit consent copy, audit logging, request retention controls, and provider-specific data handling review before handling real patient data.
