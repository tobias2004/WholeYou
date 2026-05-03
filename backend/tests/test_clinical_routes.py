import unittest

from fastapi.testclient import TestClient

from main import app
from session_store import SESSION_DATA


class ClinicalRoutesTests(unittest.TestCase):
    def setUp(self):
        SESSION_DATA.clear()
        self.client = TestClient(app)

    def tearDown(self):
        SESSION_DATA.clear()

    def test_clinical_summary_returns_disconnected_shape(self):
        response = self.client.get("/api/clinical/summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["connected"])
        self.assertEqual(payload["conditions"], [])
        self.assertEqual(payload["medications"], [])
        self.assertEqual(payload["labs"], [])
        self.assertEqual(payload["vitals"], [])
        self.assertEqual(payload["encounters"], [])

    def test_clinical_slice_routes_return_normalized_lists(self):
        SESSION_DATA["clinical_summary"] = {
            "connected": True,
            "conditions": [{"id": "c1", "source": "epic"}],
            "medications": [{"id": "m1", "source": "epic"}],
            "labs": [{"id": "l1", "source": "epic"}],
            "vitals": [{"id": "v1", "source": "epic"}],
            "encounters": [{"id": "e1", "source": "epic"}],
            "generatedAt": "2026-05-02T00:00:00Z",
        }

        self.assertEqual(self.client.get("/api/clinical/conditions").json()[0]["id"], "c1")
        self.assertEqual(self.client.get("/api/clinical/medications").json()[0]["id"], "m1")
        self.assertEqual(self.client.get("/api/clinical/labs").json()[0]["id"], "l1")
        self.assertEqual(self.client.get("/api/clinical/vitals").json()[0]["id"], "v1")
        self.assertEqual(self.client.get("/api/clinical/encounters").json()[0]["id"], "e1")


if __name__ == "__main__":
    unittest.main()
