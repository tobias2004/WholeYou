import unittest

from fastapi.testclient import TestClient

from main import app
from session_store import SESSION_DATA


class AuditLogsTests(unittest.TestCase):
    def setUp(self):
        SESSION_DATA.clear()
        self.client = TestClient(app)

    def tearDown(self):
        SESSION_DATA.clear()

    def test_append_and_list_logs_sanitize_sensitive_details(self):
        from audit_logs import append_log, list_logs

        append_log(
            system="ai",
            action="user_query",
            status="succeeded",
            summary="AI request completed.",
            data_accessed=[
                {
                    "source": "epic",
                    "categoryId": "epic.patient",
                    "categoryLabel": "Patient",
                    "recordCount": 1,
                    "rawPayload": {"id": "patient-123"},
                }
            ],
            details={
                "prompt": "What is my diagnosis?",
                "promptLength": 21,
                "imageDataUrl": "data:image/png;base64,abc",
                "answer": "The answer text",
                "authorizationCode": "secret-code",
                "selectedSkillIds": ["mychart_data"],
            },
        )

        logs = list_logs()

        self.assertEqual(len(logs), 1)
        log = logs[0]
        self.assertEqual(log["system"], "ai")
        self.assertEqual(log["action"], "user_query")
        self.assertEqual(log["status"], "succeeded")
        self.assertEqual(log["details"]["promptLength"], 21)
        self.assertEqual(log["details"]["selectedSkillIds"], ["mychart_data"])
        self.assertNotIn("prompt", log["details"])
        self.assertNotIn("imageDataUrl", log["details"])
        self.assertNotIn("answer", log["details"])
        self.assertNotIn("authorizationCode", log["details"])
        self.assertEqual(
            log["dataAccessed"],
            [
                {
                    "source": "epic",
                    "categoryId": "epic.patient",
                    "categoryLabel": "Patient",
                    "recordCount": 1,
                }
            ],
        )
        self.assertNotIn("What is my diagnosis?", str(log))
        self.assertNotIn("patient-123", str(log))

    def test_log_store_keeps_most_recent_entries_with_fixed_limit(self):
        from audit_logs import append_log, list_logs

        for index in range(505):
            append_log(
                system="backend",
                action="test_action",
                status="succeeded",
                summary=f"Entry {index}",
            )

        logs = list_logs()

        self.assertEqual(len(logs), 500)
        self.assertEqual(logs[0]["summary"], "Entry 5")
        self.assertEqual(logs[-1]["summary"], "Entry 504")

    def test_logs_routes_list_and_clear_backend_memory_entries(self):
        from audit_logs import append_log

        append_log(
            system="openWearables",
            action="account_link",
            status="succeeded",
            summary="Connected Oura.",
            details={"provider": "oura", "mode": "synthetic"},
        )

        response = self.client.get("/api/logs")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["logs"]), 1)
        self.assertEqual(payload["logs"][0]["summary"], "Connected Oura.")

        clear_response = self.client.delete("/api/logs")

        self.assertEqual(clear_response.status_code, 200)
        self.assertEqual(clear_response.json(), {"cleared": 1})
        self.assertEqual(self.client.get("/api/logs").json(), {"logs": []})


if __name__ == "__main__":
    unittest.main()
