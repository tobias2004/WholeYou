import unittest

from data_sources.clinical.service import ClinicalDataService


class ClinicalDataServiceTests(unittest.TestCase):
    def test_returns_empty_disconnected_summary_without_session_data(self):
        service = ClinicalDataService(session_data={})

        summary = service.get_clinical_summary("local")

        self.assertFalse(summary["connected"])
        self.assertEqual(summary["conditions"], [])
        self.assertEqual(summary["medications"], [])
        self.assertEqual(summary["labs"], [])
        self.assertEqual(summary["vitals"], [])
        self.assertEqual(summary["encounters"], [])

    def test_returns_slices_from_epic_backed_summary(self):
        service = ClinicalDataService(
            session_data={
                "clinical_summary": {
                    "connected": True,
                    "conditions": [{"id": "c1", "source": "epic"}],
                    "medications": [{"id": "m1", "source": "epic"}],
                    "labs": [{"id": "l1", "source": "epic"}],
                    "vitals": [{"id": "v1", "source": "epic"}],
                    "encounters": [{"id": "e1", "source": "epic"}],
                    "generatedAt": "2026-05-02T00:00:00Z",
                }
            }
        )

        self.assertEqual(service.get_conditions("local"), [{"id": "c1", "source": "epic"}])
        self.assertEqual(service.get_medications("local"), [{"id": "m1", "source": "epic"}])
        self.assertEqual(service.get_labs("local"), [{"id": "l1", "source": "epic"}])
        self.assertEqual(service.get_vitals("local"), [{"id": "v1", "source": "epic"}])
        self.assertEqual(service.get_encounters("local"), [{"id": "e1", "source": "epic"}])


if __name__ == "__main__":
    unittest.main()
