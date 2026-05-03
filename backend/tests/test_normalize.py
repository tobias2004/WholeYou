import unittest

from normalize import (
    normalize_condition,
    normalize_medication_request,
    normalize_observation,
    normalize_patient,
)


class NormalizeTests(unittest.TestCase):
    def test_normalize_patient_uses_human_name_parts(self):
        patient = {
            "id": "pat-123",
            "name": [{"given": ["Jane", "Q"], "family": "Public"}],
            "birthDate": "1980-01-01",
            "gender": "female",
        }

        self.assertEqual(
            normalize_patient(patient),
            {
                "id": "pat-123",
                "name": "Jane Q Public",
                "birthDate": "1980-01-01",
                "gender": "female",
            },
        )

    def test_normalize_observation_handles_quantity_and_interpretation(self):
        observation = {
            "id": "obs-1",
            "status": "final",
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": "4548-4",
                        "display": "Hemoglobin A1c",
                    }
                ]
            },
            "valueQuantity": {"value": 6.4, "unit": "%"},
            "effectiveDateTime": "2026-04-01",
            "interpretation": [{"coding": [{"code": "H", "display": "High"}]}],
        }

        self.assertEqual(
            normalize_observation(observation),
            {
                "id": "obs-1",
                "name": "Hemoglobin A1c",
                "value": 6.4,
                "unit": "%",
                "date": "2026-04-01",
                "status": "final",
                "code": "4548-4",
                "codeSystem": "http://loinc.org",
                "flag": "high",
            },
        )

    def test_normalize_observation_handles_component_blood_pressure(self):
        observation = {
            "id": "bp-1",
            "status": "final",
            "code": {"text": "Blood Pressure"},
            "effectiveDateTime": "2026-04-01T10:00:00Z",
            "component": [
                {
                    "code": {
                        "coding": [
                            {"code": "8480-6", "display": "Systolic Blood Pressure"}
                        ]
                    },
                    "valueQuantity": {"value": 120, "unit": "mmHg"},
                },
                {
                    "code": {
                        "coding": [
                            {"code": "8462-4", "display": "Diastolic Blood Pressure"}
                        ]
                    },
                    "valueQuantity": {"value": 80, "unit": "mmHg"},
                },
            ],
        }

        result = normalize_observation(observation)

        self.assertEqual(result["name"], "Blood Pressure")
        self.assertEqual(result["value"], "120/80")
        self.assertEqual(result["unit"], "mmHg")
        self.assertEqual(result["date"], "2026-04-01T10:00:00Z")

    def test_normalize_condition_uses_status_codes_and_onset(self):
        condition = {
            "id": "cond-1",
            "code": {"coding": [{"display": "Type 2 diabetes mellitus"}]},
            "clinicalStatus": {"coding": [{"code": "active"}]},
            "verificationStatus": {"coding": [{"code": "confirmed"}]},
            "onsetDateTime": "2020-01-01",
        }

        self.assertEqual(
            normalize_condition(condition),
            {
                "id": "cond-1",
                "name": "Type 2 diabetes mellitus",
                "clinicalStatus": "active",
                "verificationStatus": "confirmed",
                "onsetDate": "2020-01-01",
            },
        )

    def test_normalize_medication_request_handles_codeable_concept_and_dosage(self):
        request = {
            "id": "med-1",
            "status": "active",
            "intent": "order",
            "medicationCodeableConcept": {
                "coding": [{"display": "Metformin 500 MG Oral Tablet"}]
            },
            "authoredOn": "2026-03-01",
            "dosageInstruction": [{"text": "Take 1 tablet by mouth twice daily"}],
        }

        self.assertEqual(
            normalize_medication_request(request),
            {
                "id": "med-1",
                "name": "Metformin 500 MG Oral Tablet",
                "status": "active",
                "intent": "order",
                "authoredOn": "2026-03-01",
                "dosageText": "Take 1 tablet by mouth twice daily",
            },
        )


if __name__ == "__main__":
    unittest.main()
