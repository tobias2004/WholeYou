import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import torch
from fastapi.testclient import TestClient
from openai import RateLimitError

import data_sources.ai.routes as ai_routes
from main import app
from session_store import SESSION_DATA


class FakeOpenRouterClient:
    def __init__(self, messages):
        self.messages = list(messages)
        self.calls = []

    def complete(self, messages, tools):
        self.calls.append({"messages": messages, "tools": tools})
        return self.messages.pop(0)


class FakeRerankClient:
    def __init__(self):
        self.calls = []

    def rerank(self, query, passages, top_n=5):
        self.calls.append({"query": query, "passages": passages, "top_n": top_n})
        return [
            {"index": 0, "relevance_score": 0.98, "text": passages[0]["text"]},
        ]


class FakeMedicalCorpus:
    def candidates(self, query, limit=20):
        return [
            {
                "id": "medical-1",
                "text": "Hypertension can be evaluated with repeated blood pressure readings.",
                "source": "medical-rag-corpus",
            }
        ]


class FakeTextbooksCorpus:
    def candidates(self, query, limit=20):
        return [
            {
                "id": "textbook-1",
                "text": "Harrison describes evaluation of sustained elevated blood pressure.",
                "source": "MedRAG/textbooks",
            }
        ]


class FakeQueryEncoder:
    def embed(self, query):
        del query
        return torch.tensor([1.0, 0.0], dtype=torch.float32)


class FakeTranslationClient:
    def __init__(self):
        self.calls = []

    def translate(self, text, source_language, target_language):
        self.calls.append(
            {
                "text": text,
                "source_language": source_language,
                "target_language": target_language,
            }
        )
        if target_language == "en":
            return "What conditions matter for this patient?"
        return "Estas condiciones importan."


class FailingChatCompletions:
    def create(self, **kwargs):
        del kwargs
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        response = httpx.Response(
            429,
            request=request,
            json={
                "error": {
                    "message": (
                        "Rate limit exceeded: free-models-per-day. "
                        "Add 10 credits to unlock 1000 free model requests per day"
                    ),
                    "code": 429,
                    "metadata": {"user_id": "should-not-leak"},
                }
            },
        )
        raise RateLimitError(
            "Error code: 429",
            response=response,
            body=response.json(),
        )


class FailingOpenAiClient:
    def __init__(self):
        self.chat = type("Chat", (), {"completions": FailingChatCompletions()})()


