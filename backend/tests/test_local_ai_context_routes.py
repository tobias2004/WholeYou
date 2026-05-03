import unittest
from datetime import datetime

from fastapi.testclient import TestClient

import data_sources.local_ai.routes as local_ai_routes
from main import app
from session_store import SESSION_DATA


class FakeWearableDataService:
    def __init__(self):
        self.calls = []

    async def get_connections(self, user_id):
        self.calls.append(("get_connections", user_id))
        return [{"provider": "oura"}]

    async def get_summary(self, user_id, summary_type):
        self.calls.append(("get_summary", user_id, summary_type))
        return {"summaryType": summary_type}

    async def get_data_sources(self, user_id):
        self.calls.append(("get_data_sources", user_id))
        return {"dataSources": [{"provider": "oura"}]}

    async def get_timeseries(self, user_id, filters=None):
        self.calls.append(("get_timeseries", user_id, filters))
        return [{"type": filters["type"], "value": 64}]

    async def get_workouts(self, user_id, filters=None):
        self.calls.append(("get_workouts", user_id, filters))
        return [{"id": "workout-1"}]

    async def get_sleep(self, user_id, filters=None):
        self.calls.append(("get_sleep", user_id, filters))
        return [{"id": "sleep-1"}]

    async def get_health_scores(self, user_id, filters=None):
        self.calls.append(("get_health_scores", user_id, filters))
        return [{"category": "sleep", "value": 82}]


class LocalAiContextRoutesTests(unittest.TestCase):
    def setUp(self):
        SESSION_DATA.clear()
        self.fake_service = FakeWearableDataService()
        self.original_service = local_ai_routes._service
        local_ai_routes._service = lambda: self.fake_service
        self.client = TestClient(app)

    def tearDown(self):
        local_ai_routes._service = self.original_service
        SESSION_DATA.clear()

    def test_available_returns_metadata_without_raw_payloads(self):
        SESSION_DATA["raw"] = {
            "patient": {
                "resourceType": "Patient",
                "id": "patient-123",
                "name": [{"text": "Test Patient"}],
            },
            "observations_labs": [
                {
                    "resourceType": "Observation",
                    "id": "lab-1",
                    "valueString": "large raw value should not appear",
                }
            ],
        }

        response = self.client.get("/api/local-ai/context/available")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        epic = next(source for source in payload["sources"] if source["id"] == "epic")
        open_wearables = next(
            source for source in payload["sources"] if source["id"] == "openWearables"
        )
        epic_categories = {category["id"]: category for category in epic["categories"]}
        self.assertEqual(
            epic_categories["epic.patient"],
            {
                "id": "epic.patient",
                "source": "epic",
                "key": "patient",
                "label": "Patient",
                "available": True,
                "recordCount": 1,
            },
        )
        self.assertEqual(
            epic_categories["epic.observations_labs"],
            {
                "id": "epic.observations_labs",
                "source": "epic",
                "key": "observations_labs",
                "label": "Observations Labs",
                "available": True,
                "recordCount": 1,
            },
        )
        heart_rate = next(
            category
            for category in open_wearables["categories"]
            if category["id"] == "wearables.timeseries.heart_rate"
        )
        self.assertEqual(
            heart_rate,
            {
                "id": "wearables.timeseries.heart_rate",
                "source": "openWearables",
                "key": "heartRate",
                "label": "Heart Rate",
                "available": True,
                "recordCount": None,
            },
        )
        payload_text = response.text
        self.assertIn("epic.patient", payload_text)
        self.assertIn("epic.observations_labs", payload_text)
        self.assertNotIn("Test Patient", payload_text)
        self.assertNotIn("large raw value should not appear", payload_text)

    def test_raw_returns_only_selected_epic_categories(self):
        from audit_logs import list_logs

        SESSION_DATA["raw"] = {
            "patient": {"resourceType": "Patient", "id": "patient-123"},
            "observations_labs": [{"resourceType": "Observation", "id": "lab-1"}],
        }

        response = self.client.post(
            "/api/local-ai/context/raw",
            json={"categoryIds": ["epic.patient"]},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        selected = payload["selectedRawContext"]
        self.assertEqual(
            selected,
            {"epic": {"patient": {"resourceType": "Patient", "id": "patient-123"}}},
        )
        self.assertNotIn("observations_labs", selected["epic"])
        datetime.fromisoformat(payload["generatedAt"])
        logs = list_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["action"], "api_context_fetch")
        self.assertEqual(logs[0]["status"], "succeeded")
        self.assertEqual(
            logs[0]["dataAccessed"],
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
        self.assertNotIn("patient-123", str(logs))

    def test_raw_fetches_only_requested_wearable_category(self):
        response = self.client.post(
            "/api/local-ai/context/raw",
            json={"categoryIds": ["wearables.timeseries.heart_rate"]},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        selected = payload["selectedRawContext"]
        self.assertEqual(
            selected,
            {"openWearables": {"heartRate": [{"type": "heart_rate", "value": 64}]}},
        )
        datetime.fromisoformat(payload["generatedAt"])
        self.assertEqual(
            self.fake_service.calls,
            [("get_timeseries", "local", {"type": "heart_rate", "limit": 12})],
        )

    def test_documents_returns_metadata_without_raw_payloads(self):
        SESSION_DATA["raw"] = {
            "documents_clinical_notes": [
                {
                    "resourceType": "DocumentReference",
                    "id": "doc-1",
                    "type": {"text": "Progress Note"},
                    "description": "Annual visit note",
                    "date": "2026-04-03T10:15:00Z",
                    "contained": [
                        {
                            "resourceType": "Binary",
                            "contentType": "text/html",
                            "data": "large raw note should not appear",
                        }
                    ],
                    "content": [
                        {
                            "attachment": {
                                "contentType": "text/html",
                                "title": "Visit HTML",
                            }
                        }
                    ],
                }
            ],
        }

        response = self.client.get("/api/local-ai/context/documents")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["documents"],
            [
                {
                    "id": "doc-1",
                    "categoryId": "epic.documents_clinical_notes",
                    "documentType": "Progress Note",
                    "details": "Annual visit note",
                    "date": "2026-04-03T10:15:00Z",
                    "contentType": "text/html",
                }
            ],
        )
        self.assertNotIn("large raw note should not appear", response.text)

    def test_document_raw_returns_only_selected_document(self):
        SESSION_DATA["raw"] = {
            "documents_clinical_notes": [
                {
                    "resourceType": "DocumentReference",
                    "id": "doc-1",
                    "description": "Selected note",
                },
                {
                    "resourceType": "DocumentReference",
                    "id": "doc-2",
                    "description": "Other note",
                },
            ],
        }

        response = self.client.post(
            "/api/local-ai/context/document/raw",
            json={
                "categoryId": "epic.documents_clinical_notes",
                "documentId": "doc-1",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["selectedRawContext"],
            {
                "epic": {
                    "documents_clinical_notes": [
                        {
                            "resourceType": "DocumentReference",
                            "id": "doc-1",
                            "description": "Selected note",
                        }
                    ]
                }
            },
        )
        self.assertNotIn("Other note", response.text)
        datetime.fromisoformat(payload["generatedAt"])

    def test_raw_rejects_unknown_categories(self):
        response = self.client.post(
            "/api/local-ai/context/raw",
            json={"categoryIds": ["unknown.category"]},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unknown context category", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
