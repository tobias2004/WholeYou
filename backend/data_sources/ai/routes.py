from __future__ import annotations

import asyncio
import json
import pickle
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from audit_logs import append_log, data_access_entry
from config import (
    MEDICAL_RAG_DATA_DIR,
    MEDICAL_RAG_DATASET_ID,
    MEDRAG_TEXTBOOKS_DATA_DIR,
    NVIDIA_RERANKER_API_KEY,
    NVIDIA_RERANK_MODEL,
    NVIDIA_RERANK_URL,
    NVIDIA_TRANSLATION_API_KEY,
    NVIDIA_TRANSLATION_BASE_URL,
    NVIDIA_TRANSLATION_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
)
from data_sources.local_ai.routes import (
    WEARABLE_CATEGORY_BY_ID,
    _compact_epic_raw,
    _fetch_wearable_category,
    _label_from_key,
    _record_count,
    _service,
)
from data_sources.wearables.service import DEMO_USER_ID, WearableDataService

router = APIRouter(prefix="/api/ai", tags=["ai"])


class AiAttachment(BaseModel):
    categoryId: str
    documentId: str | None = None


class AiPriorMessage(BaseModel):
    role: str
    content: Any = None
    reasoning_details: Any = None


class AiChatRequest(BaseModel):
    prompt: str = Field(min_length=1)
    selectedCategoryIds: list[str] = Field(default_factory=list)
    selectedDocuments: list[AiAttachment] = Field(default_factory=list)
    selectedSkillIds: list[str] = Field(default_factory=list)
    translationLanguage: str | None = None
    imageDataUrl: str | None = None
    messages: list[AiPriorMessage] = Field(default_factory=list)


class AiChatResponse(BaseModel):
    answer: str
    model: str
    generatedAt: str
    reasoningDetails: Any = None


@dataclass
class RerankedPassage:
    index: int
    relevance_score: float | None
    text: str
    source: str | None = None


ProgressEmitter = Callable[[str, dict[str, Any]], Awaitable[None]]


class OpenRouterNemotronClient:
    def __init__(
        self,
        api_key: str = OPENROUTER_API_KEY,
        base_url: str = OPENROUTER_BASE_URL,
        model: str = OPENROUTER_MODEL,
    ):
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="OPENROUTER_API_KEY is not configured.",
            )
        from openai import OpenAI

        self.model = model
        self._client = OpenAI(base_url=base_url, api_key=api_key)

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                extra_body={"reasoning": {"enabled": True}},
            )
        except Exception as exc:
            raise _openrouter_http_exception(exc) from exc
        return _message_to_dict(response.choices[0].message)


class NvidiaRerankClient:
    def __init__(
        self,
        api_key: str = NVIDIA_RERANKER_API_KEY,
        url: str = NVIDIA_RERANK_URL,
        model: str = NVIDIA_RERANK_MODEL,
    ):
        if not api_key:
            raise HTTPException(status_code=500, detail="NVIDIA_RERANKER_API_KEY is not configured.")
        self._api_key = api_key
        self._url = url
        self._model = model

    def rerank(
        self,
        query: str,
        passages: list[dict[str, Any]],
        top_n: int = 5,
    ) -> list[dict[str, Any]]:
        if not passages:
            return []
        response = httpx.post(
            self._url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "model": self._model,
                "query": {"text": query},
                "passages": [{"text": passage["text"]} for passage in passages],
                "truncate": "END",
            },
            timeout=60,
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"NVIDIA rerank failed: {response.text}")
        payload = response.json()
        results = payload.get("rankings") or payload.get("results") or payload.get("data") or []
        normalized: list[dict[str, Any]] = []
        for item in results[:top_n]:
            index = int(item.get("index", item.get("document_index", 0)))
            passage = passages[index] if 0 <= index < len(passages) else {}
            normalized.append(
                {
                    "index": index,
                    "relevance_score": item.get("relevance_score", item.get("score")),
                    "text": passage.get("text", ""),
                    "source": passage.get("source"),
                }
            )
        return normalized


class NvidiaTranslationClient:
    def __init__(
        self,
        api_key: str = NVIDIA_TRANSLATION_API_KEY,
        base_url: str = NVIDIA_TRANSLATION_BASE_URL,
        model: str = NVIDIA_TRANSLATION_MODEL,
    ):
        if not api_key:
            raise HTTPException(status_code=500, detail="NVIDIA_TRANSLATION_API_KEY is not configured.")
        from openai import OpenAI

        self.model = model
        self._client = OpenAI(base_url=base_url, api_key=api_key)

    def translate(self, text: str, source_language: str, target_language: str) -> str:
        if not text.strip():
            return ""
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert at translating text from "
                            f"{source_language} to {target_language}."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"What is the {target_language} translation of the sentence: "
                            f"{text}?"
                        ),
                    },
                ],
                temperature=0,
                stream=False,
            )
        except Exception as exc:
            raise _nvidia_translation_http_exception(exc) from exc
        return response.choices[0].message.content or ""


