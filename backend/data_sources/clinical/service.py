from typing import Any


class ClinicalDataService:
    def __init__(self, session_data: dict[str, Any]):
        self._session_data = session_data

    def get_clinical_summary(self, user_id: str) -> dict[str, Any]:
        del user_id
        summary = self._session_data.get("clinical_summary")
        if summary:
            return summary
        return {
            "connected": False,
            "message": "No Epic/MyChart sandbox data connected yet.",
            "conditions": [],
            "medications": [],
            "labs": [],
            "vitals": [],
            "encounters": [],
            "generatedAt": None,
        }

    def get_conditions(self, user_id: str) -> list[dict[str, Any]]:
        return self.get_clinical_summary(user_id).get("conditions", [])

    def get_medications(self, user_id: str) -> list[dict[str, Any]]:
        return self.get_clinical_summary(user_id).get("medications", [])

    def get_labs(self, user_id: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        del filters
        return self.get_clinical_summary(user_id).get("labs", [])

    def get_vitals(self, user_id: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        del filters
        return self.get_clinical_summary(user_id).get("vitals", [])

    def get_encounters(self, user_id: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        del filters
        return self.get_clinical_summary(user_id).get("encounters", [])
