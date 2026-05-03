import unittest

from fastapi.testclient import TestClient

from integrations.epic.oauth import frontend_redirect
from integrations.epic.fhir_models import parse_fhir_resource
from integrations.epic.routes import compact_epic_raw_for_browser
from main import app
from session_store import SESSION_DATA


class EpicRoutesTests(unittest.TestCase):
    def setUp(self):
        SESSION_DATA.clear()
        self.client = TestClient(app)

    def tearDown(self):
        SESSION_DATA.clear()

    def test_raw_route_serializes_fhir_models_without_null_schema_fields(self):
        SESSION_DATA["raw"] = {
            "patient": parse_fhir_resource(
                {
                    "resourceType": "Patient",
                    "id": "patient-123",
                    "active": True,
                    "name": [{"text": "Test Patient"}],
                }
            )
        }

        response = self.client.get("/api/epic/raw")

        self.assertEqual(response.status_code, 200)
        patient = response.json()["patient"]
        self.assertEqual(patient["resourceType"], "Patient")
        self.assertEqual(patient["id"], "patient-123")
        self.assertEqual(patient["name"][0]["text"], "Test Patient")
        self.assertNotIn("meta", patient)
        self.assertNotIn("implicitRules", patient)
        self.assertNotIn("family", patient["name"][0])

    def test_epic_logout_clears_only_epic_session_state(self):
        SESSION_DATA.update(
            {
                "token": {"patient": "patient-123"},
                "state": "state-1",
                "code_verifier": "verifier-1",
                "raw": {"patient": {"resourceType": "Patient", "id": "patient-123"}},
                "summary": {"patient": {"id": "patient-123"}},
                "clinical_summary": {"connected": True},
                "open_wearables_user_ids": {"local": "ow-user-1"},
                "connections": {"ow-user-1": [{"provider": "oura"}]},
            }
        )

        response = self.client.post("/api/epic/logout")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        self.assertNotIn("token", SESSION_DATA)
        self.assertNotIn("raw", SESSION_DATA)
        self.assertEqual(SESSION_DATA["open_wearables_user_ids"], {"local": "ow-user-1"})
        self.assertEqual(SESSION_DATA["connections"], {"ow-user-1": [{"provider": "oura"}]})

    def test_epic_clear_data_keeps_token_metadata_and_other_session_state(self):
        SESSION_DATA.update(
            {
                "token": {"patient": "patient-123"},
                "raw": {"patient": {"resourceType": "Patient", "id": "patient-123"}},
                "summary": {"patient": {"id": "patient-123"}},
                "clinical_summary": {"connected": True},
                "open_wearables_user_ids": {"local": "ow-user-1"},
            }
        )

        response = self.client.delete("/api/epic/data")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        self.assertEqual(SESSION_DATA["token"], {"patient": "patient-123"})
        self.assertNotIn("raw", SESSION_DATA)
        self.assertNotIn("summary", SESSION_DATA)
        self.assertNotIn("clinical_summary", SESSION_DATA)
        self.assertEqual(SESSION_DATA["open_wearables_user_ids"], {"local": "ow-user-1"})

    def test_epic_frontend_redirect_targets_homepage(self):
        response = frontend_redirect("/")

        self.assertIn("http://localhost:3000/", response.body.decode())
        self.assertNotIn("/dashboard", response.body.decode())

    def test_compact_raw_removes_empty_arrays_and_reduces_bundle_entries_to_non_outcome_resources(self):
        raw = {
            "patient": parse_fhir_resource(
                {
                    "resourceType": "Patient",
                    "id": "patient-123",
                    "name": [{"text": "Test Patient"}],
                }
            ),
            "care_plans_encounter": [],
            "allergies_patient_chart": [
                parse_fhir_resource(
                    {
                        "resourceType": "Bundle",
                        "type": "searchset",
                        "entry": [
                            {
                                "resource": {
                                    "resourceType": "AllergyIntolerance",
                                    "id": "allergy-1",
                                    "patient": {"reference": "Patient/patient-123"},
                                    "clinicalStatus": {
                                        "coding": [{"code": "active"}]
                                    },
                                }
                            },
                            {
                                "resource": {
                                    "resourceType": "OperationOutcome",
                                    "issue": [{"severity": "warning", "code": "processing"}],
                                }
                            },
                        ],
                    }
                )
            ],
        }

        compact = compact_epic_raw_for_browser(raw)

        self.assertEqual(compact["patient"]["id"], "patient-123")
        self.assertNotIn("care_plans_encounter", compact)
        self.assertEqual(
            compact["allergies_patient_chart"],
            [
                {
                    "resourceType": "AllergyIntolerance",
                    "id": "allergy-1",
                    "patient": {"reference": "Patient/patient-123"},
                    "clinicalStatus": {"coding": [{"code": "active"}]},
                },
            ],
        )

    def test_compact_raw_removes_categories_that_only_contain_operation_outcomes(self):
        raw = {
            "patient": {"resourceType": "Patient", "id": "patient-123"},
            "conditions_genomics": [
                {
                    "resourceType": "Bundle",
                    "type": "searchset",
                    "entry": [
                        {
                            "resource": {
                                "resourceType": "OperationOutcome",
                                "issue": [{"severity": "warning", "code": "processing"}],
                            }
                        }
                    ],
                }
            ],
        }

        compact = compact_epic_raw_for_browser(raw)

        self.assertEqual(compact["patient"]["id"], "patient-123")
        self.assertNotIn("conditions_genomics", compact)


if __name__ == "__main__":
    unittest.main()