class MedicalRagCorpus:
    def __init__(self, dataset_id: str = MEDICAL_RAG_DATASET_ID):
        self.dataset_id = dataset_id
        self._dense_corpus = LocalDenseMedicalCorpus(
            data_dir=MEDICAL_RAG_DATA_DIR,
            dataset_id=dataset_id,
            sqlite_name="medical_rag.sqlite",
        )
        self._cache: list[dict[str, Any]] | None = None

    def candidates(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        dense_rows = self._dense_corpus.candidates(query, limit)
        if dense_rows:
            return dense_rows
        rows = self._load_rows()
        terms = _query_terms(query)
        scored: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            text = row.get("text", "")
            haystack = text.lower()
            score = sum(1 for term in terms if term in haystack)
            if score > 0:
                scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [row for _, row in scored[:limit]]

    def _load_rows(self) -> list[dict[str, Any]]:
        if self._cache is not None:
            return self._cache
        self._cache = []
        try:
            tree_url = f"https://huggingface.co/api/datasets/{self.dataset_id}/tree/main"
            tree = httpx.get(tree_url, timeout=20).json()
            candidates = [
                item["path"]
                for item in tree
                if isinstance(item, dict)
                and isinstance(item.get("path"), str)
                and item["path"].lower().endswith((".jsonl", ".json", ".csv", ".txt"))
            ]
            for path in candidates[:2]:
                self._cache.extend(self._read_dataset_file(path))
                if len(self._cache) >= 2000:
                    break
        except Exception:
            self._cache = []
        return self._cache

    def _read_dataset_file(self, path: str) -> list[dict[str, Any]]:
        url = f"https://huggingface.co/datasets/{self.dataset_id}/resolve/main/{path}"
        response = httpx.get(url, timeout=30)
        response.raise_for_status()
        rows: list[dict[str, Any]] = []
        for index, line in enumerate(response.text.splitlines()):
            text = _line_to_text(line)
            if text:
                rows.append({"id": f"{path}:{index}", "text": text, "source": self.dataset_id})
            if len(rows) >= 2000:
                break
        return rows


class LocalDenseMedicalCorpus:
    def __init__(
        self,
        data_dir: str,
        dataset_id: str,
        sqlite_name: str,
        query_encoder: Any | None = None,
    ):
        self.data_dir = _repo_relative_path(data_dir)
        self.dataset_id = dataset_id
        self.sqlite_path = self.data_dir / sqlite_name
        self.corpus_path = self.data_dir / "final_corpus.pkl"
        self.embedding_dir = self.data_dir / "embedding_shards"
        self._query_encoder = query_encoder
        self._cache: list[dict[str, Any]] | None = None

    def candidates(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        if self.sqlite_path.exists() and self.embedding_dir.exists():
            dense_rows = self._dense_candidates(query, limit)
            if dense_rows:
                return dense_rows
        if self.sqlite_path.exists():
            return self._sqlite_candidates(query, limit)
        return self._pickle_candidates(query, limit)

    def _dense_candidates(self, query: str, limit: int) -> list[dict[str, Any]]:
        try:
            import torch

            query_embedding = self._encoder().embed(query).detach().cpu().float()
            scored: list[tuple[float, int]] = []
            for shard_path in sorted(self.embedding_dir.glob("embeddings_*.pt")):
                shard_range = _embedding_shard_range(shard_path)
                if shard_range is None:
                    continue
                start, _ = shard_range
                embeddings = torch.load(shard_path, map_location="cpu").float()
                scores = embeddings @ query_embedding
                top_count = min(limit, scores.numel())
                if top_count == 0:
                    continue
                values, indices = torch.topk(scores, k=top_count)
                scored.extend(
                    (float(value), start + int(index))
                    for value, index in zip(values.tolist(), indices.tolist(), strict=True)
                )
            scored.sort(key=lambda item: item[0], reverse=True)
            return self._rows_by_embedding_indices(scored[:limit])
        except Exception:
            return []

    def _encoder(self) -> Any:
        if self._query_encoder is None:
            self._query_encoder = _medcpt_query_encoder()
        return self._query_encoder

    def _rows_by_embedding_indices(self, scored_indices: list[tuple[float, int]]) -> list[dict[str, Any]]:
        if not scored_indices:
            return []
        rows: list[dict[str, Any]] = []
        with sqlite3.connect(self.sqlite_path) as connection:
            connection.row_factory = sqlite3.Row
            for score, embedding_index in scored_indices:
                row = connection.execute(
                    """
                    SELECT id, text, title, source, category, dataset_id
                    FROM documents
                    WHERE embedding_index = ?
                    """,
                    (embedding_index,),
                ).fetchone()
                if row is None:
                    continue
                rows.append(
                    {
                        "id": row["id"],
                        "title": row["title"],
                        "text": row["text"],
                        "source": row["source"],
                        "category": row["category"],
                        "dataset_id": row["dataset_id"],
                        "dense_score": score,
                    }
                )
        return rows

    def _sqlite_candidates(self, query: str, limit: int) -> list[dict[str, Any]]:
        terms = _query_terms(query)
        if not terms:
            return []
        match_query = " OR ".join(_fts5_token(term) for term in sorted(terms))
        try:
            with sqlite3.connect(self.sqlite_path) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    """
                    SELECT documents.id, documents.text, documents.title, documents.source,
                        documents.category, documents.dataset_id
                    FROM documents_fts
                    JOIN documents ON documents_fts.rowid = documents.embedding_index
                    WHERE documents_fts MATCH ?
                    ORDER BY bm25(documents_fts)
                    LIMIT ?
                    """,
                    (match_query, limit),
                ).fetchall()
        except sqlite3.Error:
            return []
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "text": row["text"],
                "source": row["source"],
                "category": row["category"],
                "dataset_id": row["dataset_id"],
            }
            for row in rows
        ]

    def _pickle_candidates(self, query: str, limit: int) -> list[dict[str, Any]]:
        rows = self._load_pickle_rows()
        terms = _query_terms(query)
        scored: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            text = row.get("text", "")
            haystack = text.lower()
            score = sum(1 for term in terms if term in haystack)
            if score > 0:
                scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [row for _, row in scored[:limit]]

    def _load_pickle_rows(self) -> list[dict[str, Any]]:
        if self._cache is not None:
            return self._cache
        if not self.corpus_path.exists():
            self._cache = []
            return self._cache
        with self.corpus_path.open("rb") as handle:
            self._cache = pickle.load(handle)
        return self._cache


