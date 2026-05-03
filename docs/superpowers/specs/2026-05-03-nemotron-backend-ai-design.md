# Nemotron Backend AI Design

WholeYou will replace browser-local generation with backend AI orchestration. The frontend will keep the existing data attachment workflow, add image upload, and submit prompts to a backend endpoint instead of downloading a Transformers.js model.

The backend will call OpenRouter with the OpenAI SDK, `base_url="https://openrouter.ai/api/v1"`, model `nvidia/nemotron-3-super-120b-a12b:free`, and `extra_body={"reasoning": {"enabled": True}}`. If prior assistant messages with `reasoning_details` are later sent back by the frontend, the backend preserves them unmodified in the OpenRouter message list.

The backend exposes four OpenAI-style tools to Nemotron 3 Super:

- `data_with_rerank`: gather MyChart and wearable candidate chunks, rerank with NVIDIA `llama-nemotron-rerank-1b-v2`, and return the most relevant snippets.
- `rag_with_rerank`: retrieve candidates from `Sagarika-Singh-99/medical-rag-corpus`, rerank with NVIDIA, and return evidence snippets.
- `mychart_data`: list top-level MyChart categories or fetch requested categories/documents.
- `wearables_data`: list top-level wearable categories or fetch requested categories.

Secrets stay server-side only: `OPENROUTER_API_KEY`, `NVIDIA_API_KEY`, optional `OPENROUTER_MODEL`, and optional endpoint overrides. User-attached health data and images are sent from frontend to backend; selected tool results may then be sent to OpenRouter/NVIDIA hosted services.

Initial RAG implementation will avoid a vector database. It will lazily fetch/cache the Hugging Face dataset metadata or rows, use simple lexical candidate retrieval, and rely on NVIDIA rerank for final ordering. This keeps the first version testable and replaceable.
