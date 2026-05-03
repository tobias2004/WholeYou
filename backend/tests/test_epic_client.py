import unittest

from config import EPIC_SCOPES
from integrations.epic.client import (
    attach_binary_resources_to_documents,
    build_patient_record_queries,
    binary_read_url_from_attachment_url,
    resources_from_fhir_response_pages,
)
from integrations.epic.fhir_models import parse_fhir_resource


class EpicClientTests(unittest.TestCase):
    def test_resources_from_fhir_response_pages_keeps_raw_pages_separate(self):
        pages = [
            {
                "resourceType": "Bundle",
                "entry": [
                    {"resource": {"resourceType": "Observation", "id": "obs-1"}},
                    {"resource": {"resourceType": "OperationOutcome", "issue": []}},
                ],
            },
            {"resourceType": "Bundle", "entry": [{"resource": {"resourceType": "Observation", "id": "obs-2"}}]},
        ]

        resources = resources_from_fhir_response_pages(pages)

        self.assertEqual(resources[0]["id"], "obs-1")
        self.assertEqual(resources[1]["resourceType"], "OperationOutcome")
        self.assertEqual(resources[2]["id"], "obs-2")
        self.assertEqual(pages[0]["entry"][0]["resource"]["id"], "obs-1")

    def test_build_patient_record_queries_includes_selected_epic_api_surfaces(self):
        queries = build_patient_record_queries("patient-123")

        expected_keys = {
            "allergies_patient_chart",
            "allergies_outside_record",
            "care_plans_encounter",
            "care_plans_longitudinal",
            "care_plans_outside_record",
            "care_teams_longitudinal",
            "care_teams_outside_record",
            "conditions_encounter_diagnosis",
            "conditions_health_concerns",
            "conditions_problems",
            "conditions_outside_record_encounter_diagnosis",
            "conditions_outside_record_health_concerns",
            "conditions_outside_record_problems",
            "diagnostic_reports_results",
            "diagnostic_reports_outside_record_results",
            "documents_clinical_notes",
            "documents_labs",
            "documents_outside_record_clinical_notes",
            "encounters_patient_chart",
            "encounters_outside_record",
            "goals_patient",
            "goals_outside_record",
            "goals_care_plan_goal",
            "immunizations_patient_chart",
            "observations_assessments",
            "observations_labs",
            "observations_sdoh_assessments",
            "observations_social_history",
            "observations_vital_signs",
            "observations_outside_record_activities_of_daily_living",
            "observations_outside_record_occupation",
            "observations_outside_record_pregnancy_status",
            "observations_outside_record_results",
            "observations_outside_record_screening_assessment",
            "observations_outside_record_sdoh_assessment",
            "observations_outside_record_sexual_orientation",
            "observations_outside_record_smoking_status",
            "observations_outside_record_vital_signs",
            "observations_smartdata_elements",
            "procedures_orders",
            "procedures_surgeries",
            "procedures_outside_record",
            "procedures_sdoh_intervention",
            "medication_requests_signed_order",
            "medication_requests_outside_record",
            "medication_dispenses_fill_status",
            "medication_dispenses_outside_record",
            "medications_outside_record",
            "devices_implants",
            "devices_outside_record",
            "coverage_outside_record",
            "coverage_patient_insurance",
        }

        self.assertEqual(set(queries), expected_keys)
        self.assertEqual(queries["observations_labs"].params["category"], "laboratory")
        self.assertEqual(queries["observations_vital_signs"].params["category"], "vital-signs")
        self.assertEqual(queries["observations_social_history"].params["category"], "social-history")

    def test_epic_scopes_cover_expanded_patient_record_resources(self):
        expected_scopes = {
            "patient/AllergyIntolerance.read",
            "patient/Binary.read",
            "patient/CarePlan.read",
            "patient/CareTeam.read",
            "patient/Condition.read",
            "patient/Coverage.read",
            "patient/Device.read",
            "patient/DiagnosticReport.read",
            "patient/DocumentReference.read",
            "patient/Encounter.read",
            "patient/Goal.read",
            "patient/Immunization.read",
            "patient/Medication.read",
            "patient/MedicationDispense.read",
            "patient/MedicationRequest.read",
            "patient/Observation.read",
            "patient/Patient.read",
            "patient/Procedure.read",
        }

        self.assertTrue(expected_scopes.issubset(set(EPIC_SCOPES)))

    def test_parse_fhir_resource_returns_python_model_without_normalizing_fields(self):
        patient = {
            "resourceType": "Patient",
            "id": "patient-123",
            "active": True,
            "name": [{"text": "Test Patient"}],
        }

        parsed = parse_fhir_resource(patient)

        self.assertEqual(parsed.get_resource_type(), "Patient")
        self.assertEqual(parsed.model_dump()["id"], "patient-123")
        self.assertEqual(parsed.model_dump()["name"][0]["text"], "Test Patient")

    def test_binary_read_url_from_attachment_url_accepts_relative_and_absolute_binary_urls(self):
        self.assertEqual(
            binary_read_url_from_attachment_url("Binary/note-1"),
            "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4/Binary/note-1",
        )
        self.assertEqual(
            binary_read_url_from_attachment_url(
                "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4/Binary/note-2"
            ),
            "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4/Binary/note-2",
        )
        self.assertIsNone(binary_read_url_from_attachment_url("https://example.com/file.pdf"))

    def test_attach_binary_resources_to_documents_stores_binary_in_contained_resources(self):
        class FakeResponse:
            status_code = 200

            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        class FakeClient:
            def __init__(self):
                self.urls = []

            async def get(self, url, headers):
                self.urls.append(url)
                return FakeResponse(
                    {
                        "resourceType": "Binary",
                        "id": "note-1",
                        "contentType": "text/plain",
                        "data": "SGVsbG8=",
                    }
                )

        documents = [
            {
                "resourceType": "DocumentReference",
                "id": "doc-1",
                "status": "current",
                "content": [{"attachment": {"url": "Binary/note-1"}}],
            }
        ]

        import asyncio

        count = asyncio.run(
            attach_binary_resources_to_documents(FakeClient(), documents, {})
        )

        self.assertEqual(count, 1)
        self.assertEqual(documents[0]["contained"][0]["resourceType"], "Binary")
        self.assertEqual(documents[0]["contained"][0]["data"], "SGVsbG8=")
        parsed = parse_fhir_resource(documents[0])
        self.assertEqual(parsed.contained[0].get_resource_type(), "Binary")


if __name__ == "__main__":
    unittest.main()