class MedragTextbooksCorpus(LocalDenseMedicalCorpus):
    def __init__(
        self,
        data_dir: str = MEDRAG_TEXTBOOKS_DATA_DIR,
        query_encoder: Any | None = None,
    ):
        super().__init__(
            data_dir=data_dir,
            dataset_id="MedRAG/textbooks",
            sqlite_name="textbooks.sqlite",
            query_encoder=query_encoder,
        )


class MedcptQueryEncoder:
    model_id = "ncbi/MedCPT-Query-Encoder"

    def __init__(self) -> None:
        import torch
        from transformers import AutoModel, AutoTokenizer

        self._torch = torch
        self._device = _best_torch_device(torch)
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        self._model = AutoModel.from_pretrained(self.model_id).to(self._device)
        self._model.eval()

    def embed(self, query: str) -> Any:
        with self._torch.no_grad():
            encoded = self._tokenizer(
                [query],
                truncation=True,
                padding=True,
                return_tensors="pt",
                max_length=64,
            )
            encoded = {key: value.to(self._device) for key, value in encoded.items()}
            return self._model(**encoded).last_hidden_state[:, 0, :][0]


_medical_rag_corpus: MedicalRagCorpus | None = None
_medrag_textbooks_corpus: MedragTextbooksCorpus | None = None
_medcpt_query_encoder_instance: MedcptQueryEncoder | None = None


def _openrouter_client() -> OpenRouterNemotronClient:
    return OpenRouterNemotronClient()


def _rerank_client() -> NvidiaRerankClient:
    return NvidiaRerankClient()


def _translation_client() -> NvidiaTranslationClient:
    return NvidiaTranslationClient()


def _medical_corpus() -> MedicalRagCorpus:
    global _medical_rag_corpus
    if _medical_rag_corpus is None:
        _medical_rag_corpus = MedicalRagCorpus()
    return _medical_rag_corpus


def _textbooks_corpus() -> MedragTextbooksCorpus:
    global _medrag_textbooks_corpus
    if _medrag_textbooks_corpus is None:
        _medrag_textbooks_corpus = MedragTextbooksCorpus()
    return _medrag_textbooks_corpus


def _medcpt_query_encoder() -> MedcptQueryEncoder:
    global _medcpt_query_encoder_instance
    if _medcpt_query_encoder_instance is None:
        _medcpt_query_encoder_instance = MedcptQueryEncoder()
    return _medcpt_query_encoder_instance


def _openrouter_http_exception(exc: Exception) -> HTTPException:
    from openai import APIConnectionError, APIStatusError, OpenAIError, RateLimitError

    if isinstance(exc, RateLimitError):
        return HTTPException(
            status_code=429,
            detail=f"OpenRouter rate limit exceeded: {_openrouter_error_message(exc)}",
        )
    if isinstance(exc, APIConnectionError):
        return HTTPException(
            status_code=502,
            detail="Could not connect to OpenRouter. Check network access and OPENROUTER_BASE_URL.",
        )
    if isinstance(exc, APIStatusError):
        status_code = 502
        if exc.status_code in {401, 403}:
            detail = "OpenRouter rejected the configured API key or model access."
        else:
            detail = f"OpenRouter request failed: {_openrouter_error_message(exc)}"
        return HTTPException(status_code=status_code, detail=detail)
    if isinstance(exc, OpenAIError):
        return HTTPException(status_code=502, detail=f"OpenRouter SDK error: {str(exc)}")
    return HTTPException(status_code=502, detail=f"OpenRouter request failed: {str(exc)}")


def _openrouter_error_message(exc: Exception) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]
        if isinstance(body.get("message"), str):
            return body["message"]
    return str(exc)


def _nvidia_translation_http_exception(exc: Exception) -> HTTPException:
    from openai import APIConnectionError, APIStatusError, OpenAIError, RateLimitError

    if isinstance(exc, RateLimitError):
        return HTTPException(
            status_code=429,
            detail=f"NVIDIA translation rate limit exceeded: {_openrouter_error_message(exc)}",
        )
    if isinstance(exc, APIConnectionError):
        return HTTPException(
            status_code=502,
            detail="Could not connect to NVIDIA translation endpoint.",
        )
    if isinstance(exc, APIStatusError):
        if exc.status_code in {401, 403}:
            detail = "NVIDIA translation rejected the configured API key or model access."
        else:
            detail = f"NVIDIA translation request failed: {_openrouter_error_message(exc)}"
        return HTTPException(status_code=502, detail=detail)
    if isinstance(exc, OpenAIError):
        return HTTPException(status_code=502, detail=f"NVIDIA translation SDK error: {str(exc)}")
    return HTTPException(status_code=502, detail=f"NVIDIA translation request failed: {str(exc)}")


@router.post("/chat", response_model=AiChatResponse)
async def ai_chat(request: AiChatRequest) -> AiChatResponse:
    return await _run_ai_chat(request)