class AiRoutesTests(unittest.TestCase):
    def setUp(self):
        SESSION_DATA.clear()
        SESSION_DATA["raw"] = {
            "patient": {"resourceType": "Patient", "id": "patient-123", "name": [{"text": "Camila"}]},
            "conditions_problems": [
                {"resourceType": "Condition", "id": "condition-1", "code": {"text": "Hypertension"}}
            ],
        }
        self.original_openrouter_client = ai_routes._openrouter_client
        self.original_rerank_client = ai_routes._rerank_client
        self.original_medical_corpus = ai_routes._medical_corpus
        self.original_textbooks_corpus = ai_routes._textbooks_corpus
        self.original_translation_client = ai_routes._translation_client
        self.rerank_client = FakeRerankClient()
        self.translation_client = FakeTranslationClient()
        ai_routes._rerank_client = lambda: self.rerank_client
        ai_routes._medical_corpus = lambda: FakeMedicalCorpus()
        ai_routes._textbooks_corpus = lambda: FakeTextbooksCorpus()
        ai_routes._translation_client = lambda: self.translation_client
        self.client = TestClient(app)

    def tearDown(self):
        ai_routes._openrouter_client = self.original_openrouter_client
        ai_routes._rerank_client = self.original_rerank_client
        ai_routes._medical_corpus = self.original_medical_corpus
        ai_routes._textbooks_corpus = self.original_textbooks_corpus
        ai_routes._translation_client = self.original_translation_client
        SESSION_DATA.clear()

    def test_chat_runs_openrouter_tool_loop_with_reasoning_enabled_tools(self):
        openrouter_client = FakeOpenRouterClient(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "reasoning_details": [{"type": "reasoning", "text": "Need chart data."}],
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "mychart_data",
                                "arguments": '{"mode":"get","categoryIds":["epic.patient"]}',
                            },
                        }
                    ],
                },
                {
                    "role": "assistant",
                    "content": "Camila is the selected patient.",
                    "reasoning_details": [{"type": "reasoning", "text": "Answered from patient data."}],
                },
            ]
        )
        ai_routes._openrouter_client = lambda: openrouter_client

        response = self.client.post(
            "/api/ai/chat",
            json={
                "prompt": "Who is the patient?",
                "selectedCategoryIds": ["epic.patient"],
                "selectedSkillIds": [
                    "data_with_rerank",
                    "rag_with_rerank",
                    "open_wearables_health_ai",
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["answer"], "Camila is the selected patient.")
        self.assertEqual(payload["model"], "nvidia/nemotron-3-super-120b-a12b:free")
        self.assertEqual(len(openrouter_client.calls), 2)
        first_system_message = openrouter_client.calls[0]["messages"][0]
        self.assertEqual(first_system_message["role"], "system")
        self.assertIn("plain-language personal health guide", first_system_message["content"])
        self.assertIn("structured health reports", first_system_message["content"])
        self.assertIn("Use `data_with_rerank`", first_system_message["content"])
        self.assertIn("Use `rag_with_rerank`", first_system_message["content"])
        self.assertIn("User-selected skills for this request", first_system_message["content"])
        self.assertIn("data_with_rerank", first_system_message["content"])
        self.assertIn("Open Wearables Health AI Engine", first_system_message["content"])
        self.assertIn("## Selected Skill Workflows", first_system_message["content"])
        self.assertIn("Prefer these tools when they are relevant", first_system_message["content"])
        self.assertIn("recommend adding MyChart data", first_system_message["content"])
        self.assertIn("side effects", first_system_message["content"])
        self.assertIn("reranked RAG", first_system_message["content"])
        tool_names = {
            tool["function"]["name"]
            for tool in openrouter_client.calls[0]["tools"]
            if tool["type"] == "function"
        }
        self.assertEqual(
            tool_names,
            {
                "data_with_rerank",
                "rag_with_rerank",
                "mychart_data",
                "wearables_data",
                "translate_text",
            },
        )
        second_call_messages = openrouter_client.calls[1]["messages"]
        self.assertEqual(second_call_messages[-1]["role"], "tool")
        self.assertEqual(second_call_messages[-1]["tool_call_id"], "call-1")
        self.assertIn("patient-123", second_call_messages[-1]["content"])
        assistant_tool_message = second_call_messages[-2]
        self.assertEqual(
            assistant_tool_message["reasoning_details"],
            [{"type": "reasoning", "text": "Need chart data."}],
        )

    def test_chat_stream_emits_progress_tool_and_complete_events(self):
        openrouter_client = FakeOpenRouterClient(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "mychart_data",
                                "arguments": '{"mode":"get","categoryIds":["epic.patient"]}',
                            },
                        }
                    ],
                },
                {"role": "assistant", "content": "Camila is the selected patient."},
            ]
        )
        ai_routes._openrouter_client = lambda: openrouter_client

        with self.client.stream(
            "POST",
            "/api/ai/chat/stream",
            json={"prompt": "Who is the patient?"},
        ) as response:
            body = response.read().decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: progress", body)
        self.assertIn('"stage": "waiting_for_model"', body)
        self.assertIn('"stage": "using_tool"', body)
        self.assertIn('"toolName": "mychart_data"', body)
        self.assertIn("event: complete", body)
        self.assertIn("Camila is the selected patient.", body)

    def test_chat_appends_safe_audit_logs_for_request_and_tool_access(self):
        from audit_logs import list_logs

        openrouter_client = FakeOpenRouterClient(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "mychart_data",
                                "arguments": '{"mode":"get","categoryIds":["epic.patient"]}',
                            },
                        }
                    ],
                },
                {"role": "assistant", "content": "Camila is the selected patient."},
            ]
        )
        ai_routes._openrouter_client = lambda: openrouter_client

        response = self.client.post(
            "/api/ai/chat",
            json={
                "prompt": "Who is Camila?",
                "selectedCategoryIds": ["epic.patient"],
                "selectedDocuments": [
                    {"categoryId": "epic.documents_labs", "documentId": "doc-1"}
                ],
                "selectedSkillIds": ["mychart_data"],
                "imageDataUrl": "data:image/png;base64,abc",
            },
        )

        self.assertEqual(response.status_code, 200)
        logs = list_logs()
        self.assertTrue(
            any(log["action"] == "user_query" and log["status"] == "started" for log in logs)
        )
        self.assertTrue(
            any(log["action"] == "user_query" and log["status"] == "succeeded" for log in logs)
        )
        tool_logs = [log for log in logs if log["action"] == "llm_tool_call"]
        self.assertEqual(len(tool_logs), 1)
        self.assertEqual(tool_logs[0]["details"]["toolName"], "mychart_data")
        self.assertEqual(tool_logs[0]["details"]["mode"], "get")
        self.assertEqual(tool_logs[0]["details"]["selectedSkillIds"], ["mychart_data"])
        self.assertEqual(
            tool_logs[0]["dataAccessed"],
            [
                {
                    "source": "epic",
                    "categoryId": "epic.patient",
                    "categoryLabel": "Patient",
                    "recordCount": 1,
                    "accessType": "raw_category",
                }
            ],
        )
        logs_text = str(logs)
        self.assertNotIn("Who is Camila?", logs_text)
        self.assertNotIn("data:image/png", logs_text)
        self.assertNotIn("Camila is the selected patient", logs_text)
        self.assertNotIn("patient-123", logs_text)

    def test_data_and_rag_tools_use_nvidia_rerank_results(self):
        openrouter_client = FakeOpenRouterClient(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "data_with_rerank",
                                "arguments": (
                                    '{"query":"blood pressure","topN":1,'
                                    '"categoryIds":["epic.conditions_problems"]}'
                                ),
                            },
                        },
                        {
                            "id": "call-2",
                            "type": "function",
                            "function": {
                                "name": "rag_with_rerank",
                                "arguments": '{"query":"blood pressure","topN":1}',
                            },
                        },
                    ],
                },
                {"role": "assistant", "content": "Reranked evidence is available."},
            ]
        )
        ai_routes._openrouter_client = lambda: openrouter_client

        response = self.client.post("/api/ai/chat", json={"prompt": "Assess blood pressure"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "Reranked evidence is available.")
        self.assertEqual(len(self.rerank_client.calls), 2)
        self.assertEqual(self.rerank_client.calls[0]["query"], "blood pressure")
        self.assertGreaterEqual(len(self.rerank_client.calls[0]["passages"]), 1)
        self.assertIn("Hypertension", self.rerank_client.calls[0]["passages"][0]["text"])
        self.assertEqual(self.rerank_client.calls[1]["passages"][0]["source"], "medical-rag-corpus")
        self.assertEqual(self.rerank_client.calls[1]["passages"][1]["source"], "MedRAG/textbooks")

    def test_data_tools_return_category_metadata_when_get_lacks_category_ids(self):
        openrouter_client = FakeOpenRouterClient(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-mychart",
                            "type": "function",
                            "function": {
                                "name": "mychart_data",
                                "arguments": '{"mode":"get"}',
                            },
                        },
                        {
                            "id": "call-wearables",
                            "type": "function",
                            "function": {
                                "name": "wearables_data",
                                "arguments": '{"mode":"get"}',
                            },
                        },
                    ],
                },
                {"role": "assistant", "content": "I need category choices."},
            ]
        )
        ai_routes._openrouter_client = lambda: openrouter_client

        response = self.client.post("/api/ai/chat", json={"prompt": "Check my data"})

        self.assertEqual(response.status_code, 200)
        tool_results = [message for message in openrouter_client.calls[1]["messages"] if message["role"] == "tool"]
        mychart_result = ai_routes.json.loads(tool_results[0]["content"])
        wearable_result = ai_routes.json.loads(tool_results[1]["content"])
        self.assertEqual(mychart_result["mode"], "list")
        self.assertEqual(mychart_result["requiresCategorySelection"], True)
        self.assertIn("epic.patient", [category["id"] for category in mychart_result["availableCategories"]])
        self.assertEqual(wearable_result["mode"], "list")
        self.assertEqual(wearable_result["requiresCategorySelection"], True)
        self.assertIn(
            "wearables.health_scores",
            [category["id"] for category in wearable_result["availableCategories"]],
        )
        self.assertEqual(self.rerank_client.calls, [])

    def test_data_with_rerank_requires_explicit_category_selection(self):
        openrouter_client = FakeOpenRouterClient(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-rerank",
                            "type": "function",
                            "function": {
                                "name": "data_with_rerank",
                                "arguments": '{"query":"blood pressure","topN":1}',
                            },
                        }
                    ],
                },
                {"role": "assistant", "content": "I need category choices."},
            ]
        )
        ai_routes._openrouter_client = lambda: openrouter_client

        response = self.client.post("/api/ai/chat", json={"prompt": "Assess blood pressure"})

        self.assertEqual(response.status_code, 200)
        tool_result = next(
            message for message in openrouter_client.calls[1]["messages"] if message["role"] == "tool"
        )
        payload = ai_routes.json.loads(tool_result["content"])
        self.assertEqual(payload["requiresCategorySelection"], True)
        self.assertEqual(payload["query"], "blood pressure")
        self.assertIn("epic.patient", [category["id"] for category in payload["availableCategories"]["mychart"]])
        self.assertIn(
            "wearables.health_scores",
            [category["id"] for category in payload["availableCategories"]["wearables"]],
        )
        self.assertEqual(self.rerank_client.calls, [])

    def test_dense_medical_corpus_uses_embeddings_before_sqlite_text_lookup(self):
        with TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            shard_dir = data_dir / "embedding_shards"
            shard_dir.mkdir()
            torch.save(
                torch.tensor([[0.0, 1.0], [3.0, 0.0]], dtype=torch.float32),
                shard_dir / "embeddings_000000_000002.pt",
            )
            with ai_routes.sqlite3.connect(data_dir / "textbooks.sqlite") as connection:
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
                connection.executemany(
                    """
                    INSERT INTO documents
                    (embedding_index, id, text, title, source, category, dataset_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            0,
                            "wrong",
                            "hypertension keyword match",
                            "Wrong",
                            "MedRAG/textbooks",
                            "textbook",
                            "MedRAG/textbooks",
                        ),
                        (
                            1,
                            "dense-hit",
                            "semantic dense result",
                            "Dense",
                            "MedRAG/textbooks",
                            "textbook",
                            "MedRAG/textbooks",
                        ),
                    ],
                )

            corpus = ai_routes.LocalDenseMedicalCorpus(
                data_dir=str(data_dir),
                dataset_id="MedRAG/textbooks",
                sqlite_name="textbooks.sqlite",
                query_encoder=FakeQueryEncoder(),
            )

            rows = corpus.candidates("hypertension", limit=1)

            self.assertEqual(rows[0]["id"], "dense-hit")
            self.assertEqual(rows[0]["dense_score"], 3.0)

    def test_translation_skill_translates_prompt_to_english_and_answer_back(self):
        openrouter_client = FakeOpenRouterClient(
            [{"role": "assistant", "content": "These conditions matter."}]
        )
        ai_routes._openrouter_client = lambda: openrouter_client

        response = self.client.post(
            "/api/ai/chat",
            json={
                "prompt": "Que condiciones importan?",
                "selectedSkillIds": ["translation"],
                "translationLanguage": "es-US",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "Estas condiciones importan.")
        self.assertEqual(
            self.translation_client.calls,
            [
                {
                    "text": "Que condiciones importan?",
                    "source_language": "es-US",
                    "target_language": "en",
                },
                {
                    "text": "These conditions matter.",
                    "source_language": "en",
                    "target_language": "es-US",
                },
            ],
        )
        self.assertIn("What conditions matter", openrouter_client.calls[0]["messages"][-1]["content"])

    def test_translate_text_tool_returns_translation(self):
        openrouter_client = FakeOpenRouterClient(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-translate",
                            "type": "function",
                            "function": {
                                "name": "translate_text",
                                "arguments": (
                                    '{"text":"hello","sourceLanguage":"en",'
                                    '"targetLanguage":"es-US"}'
                                ),
                            },
                        }
                    ],
                },
                {"role": "assistant", "content": "Translation complete."},
            ]
        )
        ai_routes._openrouter_client = lambda: openrouter_client

        response = self.client.post("/api/ai/chat", json={"prompt": "Translate hello"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "Translation complete.")
        self.assertEqual(
            self.translation_client.calls,
            [{"text": "hello", "source_language": "en", "target_language": "es-US"}],
        )
        self.assertIn("Estas condiciones importan.", openrouter_client.calls[1]["messages"][-1]["content"])

    def test_openrouter_client_returns_clean_rate_limit_error(self):
        client = ai_routes.OpenRouterNemotronClient.__new__(ai_routes.OpenRouterNemotronClient)
        client.model = "nvidia/nemotron-3-super-120b-a12b:free"
        client._client = FailingOpenAiClient()

        with self.assertRaises(ai_routes.HTTPException) as raised:
            client.complete([{"role": "user", "content": "hello"}], [])

        self.assertEqual(raised.exception.status_code, 429)
        self.assertIn("OpenRouter rate limit exceeded", raised.exception.detail)
        self.assertIn("free-models-per-day", raised.exception.detail)
        self.assertNotIn("should-not-leak", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