@router.post("/chat/stream")
async def ai_chat_stream(request: AiChatRequest) -> StreamingResponse:
    async def stream() -> Any:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def emit(stage: str, payload: dict[str, Any]) -> None:
            await queue.put({"event": "progress", "data": {"stage": stage, **payload}})

        async def run() -> None:
            try:
                response = await _run_ai_chat(request, emit=emit)
            except HTTPException as exc:
                await queue.put(
                    {
                        "event": "error",
                        "data": {
                            "stage": "error",
                            "message": str(exc.detail),
                            "statusCode": exc.status_code,
                        },
                    }
                )
            except Exception as exc:
                await queue.put(
                    {
                        "event": "error",
                        "data": {
                            "stage": "error",
                            "message": f"Generation failed: {exc.__class__.__name__}",
                            "statusCode": 500,
                        },
                    }
                )
            else:
                await queue.put(
                    {
                        "event": "complete",
                        "data": {
                            "stage": "complete",
                            "response": response.model_dump(),
                        },
                    }
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(run())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield _sse_message(item["event"], item["data"])
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _run_ai_chat(
    request: AiChatRequest,
    emit: ProgressEmitter | None = None,
) -> AiChatResponse:
    await _emit_progress(emit, "thinking", "Preparing request")
    append_log(
        system="ai",
        action="user_query",
        status="started",
        summary="Started AI chat request.",
        data_accessed=_request_attachment_data_access(request),
        details=_chat_request_log_details(request),
    )
    try:
        translation_language = _selected_translation_language(request)
        translated_prompt: str | None = None
        if translation_language:
            await _emit_progress(
                emit,
                "using_tool",
                "Translating prompt",
                toolName="translate_text",
            )
            await _emit_progress(
                emit,
                "waiting_for_tool",
                "Waiting for translation",
                toolName="translate_text",
            )
            append_log(
                system="nvidia",
                action="translation",
                status="started",
                summary="Translated user query to English for AI processing.",
                details={
                    "sourceLanguage": translation_language,
                    "targetLanguage": "en",
                    "textLength": len(request.prompt),
                },
            )
            translated_prompt = await run_in_threadpool(
                _translation_client().translate,
                request.prompt,
                translation_language,
                "en",
            )
            append_log(
                system="nvidia",
                action="translation",
                status="succeeded",
                summary="Translated user query to English for AI processing.",
                details={
                    "sourceLanguage": translation_language,
                    "targetLanguage": "en",
                    "textLength": len(request.prompt),
                },
            )

        messages = _initial_messages(request, translated_prompt=translated_prompt)
        client = _openrouter_client()
        tools = _tool_definitions()

        for _ in range(6):
            await _emit_progress(emit, "waiting_for_model", "Waiting for model")
            assistant_message = await run_in_threadpool(client.complete, messages, tools)
            await _emit_progress(emit, "thinking", "Thinking")
            tool_calls = assistant_message.get("tool_calls") or []
            if not tool_calls:
                answer = assistant_message.get("content") or ""
                if translation_language and answer:
                    await _emit_progress(
                        emit,
                        "using_tool",
                        "Translating answer",
                        toolName="translate_text",
                    )
                    await _emit_progress(
                        emit,
                        "waiting_for_tool",
                        "Waiting for translation",
                        toolName="translate_text",
                    )
                    append_log(
                        system="nvidia",
                        action="translation",
                        status="started",
                        summary="Translated AI answer back to the requested language.",
                        details={
                            "sourceLanguage": "en",
                            "targetLanguage": translation_language,
                            "textLength": len(answer),
                        },
                    )
                    answer = await run_in_threadpool(
                        _translation_client().translate,
                        answer,
                        "en",
                        translation_language,
                    )
                    append_log(
                        system="nvidia",
                        action="translation",
                        status="succeeded",
                        summary="Translated AI answer back to the requested language.",
                        details={
                            "sourceLanguage": "en",
                            "targetLanguage": translation_language,
                            "textLength": len(answer),
                        },
                    )
                append_log(
                    system="ai",
                    action="user_query",
                    status="succeeded",
                    summary="Completed AI chat request.",
                    data_accessed=_request_attachment_data_access(request),
                    details=_chat_request_log_details(request),
                )
                return AiChatResponse(
                    answer=answer,
                    model=OPENROUTER_MODEL,
                    generatedAt=datetime.now(timezone.utc).isoformat(),
                    reasoningDetails=assistant_message.get("reasoning_details"),
                )

            messages.append(assistant_message)
            for tool_call in tool_calls:
                tool_name = str(tool_call.get("function", {}).get("name") or "tool")
                await _emit_progress(
                    emit,
                    "using_tool",
                    f"Using {tool_name}",
                    toolName=tool_name,
                )
                await _emit_progress(
                    emit,
                    "waiting_for_tool",
                    f"Waiting for {tool_name}",
                    toolName=tool_name,
                )
                result = await _execute_tool(tool_call, request)
                _log_tool_call(tool_call, request, result)
                await _emit_progress(
                    emit,
                    "thinking",
                    "Thinking",
                    toolName=tool_name,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "name": tool_call.get("function", {}).get("name"),
                        "content": json.dumps(result, default=str),
                    }
                )

        raise HTTPException(status_code=502, detail="Nemotron tool loop exceeded the maximum depth.")
    except HTTPException as exc:
        append_log(
            system="ai",
            action="user_query",
            status="failed",
            summary="AI chat request failed.",
            data_accessed=_request_attachment_data_access(request),
            details={**_chat_request_log_details(request), "errorMessage": str(exc.detail)},
        )
        raise


async def _emit_progress(
    emit: ProgressEmitter | None,
    stage: str,
    message: str,
    **payload: Any,
) -> None:
    if emit is None:
        return
    await emit(stage, {"message": message, **payload})


def _sse_message(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _initial_messages(
    request: AiChatRequest,
    translated_prompt: str | None = None,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": f"{_system_prompt()}{_selected_skill_prompt(request.selectedSkillIds)}",
        }
    ]
    for prior in request.messages:
        message = {"role": prior.role, "content": prior.content}
        if prior.reasoning_details is not None:
            message["reasoning_details"] = prior.reasoning_details
        messages.append(message)
    messages.append({"role": "user", "content": _user_content(request, translated_prompt)})
    return messages


@lru_cache(maxsize=1)
def _tool_policy() -> str:
    policy_path = Path(__file__).with_name("tool_policy.md")
    return policy_path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1)
def _skill_workflows() -> dict[str, str]:
    skills_path = Path(__file__).resolve().parents[3] / "SKILLS.md"
    if not skills_path.exists():
        return {}
    content = skills_path.read_text(encoding="utf-8")
    sections = re.split(r"(?m)^## ", content)
    workflows: dict[str, str] = {}
    title_to_id = {
        "Data with rerank": "data_with_rerank",
        "RAG with rerank": "rag_with_rerank",
        "MyChart data": "mychart_data",
        "Wearables data": "wearables_data",
        "Open Wearables Health AI Engine": "open_wearables_health_ai",
        "Translation": "translation",
    }
    for section in sections[1:]:
        title, _, body = section.partition("\n")
        skill_id = title_to_id.get(title.strip())
        if skill_id and body.strip():
            workflows[skill_id] = f"## {title.strip()}\n{body.strip()}"
    return workflows


def _system_prompt() -> str:
    return (
        "You are WholeYou, a plain-language personal health guide. Your job is to "
        "help the user understand what is going on across their health records, "
        "wearable data, documents, images, and questions. Explain things clearly "
        "to a non-expert, connect relevant patterns, and provide practical next "
        "steps.\n\n"
        "You can take on several roles depending on the request: explain labs, "
        "reports, medications, conditions, documents, and images; analyze wearable "
        "trends and changes over time; connect MyChart and device patterns; produce "
        "structured health reports; use medical RAG for general medical background; "
        "and help the user decide what to monitor or ask a clinician.\n\n"
        "You are not a clinician and you do not diagnose. You can explain likely "
        "meanings, possibilities, patterns, risks, questions to ask, and when "
        "something deserves timely professional attention. Use tools when chart, "
        "wearable, document, image, or medical corpus evidence would improve the "
        "answer. Do not invent health facts that are not present in tool results "
        "or attached context.\n\n"
        f"{_tool_policy()}"
    )


def _selected_skill_prompt(selected_skill_ids: list[str]) -> str:
    if not selected_skill_ids:
        return ""
    allowed = {
        "data_with_rerank",
        "rag_with_rerank",
        "mychart_data",
        "wearables_data",
        "open_wearables_health_ai",
        "translation",
    }
    selected = [skill_id for skill_id in selected_skill_ids if skill_id in allowed]
    if not selected:
        return ""
    workflows = _skill_workflows()
    selected_workflows = [workflows[skill_id] for skill_id in selected if skill_id in workflows]
    workflow_text = ""
    if selected_workflows:
        workflow_text = "\n\n## Selected Skill Workflows\n\n" + "\n\n".join(selected_workflows)
    return (
        "\n\nUser-selected skills for this request: "
        f"{', '.join(selected)}. Prefer these tools when they are relevant, but still follow "
        "the tool policy and do not force an irrelevant tool call."
        f"{workflow_text}"
    )


def _user_content(request: AiChatRequest, translated_prompt: str | None = None) -> Any:
    attachment_note = ""
    if request.selectedCategoryIds or request.selectedDocuments:
        attachment_note = (
            "\n\nThe user manually attached data selections. Use the data tools to inspect "
            "these selected IDs when needed:\n"
            f"selectedCategoryIds={request.selectedCategoryIds}\n"
            f"selectedDocuments={[item.model_dump() for item in request.selectedDocuments]}"
        )
    prompt = translated_prompt or request.prompt
    if translated_prompt:
        prompt = (
            f"{translated_prompt}\n\n"
            f"Original user prompt was in {request.translationLanguage}: {request.prompt}"
        )
    text = f"{prompt}{attachment_note}"
    if not request.imageDataUrl:
        return text
    return [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": request.imageDataUrl}},
    ]


async def _execute_tool(tool_call: dict[str, Any], request: AiChatRequest) -> dict[str, Any]:
    function = tool_call.get("function", {})
    name = function.get("name")
    try:
        args = json.loads(function.get("arguments") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid tool arguments for {name}.") from exc

    if name == "mychart_data":
        return await _mychart_data(args, request)
    if name == "wearables_data":
        return await _wearables_data(args, request)
    if name == "data_with_rerank":
        return await _data_with_rerank(args, request)
    if name == "rag_with_rerank":
        return await _rag_with_rerank(args)
    if name == "translate_text":
        return await _translate_text(args)
    raise HTTPException(status_code=400, detail=f"Unknown AI tool: {name}")


async def _translate_text(args: dict[str, Any]) -> dict[str, Any]:
    text = str(args.get("text") or "")
    source_language = str(args.get("sourceLanguage") or args.get("translateFrom") or "en")
    target_language = str(args.get("targetLanguage") or args.get("translateTo") or "en")
    _validate_translation_language(source_language)
    _validate_translation_language(target_language)
    append_log(
        system="nvidia",
        action="translation",
        status="started",
        summary="Translated text using the AI translation tool.",
        details={
            "sourceLanguage": source_language,
            "targetLanguage": target_language,
            "textLength": len(text),
        },
    )
    translated = await run_in_threadpool(
        _translation_client().translate,
        text,
        source_language,
        target_language,
    )
    append_log(
        system="nvidia",
        action="translation",
        status="succeeded",
        summary="Translated text using the AI translation tool.",
        details={
            "sourceLanguage": source_language,
            "targetLanguage": target_language,
            "textLength": len(text),
        },
    )
    return {
        "sourceLanguage": source_language,
        "targetLanguage": target_language,
        "translatedText": translated,
    }


async def _mychart_data(args: dict[str, Any], request: AiChatRequest) -> dict[str, Any]:
    compact = _compact_epic_raw()
    available_categories = _epic_categories(compact)
    if args.get("mode") == "list":
        return {
            "source": "epic",
            "mode": "list",
            "categories": available_categories,
            "availableCategories": available_categories,
            "instruction": (
                "Choose relevant categoryIds from availableCategories, then call "
                "mychart_data again with mode='get'."
            ),
        }
    category_ids = _valid_category_ids(args.get("categoryIds"), source="epic")
    if not category_ids:
        return _category_selection_required(
            source="epic",
            tool_name="mychart_data",
            available_categories=available_categories,
            requested_mode=str(args.get("mode") or "get"),
        )
    selected: dict[str, Any] = {}
    for category_id in category_ids:
        key = category_id.removeprefix("epic.")
        if key in compact:
            selected[key] = compact[key]
    return {
        "source": "epic",
        "mode": "get",
        "selectedCategoryIds": category_ids,
        "availableCategories": available_categories,
        "selected": selected,
    }


async def _wearables_data(args: dict[str, Any], request: AiChatRequest) -> dict[str, Any]:
    available_categories = _wearable_categories()
    if args.get("mode") == "list":
        return {
            "source": "openWearables",
            "mode": "list",
            "categories": available_categories,
            "availableCategories": available_categories,
            "instruction": (
                "Choose relevant categoryIds from availableCategories, then call "
                "wearables_data again with mode='get'."
            ),
        }
    category_ids = _valid_category_ids(args.get("categoryIds"), source="wearables")
    if not category_ids:
        return _category_selection_required(
            source="openWearables",
            tool_name="wearables_data",
            available_categories=available_categories,
            requested_mode=str(args.get("mode") or "get"),
        )
    service = _service()
    selected: dict[str, Any] = {}
    for category_id in category_ids:
        category = WEARABLE_CATEGORY_BY_ID.get(category_id)
        selected[category.raw_key] = await _fetch_wearable_category(service, category_id)
    return {
        "source": "openWearables",
        "mode": "get",
        "selectedCategoryIds": category_ids,
        "availableCategories": available_categories,
        "selected": selected,
    }


async def _data_with_rerank(args: dict[str, Any], request: AiChatRequest) -> dict[str, Any]:
    query = str(args.get("query") or request.prompt)
    top_n = _top_n(args)
    category_ids = _valid_category_ids(args.get("categoryIds"), source="all")
    if not category_ids:
        return _rerank_category_selection_required(query=query, top_n=top_n)
    passages = await _health_data_passages(category_ids)
    append_log(
        system="nvidia",
        action="rerank",
        status="started",
        summary="Reranked selected health data passages.",
        data_accessed=_category_data_access(category_ids, access_type="rerank_search"),
        details={"topN": top_n, "passageCount": len(passages), "dataset": "selected_health_data"},
    )
    results = await run_in_threadpool(_rerank_client().rerank, query, passages, top_n)
    append_log(
        system="nvidia",
        action="rerank",
        status="succeeded",
        summary="Reranked selected health data passages.",
        data_accessed=_category_data_access(category_ids, access_type="rerank_search"),
        details={"topN": top_n, "passageCount": len(passages), "dataset": "selected_health_data"},
    )
    return {
        "query": query,
        "selectedCategoryIds": category_ids,
        "availableCategories": _available_personal_data_categories(),
        "results": results,
    }


async def _rag_with_rerank(args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "")
    top_n = _top_n(args)
    candidate_limit = max(20, top_n * 4)
    medical_passages = await run_in_threadpool(
        _medical_corpus().candidates,
        query,
        candidate_limit,
    )
    textbook_passages = await run_in_threadpool(
        _textbooks_corpus().candidates,
        query,
        candidate_limit,
    )
    passages = medical_passages + textbook_passages
    append_log(
        system="medicalRag",
        action="rerank",
        status="started",
        summary="Reranked medical RAG corpus passages.",
        data_accessed=[
            data_access_entry(source=MEDICAL_RAG_DATASET_ID, access_type="rag_passages"),
            data_access_entry(source="MedRAG/textbooks", access_type="rag_passages"),
        ],
        details={"topN": top_n, "passageCount": len(passages)},
    )
    results = await run_in_threadpool(_rerank_client().rerank, query, passages, top_n)
    append_log(
        system="medicalRag",
        action="rerank",
        status="succeeded",
        summary="Reranked medical RAG corpus passages.",
        data_accessed=[
            data_access_entry(source=MEDICAL_RAG_DATASET_ID, access_type="rag_passages"),
            data_access_entry(source="MedRAG/textbooks", access_type="rag_passages"),
        ],
        details={"topN": top_n, "passageCount": len(passages)},
    )
    return {
        "query": query,
        "datasets": [MEDICAL_RAG_DATASET_ID, "MedRAG/textbooks"],
        "results": results,
    }


async def _health_data_passages(category_ids: list[str]) -> list[dict[str, Any]]:
    passages: list[dict[str, Any]] = []
    compact = _compact_epic_raw()
    selected_epic_keys = [
        category_id.removeprefix("epic.")
        for category_id in category_ids
        if category_id.startswith("epic.")
    ]
    selected_epic_keys.sort(key=lambda key: key == "patient")
    for key in selected_epic_keys:
        if key in compact:
            passages.extend(_value_to_passages(f"epic.{key}", compact[key]))

    service: WearableDataService | None = None
    selected_wearable_ids = [
        category_id for category_id in category_ids if category_id in WEARABLE_CATEGORY_BY_ID
    ]
    for category_id in selected_wearable_ids:
        category = WEARABLE_CATEGORY_BY_ID[category_id]
        if service is None:
            service = _service()
        value = await _fetch_wearable_category(service, category_id)
        passages.extend(_value_to_passages(category_id, value))
    return passages


def _value_to_passages(source: str, value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [
            {"id": f"{source}:{index}", "source": source, "text": json.dumps(item, default=str)}
            for index, item in enumerate(value[:50])
        ]
    return [{"id": source, "source": source, "text": json.dumps(value, default=str)}]


def _epic_categories(compact: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"epic.{key}",
            "label": _label_from_key(key),
            "recordCount": _record_count(value),
        }
        for key, value in compact.items()
    ]


def _wearable_categories() -> list[dict[str, Any]]:
    return [
        {
            "id": category.id,
            "label": category.label,
            "key": category.raw_key,
        }
        for category in WEARABLE_CATEGORY_BY_ID.values()
    ]


def _available_personal_data_categories() -> dict[str, list[dict[str, Any]]]:
    return {
        "mychart": _epic_categories(_compact_epic_raw()),
        "wearables": _wearable_categories(),
    }


def _valid_category_ids(value: Any, *, source: str) -> list[str]:
    if not isinstance(value, list):
        return []
    compact = _compact_epic_raw()
    valid_ids: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        is_epic = item.startswith("epic.") and item.removeprefix("epic.") in compact
        is_wearable = item in WEARABLE_CATEGORY_BY_ID
        if source == "epic" and is_epic:
            valid_ids.append(item)
        elif source == "wearables" and is_wearable:
            valid_ids.append(item)
        elif source == "all" and (is_epic or is_wearable):
            valid_ids.append(item)
    return valid_ids


def _category_selection_required(
    *,
    source: str,
    tool_name: str,
    available_categories: list[dict[str, Any]],
    requested_mode: str,
) -> dict[str, Any]:
    return {
        "source": source,
        "toolName": tool_name,
        "mode": "list",
        "requestedMode": requested_mode,
        "requiresCategorySelection": True,
        "availableCategories": available_categories,
        "instruction": (
            "Top-level categories are embedded in availableCategories. If you are "
            "exploring whether this source has relevant data, inspect the list and "
            "decide whether to call the tool again. If you already know this source "
            "is needed, choose the relevant categoryIds and call the same tool again "
            "with mode='get'."
        ),
    }


def _rerank_category_selection_required(query: str, top_n: int) -> dict[str, Any]:
    return {
        "source": "selected_health_data",
        "toolName": "data_with_rerank",
        "query": query,
        "topN": top_n,
        "requiresCategorySelection": True,
        "availableCategories": _available_personal_data_categories(),
        "instruction": (
            "Top-level MyChart and Open Wearables categories are embedded in "
            "availableCategories. If you are exploring whether personal data might "
            "help, inspect these categories first. If personal data is needed, call "
            "data_with_rerank again with query, topN, and categoryIds for the "
            "specific top-level domains to rerank."
        ),
    }


def _chat_request_log_details(request: AiChatRequest) -> dict[str, Any]:
    return {
        "endpoint": "/api/ai/chat",
        "promptLength": len(request.prompt),
        "selectedCategoryIds": request.selectedCategoryIds,
        "selectedDocuments": [item.model_dump() for item in request.selectedDocuments],
        "selectedSkillIds": request.selectedSkillIds,
        "translationLanguage": request.translationLanguage,
        "imageAttached": bool(request.imageDataUrl),
        "messageCount": len(request.messages),
    }


def _request_attachment_data_access(request: AiChatRequest) -> list[dict[str, Any]]:
    data_accessed = _request_category_data_access(request, access_type="attached")
    for document in request.selectedDocuments:
        data_accessed.append(
            data_access_entry(
                source="epic" if document.categoryId.startswith("epic.") else "localAi",
                category_id=document.categoryId,
                category_label=(
                    _label_from_key(document.categoryId.removeprefix("epic."))
                    if document.categoryId.startswith("epic.")
                    else document.categoryId
                ),
                document_id=document.documentId,
                access_type="attached_document",
            )
        )
    if request.imageDataUrl:
        data_accessed.append(data_access_entry(source="image", access_type="attached_image"))
    return data_accessed


def _request_category_data_access(
    request: AiChatRequest,
    *,
    access_type: str,
) -> list[dict[str, Any]]:
    return _category_data_access(request.selectedCategoryIds, access_type=access_type)


def _category_data_access(
    category_ids: list[str],
    *,
    access_type: str,
) -> list[dict[str, Any]]:
    compact = _compact_epic_raw()
    data_accessed: list[dict[str, Any]] = []
    for category_id in category_ids:
        if category_id.startswith("epic."):
            key = category_id.removeprefix("epic.")
            data_accessed.append(
                data_access_entry(
                    source="epic",
                    category_id=category_id,
                    category_label=_label_from_key(key),
                    record_count=_record_count(compact[key]) if key in compact else None,
                    access_type=access_type,
                )
            )
            continue
        category = WEARABLE_CATEGORY_BY_ID.get(category_id)
        if category:
            data_accessed.append(
                data_access_entry(
                    source="openWearables",
                    category_id=category_id,
                    category_label=category.label,
                    access_type=access_type,
                )
            )
    return data_accessed


def _data_access_from_tool_result(
    name: str,
    args: dict[str, Any],
    request: AiChatRequest,
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    if name == "mychart_data":
        if args.get("mode") == "list" or result.get("requiresCategorySelection"):
            return [data_access_entry(source="epic", access_type="metadata_list")]
        selected = result.get("selected") if isinstance(result, dict) else {}
        if not isinstance(selected, dict):
            return []
        return [
            data_access_entry(
                source="epic",
                category_id=f"epic.{key}",
                category_label=_label_from_key(key),
                record_count=_record_count(value),
                access_type="raw_category",
            )
            for key, value in selected.items()
        ]
    if name == "wearables_data":
        if args.get("mode") == "list" or result.get("requiresCategorySelection"):
            return [data_access_entry(source="openWearables", access_type="metadata_list")]
        selected = result.get("selected") if isinstance(result, dict) else {}
        if not isinstance(selected, dict):
            return []
        by_key = {category.raw_key: category for category in WEARABLE_CATEGORY_BY_ID.values()}
        entries: list[dict[str, Any]] = []
        for key, value in selected.items():
            category = by_key.get(key)
            entries.append(
                data_access_entry(
                    source="openWearables",
                    category_id=category.id if category else None,
                    category_label=category.label if category else str(key),
                    record_count=_record_count(value),
                    access_type="raw_category",
                )
            )
        return entries
    if name == "data_with_rerank":
        if result.get("requiresCategorySelection"):
            return [
                data_access_entry(source="epic", access_type="metadata_list"),
                data_access_entry(source="openWearables", access_type="metadata_list"),
            ]
        category_ids = result.get("selectedCategoryIds")
        if isinstance(category_ids, list):
            return _category_data_access(category_ids, access_type="rerank_search")
        return _request_category_data_access(request, access_type="rerank_search")
    if name == "rag_with_rerank":
        return [
            data_access_entry(source=MEDICAL_RAG_DATASET_ID, access_type="rag_passages"),
            data_access_entry(source="MedRAG/textbooks", access_type="rag_passages"),
        ]
    if name == "translate_text":
        return [data_access_entry(source="nvidia", access_type="translation")]
    return []


def _log_tool_call(tool_call: dict[str, Any], request: AiChatRequest, result: dict[str, Any]) -> None:
    function = tool_call.get("function", {})
    name = str(function.get("name") or "unknown")
    try:
        args = json.loads(function.get("arguments") or "{}")
    except json.JSONDecodeError:
        args = {}
    append_log(
        system="llm",
        action="llm_tool_call",
        status="succeeded",
        summary=f"Nemotron called {name}.",
        data_accessed=_data_access_from_tool_result(name, args, request, result),
        details={
            "toolName": name,
            "mode": args.get("mode"),
            "categoryIds": args.get("categoryIds"),
            "topN": args.get("topN"),
            "sourceLanguage": args.get("sourceLanguage") or args.get("translateFrom"),
            "targetLanguage": args.get("targetLanguage") or args.get("translateTo"),
            "selectedCategoryIds": request.selectedCategoryIds,
            "selectedDocuments": [item.model_dump() for item in request.selectedDocuments],
            "selectedSkillIds": request.selectedSkillIds,
        },
    )


def _tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "data_with_rerank",
                "description": (
                    "Search specific top-level MyChart and Open Wearables categories, "
                    "rerank them, and return relevant snippets. Provide categoryIds. "
                    "If categoryIds are omitted, the tool returns embedded available "
                    "top-level categories instead of raw data."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "topN": {"type": "integer", "minimum": 1, "maximum": 10},
                        "categoryIds": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "rag_with_rerank",
                "description": "Search the medical RAG corpus, rerank candidates, and return evidence snippets.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "topN": {"type": "integer", "minimum": 1, "maximum": 10},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "mychart_data",
                "description": (
                    "List or fetch MyChart top-level categories. Use mode='list' when "
                    "exploring whether MyChart has relevant data. Use mode='get' with "
                    "known categoryIds when you already need specific top-level "
                    "domains. If mode='get' omits categoryIds, only embedded category "
                    "metadata is returned."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string", "enum": ["list", "get"]},
                        "categoryIds": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["mode"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "wearables_data",
                "description": (
                    "List or fetch Open Wearables top-level categories. Use mode='list' "
                    "when exploring whether wearable data has relevant signals. Use "
                    "mode='get' with known categoryIds when you already need specific "
                    "top-level domains. If mode='get' omits categoryIds, only embedded "
                    "category metadata is returned."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string", "enum": ["list", "get"]},
                        "categoryIds": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["mode"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "translate_text",
                "description": "Translate text between supported NVIDIA Riva translation languages.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "sourceLanguage": {
                            "type": "string",
                            "enum": list(SUPPORTED_TRANSLATION_LANGUAGES.keys()),
                        },
                        "targetLanguage": {
                            "type": "string",
                            "enum": list(SUPPORTED_TRANSLATION_LANGUAGES.keys()),
                        },
                    },
                    "required": ["text", "sourceLanguage", "targetLanguage"],
                },
            },
        },
    ]


def _message_to_dict(message: Any) -> dict[str, Any]:
    if isinstance(message, dict):
        return message
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    result = {"role": getattr(message, "role", "assistant"), "content": getattr(message, "content", None)}
    reasoning_details = getattr(message, "reasoning_details", None)
    if reasoning_details is not None:
        result["reasoning_details"] = reasoning_details
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        result["tool_calls"] = [_message_to_dict(tool_call) for tool_call in tool_calls]
    return result


def _top_n(args: dict[str, Any]) -> int:
    try:
        return max(1, min(10, int(args.get("topN", 5))))
    except (TypeError, ValueError):
        return 5


def _query_terms(query: str) -> set[str]:
    return {term for term in re.findall(r"[a-z0-9]+", query.lower()) if len(term) > 2}


def _fts5_token(term: str) -> str:
    return f'"{term.replace(chr(34), chr(34) + chr(34))}"'


def _embedding_shard_range(path: Path) -> tuple[int, int] | None:
    match = re.fullmatch(r"embeddings_(\d{6})_(\d{6})\.pt", path.name)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def _best_torch_device(torch_module: Any) -> str:
    if torch_module.cuda.is_available():
        return "cuda"
    if getattr(torch_module.backends, "mps", None) and torch_module.backends.mps.is_available():
        return "mps"
    return "cpu"


def _repo_relative_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return Path(__file__).resolve().parents[3] / candidate


def _line_to_text(line: str) -> str | None:
    line = line.strip()
    if not line:
        return None
    if line.startswith("{"):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return line
        for key in ("text", "content", "passage", "answer", "response"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        return json.dumps(payload, default=str)
    return line


SUPPORTED_TRANSLATION_LANGUAGES = {
    "en": "English",
    "de": "German",
    "es-ES": "European Spanish",
    "es-US": "Latin American Spanish",
    "fr": "French",
    "pt-BR": "Brazilian Portuguese",
    "ru": "Russian",
    "zh-CN": "Simplified Chinese",
    "zh-TW": "Traditional Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
}


def _selected_translation_language(request: AiChatRequest) -> str | None:
    if "translation" not in request.selectedSkillIds:
        return None
    if not request.translationLanguage or request.translationLanguage == "en":
        return None
    _validate_translation_language(request.translationLanguage)
    return request.translationLanguage


def _validate_translation_language(language: str) -> None:
    if language not in SUPPORTED_TRANSLATION_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported translation language: {language}")
