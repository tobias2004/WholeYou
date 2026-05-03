import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode
from xml.etree import ElementTree

import httpx

from config import (
    STRAVA_API_BASE_URL,
    STRAVA_AUTHORIZE_URL,
    STRAVA_CLIENT_ID,
    STRAVA_CLIENT_SECRET,
    STRAVA_REDIRECT_URI,
    STRAVA_TOKEN_URL,
)
from integrations.open_wearables.scores import calculate_resilience_score, calculate_sleep_score

PROVIDER_PROFILES: dict[str, dict[str, Any]] = {
    "synthetic": {
        "workouts": True,
        "sleep": True,
        "timeseries": ["heart_rate", "steps", "oxygen_saturation"],
    },
    "garmin": {
        "workouts": True,
        "sleep": True,
        "timeseries": [
            "heart_rate",
            "steps",
            "energy",
            "oxygen_saturation",
            "heart_rate_variability_rmssd",
            "garmin_stress_level",
            "garmin_body_battery",
        ],
    },
    "suunto": {
        "workouts": True,
        "sleep": True,
        "timeseries": ["heart_rate", "steps", "energy", "oxygen_saturation", "heart_rate_variability_rmssd"],
    },
    "oura": {
        "workouts": True,
        "sleep": True,
        "timeseries": ["heart_rate", "steps", "energy", "oxygen_saturation", "vo2_max"],
    },
    "whoop": {
        "workouts": True,
        "sleep": True,
        "timeseries": [],
    },
    "ultrahuman": {
        "workouts": False,
        "sleep": True,
        "timeseries": ["heart_rate", "steps", "heart_rate_variability_sdnn", "skin_temperature", "vo2_max"],
    },
    "strava": {
        "workouts": True,
        "sleep": False,
        "timeseries": [],
    },
    "polar": {
        "workouts": True,
        "sleep": False,
        "timeseries": [],
    },
    "fitbit": {
        "workouts": True,
        "sleep": True,
        "timeseries": ["heart_rate", "steps", "energy"],
    },
    "withings": {
        "workouts": False,
        "sleep": True,
        "timeseries": ["weight", "body_fat_percentage", "heart_rate"],
    },
}

TIMESERIES_UNITS = {
    "heart_rate": "bpm",
    "resting_heart_rate": "bpm",
    "heart_rate_variability_sdnn": "ms",
    "heart_rate_variability_rmssd": "ms",
    "oxygen_saturation": "%",
    "steps": "count",
    "energy": "kcal",
    "skin_temperature": "°C",
    "vo2_max": "mL/kg/min",
    "garmin_stress_level": "score",
    "garmin_body_battery": "%",
    "weight": "kg",
    "body_fat_percentage": "%",
}

APPLE_RECORD_TYPES = {
    "HKQuantityTypeIdentifierHeartRate": ("heart_rate", "bpm"),
    "HKQuantityTypeIdentifierStepCount": ("steps", "count"),
    "HKQuantityTypeIdentifierDistanceWalkingRunning": ("distance_walking_running", "meters"),
    "HKQuantityTypeIdentifierActiveEnergyBurned": ("energy", "kcal"),
    "HKQuantityTypeIdentifierBodyMass": ("weight", "kg"),
    "HKQuantityTypeIdentifierBodyFatPercentage": ("body_fat_percentage", "%"),
    "HKQuantityTypeIdentifierOxygenSaturation": ("oxygen_saturation", "%"),
    "HKQuantityTypeIdentifierRespiratoryRate": ("respiratory_rate", "brpm"),
}

APPLE_WORKOUT_TYPES = {
    "HKWorkoutActivityTypeRunning": "running",
    "HKWorkoutActivityTypeWalking": "walking",
    "HKWorkoutActivityTypeCycling": "cycling",
    "HKWorkoutActivityTypeSwimming": "swimming",
    "HKWorkoutActivityTypeTraditionalStrengthTraining": "strength_training",
}

APPLE_SLEEP_STAGES = {
    "HKCategoryValueSleepAnalysisAsleepCore": "light",
    "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "rem",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "asleep",
    "HKCategoryValueSleepAnalysisAwake": "awake",
    "HKCategoryValueSleepAnalysisInBed": "in_bed",
}


class OpenWearablesClientError(RuntimeError):
    pass


class OpenWearablesNotAvailable(OpenWearablesClientError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class OpenWearablesBackend:
    """Minimal in-process wearable backend for the local WholeYou MVP."""

    def __init__(
        self,
        store: dict[str, Any],
        *,
        strava_client_id: str = STRAVA_CLIENT_ID,
        strava_client_secret: str = STRAVA_CLIENT_SECRET,
        strava_redirect_uri: str = STRAVA_REDIRECT_URI,
        strava_authorize_url: str = STRAVA_AUTHORIZE_URL,
        strava_token_url: str = STRAVA_TOKEN_URL,
        strava_api_base_url: str = STRAVA_API_BASE_URL,
    ):
        self._strava_client_id = strava_client_id
        self._strava_client_secret = strava_client_secret
        self._strava_redirect_uri = strava_redirect_uri
        self._strava_authorize_url = strava_authorize_url
        self._strava_token_url = strava_token_url
        self._strava_api_base_url = strava_api_base_url.rstrip("/")
        self._state = store.setdefault(
            "open_wearables",
            {
                "users": {},
                "connections": {},
                "timeseries": {},
                "workouts": {},
                "sleep": {},
                "health_scores": {},
                "data_sources": {},
                "syncs": {},
                "oauth_states": {},
                "provider_tokens": {},
            },
        )

    @property
    def configured(self) -> bool:
        return True

    @property
    def seed_configured(self) -> bool:
        return True

    async def get_users(self, params: dict[str, Any] | None = None) -> Any:
        users = list(self._state["users"].values())
        external_user_id = (params or {}).get("external_user_id")
        if external_user_id:
            users = [user for user in users if user.get("external_user_id") == external_user_id]
        return {"items": users}

    async def create_user(self, payload: dict[str, Any]) -> Any:
        external_user_id = payload.get("external_user_id")
        for user in self._state["users"].values():
            if external_user_id and user.get("external_user_id") == external_user_id:
                return user

        user_id = f"ow-local-{external_user_id or uuid.uuid4().hex[:8]}"
        user = {
            "id": user_id,
            "external_user_id": external_user_id,
            "email": payload.get("email"),
            "created_at": _now(),
        }
        self._state["users"][user_id] = user
        self._state["connections"].setdefault(user_id, [])
        self._state["timeseries"].setdefault(user_id, [])
        self._state["workouts"].setdefault(user_id, [])
        self._state["sleep"].setdefault(user_id, [])
        self._state["data_sources"].setdefault(user_id, [])
        return user

    async def get_providers(self) -> Any:
        return {
            "providers": [
                {"id": "oura", "name": "Oura", "type": "ring", "supports_oauth": True},
                {"id": "whoop", "name": "WHOOP", "type": "band", "supports_oauth": True},
                {"id": "garmin", "name": "Garmin", "type": "watch", "supports_oauth": True},
                {"id": "polar", "name": "Polar", "type": "watch", "supports_oauth": True},
                {"id": "suunto", "name": "Suunto", "type": "watch", "supports_oauth": True},
                {"id": "fitbit", "name": "Fitbit", "type": "watch", "supports_oauth": True},
                {"id": "withings", "name": "Withings", "type": "scale", "supports_oauth": True},
                {"id": "ultrahuman", "name": "Ultrahuman", "type": "ring", "supports_oauth": True},
                {"id": "strava", "name": "Strava", "type": "fitness", "supports_oauth": True},
                {
                    "id": "apple_health_xml",
                    "name": "Apple Health XML Import",
                    "type": "import",
                    "supports_import": True,
                },
            ]
        }

    async def get_authorization_url(
        self,
        provider: str,
        user_id: str,
        redirect_uri: str | None = None,
        mode: str = "synthetic",
    ) -> Any:
        self._ensure_user(user_id)
        if mode == "real":
            return self._build_real_authorization_url(provider, user_id, redirect_uri)

        self._populate_synthetic_records(user_id, random.Random(), provider=provider)
        return {
            "authorization_url": None,
            "state": f"synthetic-{provider}",
            "mode": "synthetic",
        }

    async def handle_oauth_callback(
        self,
        provider: str,
        *,
        code: str | None,
        state: str | None,
        error: str | None = None,
    ) -> dict[str, Any]:
        if error:
            raise OpenWearablesClientError(f"{provider} authorization failed: {error}")
        if provider != "strava":
            raise OpenWearablesClientError(f"Real OAuth is not implemented for {provider}")
        if not code or not state:
            raise OpenWearablesClientError("Missing Strava OAuth callback code or state")

        oauth_state = self._state["oauth_states"].pop(state, None)
        if not oauth_state or oauth_state.get("provider") != provider:
            raise OpenWearablesClientError("Invalid Strava OAuth state")

        user_id = oauth_state["user_id"]
        token_payload = await self._exchange_strava_code(code)
        access_token = token_payload.get("access_token")
        if not access_token:
            raise OpenWearablesClientError("Strava did not return an access token")

        self._state["provider_tokens"].setdefault(user_id, {})[provider] = {
            "access_token": access_token,
            "refresh_token": token_payload.get("refresh_token"),
            "expires_at": token_payload.get("expires_at"),
            "scope": token_payload.get("scope"),
        }

        athlete = token_payload.get("athlete") if isinstance(token_payload.get("athlete"), dict) else {}
        self._upsert_connection(
            user_id,
            {
                "provider": provider,
                "status": "connected",
                "provider_user_id": str(athlete.get("id") or ""),
                "scopes": str(token_payload.get("scope") or "").replace(",", " ").split(),
                "connected_at": _now(),
            },
        )
        self._ensure_data_source(user_id, provider)
        await self._import_strava_activities(user_id, access_token)
        return {"status": "connected", "provider": provider}

    async def get_connections(self, user_id: str) -> Any:
        self._ensure_user(user_id)
        return {"connections": self._state["connections"].setdefault(user_id, [])}

    async def delete_connection(self, user_id: str, provider: str) -> Any:
        self._ensure_user(user_id)
        self._state["connections"][user_id] = [
            connection
            for connection in self._state["connections"].setdefault(user_id, [])
            if connection.get("provider") != provider
        ]
        self._remove_provider_records(user_id, provider)
        self._state["provider_tokens"].setdefault(user_id, {}).pop(provider, None)
        return {"status": "disconnected", "provider": provider}

    async def clear_connections(self, user_id: str) -> dict[str, Any]:
        self._ensure_user(user_id)
        self._state["connections"][user_id] = []
        self._state["timeseries"][user_id] = []
        self._state["workouts"][user_id] = []
        self._state["sleep"][user_id] = []
        self._state["health_scores"][user_id] = []
        self._state["data_sources"][user_id] = []
        self._state["provider_tokens"][user_id] = {}
        return {"status": "cleared"}

    async def sync_user(self, user_id: str, payload: dict[str, Any] | None = None) -> Any:
        self._ensure_user(user_id)
        synced_at = _now()
        self._state["syncs"][user_id] = {"status": "completed", "synced_at": synced_at}
        for connection in self._state["connections"].setdefault(user_id, []):
            connection["last_synced_at"] = synced_at
        return {"status": "completed", "user_id": user_id, "synced_at": synced_at, **(payload or {})}

    async def sync_provider(
        self, provider: str, user_id: str, payload: dict[str, Any] | None = None
    ) -> Any:
        result = await self.sync_user(user_id, payload)
        result["provider"] = provider
        return result

    async def get_summary(self, user_id: str, summary_type: str) -> Any:
        self._ensure_user(user_id)
        if summary_type == "activity":
            steps = sum(
                int(point["value"])
                for point in self._state["timeseries"].setdefault(user_id, [])
                if point.get("type") == "steps"
            )
            return {"summaryType": "activity", "steps": steps, "workoutCount": len(self._state["workouts"][user_id])}
        if summary_type == "sleep":
            sleep_events = self._state["sleep"].setdefault(user_id, [])
            minutes = sum(float(event.get("duration_minutes") or 0) for event in sleep_events)
            return {"summaryType": "sleep", "durationMinutes": minutes, "sessionCount": len(sleep_events)}
        if summary_type == "body":
            return {"summaryType": "body", "weight": None, "bodyFatPercent": None}
        if summary_type == "data":
            return {
                "summaryType": "data",
                "dataSources": len(self._state["data_sources"].setdefault(user_id, [])),
                "timeseriesPoints": len(self._state["timeseries"].setdefault(user_id, [])),
            }
        return {"summaryType": summary_type}

    async def get_timeseries(self, user_id: str, params: dict[str, Any] | None = None) -> Any:
        self._ensure_user(user_id)
        points = list(self._state["timeseries"].setdefault(user_id, []))
        params = params or {}
        metric_type = params.get("types") or params.get("type")
        if metric_type:
            points = [point for point in points if point.get("type") == metric_type]
        limit = params.get("limit")
        if isinstance(limit, int):
            points = points[:limit]
        return {"items": points}

    async def get_workouts(self, user_id: str, params: dict[str, Any] | None = None) -> Any:
        self._ensure_user(user_id)
        workouts = list(self._state["workouts"].setdefault(user_id, []))
        limit = (params or {}).get("limit")
        if isinstance(limit, int):
            workouts = workouts[:limit]
        return {"items": workouts}

    async def get_sleep(self, user_id: str, params: dict[str, Any] | None = None) -> Any:
        self._ensure_user(user_id)
        sleep = list(self._state["sleep"].setdefault(user_id, []))
        limit = (params or {}).get("limit")
        if isinstance(limit, int):
            sleep = sleep[:limit]
        return {"items": sleep}

    async def compute_health_scores(self, user_id: str) -> dict[str, Any]:
        self._ensure_user(user_id)
        self._state["health_scores"][user_id] = []
        scores: list[dict[str, Any]] = []
        scores.extend(self._compute_internal_sleep_scores(user_id))
        resilience = self._compute_internal_resilience_score(user_id)
        if resilience:
            scores.append(resilience)
        scores.extend(self._compute_provider_native_scores(user_id))
        self._state["health_scores"][user_id] = scores
        return {"status": "computed", "scoresComputed": len(scores)}

    async def get_health_scores(self, user_id: str, params: dict[str, Any] | None = None) -> Any:
        self._ensure_user(user_id)
        scores = list(self._state["health_scores"].setdefault(user_id, []))
        params = params or {}
        category = params.get("category")
        provider = params.get("provider")
        if category:
            scores = [score for score in scores if score.get("category") == category]
        if provider:
            scores = [score for score in scores if score.get("provider") == provider]
        limit = params.get("limit")
        if isinstance(limit, int):
            scores = scores[:limit]
        return {"items": scores}

    async def get_data_sources(self, user_id: str) -> Any:
        self._ensure_user(user_id)
        return {"dataSources": self._state["data_sources"].setdefault(user_id, [])}

    async def create_apple_health_upload_url(self, user_id: str, payload: dict[str, Any]) -> Any:
        del payload
        self._ensure_user(user_id)
        return {
            "status": "not_implemented",
            "message": "Apple Health XML upload URL generation needs database-backed file storage.",
        }

    async def import_apple_health_xml_direct(
        self,
        user_id: str,
        payload: dict[str, Any] | None = None,
        *,
        filename: str = "",
        content: bytes = b"",
    ) -> Any:
        payload = payload or {}
        return await self.import_apple_health_xml_file(
            user_id,
            filename=str(filename or payload.get("filename") or ""),
            content=content or payload.get("content") or b"",
        )

    async def import_apple_health_xml_file(
        self,
        user_id: str,
        *,
        filename: str,
        content: bytes,
    ) -> dict[str, Any]:
        self._ensure_user(user_id)
        if not filename.lower().endswith(".xml"):
            raise OpenWearablesClientError("Apple Health import requires an .xml file")
        try:
            root = ElementTree.fromstring(content)
        except ElementTree.ParseError as exc:
            raise OpenWearablesClientError("Apple Health XML could not be parsed") from exc
        if root.tag != "HealthData":
            raise OpenWearablesClientError("Apple Health XML root must be HealthData")

        provider = "apple_health_xml"
        self._upsert_connection(
            user_id,
            {
                "provider": provider,
                "status": "connected",
                "provider_user_id": "apple-health-export",
                "scopes": ["timeseries", "sleep", "activity"],
                "connected_at": _now(),
                "last_synced_at": _now(),
            },
        )
        self._remove_provider_records(user_id, provider)
        self._ensure_data_source(user_id, provider)

        timeseries_count = self._import_apple_records(user_id, root)
        workouts_count = self._import_apple_workouts(user_id, root)
        sleep_count = self._import_apple_sleep(user_id, root)

        return {
            "status": "imported",
            "provider": provider,
            "timeseriesImported": timeseries_count,
            "workoutsImported": workouts_count,
            "sleepImported": sleep_count,
        }

    async def get_seed_presets(self) -> Any:
        return [
            {
                "id": "minimal",
                "label": "Minimal",
                "description": "Small synthetic local dataset.",
                "profile": {"preset": "minimal"},
            }
        ]

    async def get_seed_sleep_profiles(self) -> Any:
        return [{"id": "typical", "label": "Typical sleep"}]

    async def generate_seed_data(self, payload: dict[str, Any]) -> Any:
        seed = payload.get("random_seed")
        rng = random.Random(seed)
        users = list(self._state["users"].values())
        if not users:
            users = [await self.create_user({"external_user_id": "local", "email": "local@wholeyou.test"})]

        for user in users:
            self._populate_synthetic_records(user["id"], rng, provider="synthetic")
        return {
            "task_id": f"local-seed-{uuid.uuid4().hex[:8]}",
            "status": "completed",
            "seed_used": seed,
        }

    def _ensure_user(self, user_id: str) -> None:
        if user_id not in self._state["users"]:
            self._state["users"][user_id] = {
                "id": user_id,
                "external_user_id": user_id,
                "created_at": _now(),
            }
        self._state["connections"].setdefault(user_id, [])
        self._state["timeseries"].setdefault(user_id, [])
        self._state["workouts"].setdefault(user_id, [])
        self._state["sleep"].setdefault(user_id, [])
        self._state.setdefault("health_scores", {}).setdefault(user_id, [])
        self._state["data_sources"].setdefault(user_id, [])
        self._state["provider_tokens"].setdefault(user_id, {})

    def _upsert_connection(self, user_id: str, connection: dict[str, Any]) -> None:
        connections = self._state["connections"].setdefault(user_id, [])
        connections[:] = [
            item for item in connections if item.get("provider") != connection.get("provider")
        ]
        connections.append(connection)

    def _ensure_data_source(self, user_id: str, provider: str) -> None:
        sources = self._state["data_sources"].setdefault(user_id, [])
        if not any(source.get("provider") == provider for source in sources):
            sources.append(
                {
                    "id": f"{provider}-local-source",
                    "provider": provider,
                    "device": f"{provider.title()} demo device",
                    "device_type": "synthetic",
                    "status": "active",
                }
            )

    def _populate_synthetic_records(
        self, user_id: str, rng: random.Random, provider: str
    ) -> None:
        self._ensure_user(user_id)
        profile = PROVIDER_PROFILES.get(provider, PROVIDER_PROFILES["synthetic"])
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        self._upsert_connection(
            user_id,
            {
                "provider": provider,
                "status": "connected",
                "provider_user_id": f"{provider}-synthetic-user",
                "scopes": self._synthetic_scopes(profile),
                "connected_at": _now(),
                "last_synced_at": _now(),
            },
        )
        self._ensure_data_source(user_id, provider)
        self._remove_provider_records(user_id, provider)
        for metric_type in profile["timeseries"]:
            self._append_synthetic_timeseries(user_id, provider, metric_type, rng, now)
        if profile["workouts"]:
            self._append_synthetic_workouts(user_id, provider, rng, now)
        if profile["sleep"]:
            self._append_synthetic_sleep(user_id, provider, rng, now)

    def _synthetic_scopes(self, profile: dict[str, Any]) -> list[str]:
        scopes = []
        if profile.get("workouts"):
            scopes.append("activity")
        if profile.get("sleep"):
            scopes.append("sleep")
        if profile.get("timeseries"):
            scopes.append("timeseries")
        return scopes

    def _append_synthetic_timeseries(
        self,
        user_id: str,
        provider: str,
        metric_type: str,
        rng: random.Random,
        now: datetime,
    ) -> None:
        sample_count = rng.randint(12, 48)
        if metric_type in {"heart_rate_variability_rmssd", "heart_rate_variability_sdnn"}:
            sample_count = max(sample_count, 7)
        for offset in range(sample_count):
            delta = timedelta(days=offset) if metric_type in {
                "heart_rate_variability_rmssd",
                "heart_rate_variability_sdnn",
            } else timedelta(hours=offset)
            timestamp = (now - delta).isoformat().replace("+00:00", "Z")
            self._state["timeseries"][user_id].append(
                {
                    "timestamp": timestamp,
                    "type": metric_type,
                    "value": self._synthetic_value(metric_type, rng, offset),
                    "unit": TIMESERIES_UNITS.get(metric_type),
                    "provider": provider,
                    "device": f"{provider.title()} synthetic wearable",
                    "device_type": self._device_type(provider),
                }
            )

    def _synthetic_value(self, metric_type: str, rng: random.Random, offset: int) -> float | int:
        if metric_type == "heart_rate":
            return rng.randint(55, 105)
        if metric_type == "steps":
            return rng.randint(0, 1800) if 7 <= (offset % 24) <= 22 else rng.randint(0, 120)
        if metric_type == "energy":
            return round(rng.uniform(12, 95), 1)
        if metric_type == "oxygen_saturation":
            return round(rng.uniform(94, 99), 1)
        if metric_type == "heart_rate_variability_sdnn":
            return round(rng.uniform(35, 95), 1)
        if metric_type == "heart_rate_variability_rmssd":
            return round(rng.uniform(25, 85), 1)
        if metric_type == "skin_temperature":
            return round(rng.uniform(30.5, 35.5), 1)
        if metric_type == "vo2_max":
            return round(rng.uniform(32, 54), 1)
        if metric_type == "garmin_stress_level":
            return rng.randint(10, 80)
        if metric_type == "garmin_body_battery":
            return rng.randint(15, 100)
        if metric_type == "weight":
            return round(rng.uniform(62, 92), 1)
        if metric_type == "body_fat_percentage":
            return round(rng.uniform(14, 28), 1)
        return rng.randint(1, 100)

    def _append_synthetic_workouts(
        self,
        user_id: str,
        provider: str,
        rng: random.Random,
        now: datetime,
    ) -> None:
        workout_types = ["run", "ride", "walk", "strength_training"]
        workout_count = rng.randint(3, 6)
        type_offset = rng.randint(0, len(workout_types) - 1)
        for index in range(workout_count):
            duration = rng.randint(28, 74)
            workout_start = now - timedelta(days=index + 1, hours=rng.randint(1, 5))
            workout_type = workout_types[(type_offset + index) % len(workout_types)]
            distance = 0 if workout_type == "strength_training" else round(rng.uniform(2.2, 24.0), 2)
            self._state["workouts"][user_id].append(
                {
                    "id": f"{provider}-synthetic-workout-{index + 1}",
                    "type": workout_type,
                    "start_time": workout_start.isoformat().replace("+00:00", "Z"),
                    "end_time": (workout_start + timedelta(minutes=duration)).isoformat().replace("+00:00", "Z"),
                    "duration_minutes": duration,
                    "calories": rng.randint(160, 780),
                    "distance": distance,
                    "average_heart_rate": rng.randint(105, 158),
                    "provider": provider,
                    "device": f"{provider.title()} synthetic device",
                }
            )

    def _append_synthetic_sleep(
        self,
        user_id: str,
        provider: str,
        rng: random.Random,
        now: datetime,
    ) -> None:
        for index in range(rng.randint(2, 7)):
            duration = rng.randint(385, 505)
            sleep_start = now - timedelta(days=index, hours=9, minutes=rng.randint(0, 45))
            deep = rng.randint(55, 105)
            rem = rng.randint(70, 125)
            awake = rng.randint(8, 35)
            light = max(duration - deep - rem - awake, 120)
            self._state["sleep"][user_id].append(
                {
                    "id": f"{provider}-synthetic-sleep-{index + 1}",
                    "start_time": sleep_start.isoformat().replace("+00:00", "Z"),
                    "end_time": (sleep_start + timedelta(minutes=duration)).isoformat().replace("+00:00", "Z"),
                    "duration_minutes": duration,
                    "efficiency_percent": round((duration - awake) / duration * 100, 1),
                    "stages": [
                        {"stage": "deep", "minutes": deep},
                        {"stage": "rem", "minutes": rem},
                        {"stage": "light", "minutes": light},
                        {"stage": "awake", "minutes": awake},
                    ],
                    "interruptions": rng.randint(1, 5),
                    "provider": provider,
                }
            )

    def _device_type(self, provider: str) -> str:
        if provider in {"oura", "ultrahuman"}:
            return "ring"
        if provider == "withings":
            return "scale"
        return "watch"

    def _remove_provider_records(self, user_id: str, provider: str) -> None:
        self._state["timeseries"][user_id] = [
            item for item in self._state["timeseries"].setdefault(user_id, [])
            if item.get("provider") != provider
        ]
        self._state["workouts"][user_id] = [
            item for item in self._state["workouts"].setdefault(user_id, [])
            if item.get("provider") != provider
        ]
        self._state["sleep"][user_id] = [
            item for item in self._state["sleep"].setdefault(user_id, [])
            if item.get("provider") != provider
        ]
        self._state["health_scores"][user_id] = [
            item for item in self._state.setdefault("health_scores", {}).setdefault(user_id, [])
            if item.get("provider") not in {provider, "internal"}
        ]
        self._state["data_sources"][user_id] = [
            item for item in self._state["data_sources"].setdefault(user_id, [])
            if item.get("provider") != provider
        ]

    def _compute_internal_sleep_scores(self, user_id: str) -> list[dict[str, Any]]:
        sleep_events = sorted(
            self._state["sleep"].setdefault(user_id, []),
            key=lambda event: event.get("start_time") or "",
        )
        scores = []
        for index, sleep_event in enumerate(sleep_events):
            result = calculate_sleep_score(sleep_event, sleep_events[max(0, index - 14):index])
            if not result:
                continue
            scores.append(
                self._health_score(
                    provider="internal",
                    category="sleep",
                    value=result.overall_score,
                    recorded_at=sleep_event.get("end_time") or sleep_event.get("start_time") or _now(),
                    components=result.components,
                    data_source_id=None,
                    related_record_id=sleep_event.get("id"),
                )
            )
        return scores

    def _compute_internal_resilience_score(self, user_id: str) -> dict[str, Any] | None:
        result = calculate_resilience_score(self._state["timeseries"].setdefault(user_id, []))
        if not result:
            return None
        return self._health_score(
            provider="internal",
            category="resilience",
            value=result.hrv_cv,
            recorded_at=_now(),
            components={
                "days_counted": {"value": result.days_counted},
                "metric_type": {"qualifier": result.metric_type},
                "resilience_score": {"value": result.resilience_score},
            },
            data_source_id=None,
        )

    def _compute_provider_native_scores(self, user_id: str) -> list[dict[str, Any]]:
        connected_providers = {
            connection.get("provider")
            for connection in self._state["connections"].setdefault(user_id, [])
            if connection.get("provider")
        }
        scores: list[dict[str, Any]] = []
        for provider in sorted(connected_providers):
            scores.extend(self._provider_sleep_scores(user_id, provider))
            if provider == "garmin":
                scores.extend(self._garmin_native_scores(user_id))
            elif provider == "whoop":
                scores.extend(self._whoop_native_scores(user_id))
            elif provider == "oura":
                scores.extend(self._oura_native_scores(user_id))
        return scores

    def _provider_sleep_scores(self, user_id: str, provider: str) -> list[dict[str, Any]]:
        scores = []
        for sleep_event in self._state["sleep"].setdefault(user_id, []):
            if sleep_event.get("provider") != provider:
                continue
            value = self._sleep_native_value(sleep_event)
            if value is None:
                continue
            scores.append(
                self._health_score(
                    provider=provider,
                    category="sleep",
                    value=value,
                    qualifier=self._qualifier(value),
                    recorded_at=sleep_event.get("end_time") or _now(),
                    components={"efficiency": {"value": sleep_event.get("efficiency_percent")}},
                    related_record_id=sleep_event.get("id"),
                )
            )
        return scores[:1]

    def _garmin_native_scores(self, user_id: str) -> list[dict[str, Any]]:
        scores = []
        for metric_type, category in (
            ("garmin_body_battery", "body_battery"),
            ("garmin_stress_level", "stress"),
        ):
            point = self._latest_point(user_id, "garmin", metric_type)
            if point:
                scores.append(
                    self._health_score(
                        provider="garmin",
                        category=category,
                        value=point.get("value"),
                        qualifier=self._qualifier(point.get("value")),
                        recorded_at=point.get("timestamp") or _now(),
                    )
                )
        return scores

    def _whoop_native_scores(self, user_id: str) -> list[dict[str, Any]]:
        scores = []
        latest_sleep = self._latest_sleep(user_id, "whoop")
        if latest_sleep:
            recovery = self._sleep_native_value(latest_sleep)
            if recovery is not None:
                scores.append(
                    self._health_score(
                        provider="whoop",
                        category="recovery",
                        value=recovery,
                        qualifier=self._qualifier(recovery),
                        recorded_at=latest_sleep.get("end_time") or _now(),
                    )
                )
        latest_workout = self._latest_workout(user_id, "whoop")
        if latest_workout:
            strain = min(21.0, round((float(latest_workout.get("duration_minutes") or 0) / 74.0) * 21.0, 1))
            scores.append(
                self._health_score(
                    provider="whoop",
                    category="strain",
                    value=strain,
                    qualifier="high" if strain >= 14 else "moderate",
                    recorded_at=latest_workout.get("end_time") or _now(),
                )
            )
        return scores

    def _oura_native_scores(self, user_id: str) -> list[dict[str, Any]]:
        scores = []
        latest_sleep = self._latest_sleep(user_id, "oura")
        if latest_sleep:
            readiness = self._sleep_native_value(latest_sleep)
            if readiness is not None:
                scores.append(
                    self._health_score(
                        provider="oura",
                        category="readiness",
                        value=readiness,
                        qualifier=self._qualifier(readiness),
                        recorded_at=latest_sleep.get("end_time") or _now(),
                    )
                )
        latest_workout = self._latest_workout(user_id, "oura")
        if latest_workout:
            activity = min(100, round((float(latest_workout.get("calories") or 0) / 780.0) * 100))
            scores.append(
                self._health_score(
                    provider="oura",
                    category="activity",
                    value=activity,
                    qualifier=self._qualifier(activity),
                    recorded_at=latest_workout.get("end_time") or _now(),
                )
            )
        return scores

    def _health_score(
        self,
        *,
        provider: str,
        category: str,
        value: Any,
        recorded_at: str,
        qualifier: str | None = None,
        components: dict[str, Any] | None = None,
        data_source_id: str | None = None,
        related_record_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "id": f"score-{uuid.uuid4().hex}",
            "data_source_id": data_source_id,
            "provider": provider,
            "category": category,
            "value": value,
            "qualifier": qualifier,
            "recorded_at": recorded_at,
            "zone_offset": None,
            "components": components or {},
            "related_record_id": related_record_id,
        }

    def _latest_point(self, user_id: str, provider: str, metric_type: str) -> dict[str, Any] | None:
        points = [
            point for point in self._state["timeseries"].setdefault(user_id, [])
            if point.get("provider") == provider and point.get("type") == metric_type
        ]
        return max(points, key=lambda point: point.get("timestamp") or "", default=None)

    def _latest_sleep(self, user_id: str, provider: str) -> dict[str, Any] | None:
        events = [event for event in self._state["sleep"].setdefault(user_id, []) if event.get("provider") == provider]
        return max(events, key=lambda event: event.get("end_time") or "", default=None)

    def _latest_workout(self, user_id: str, provider: str) -> dict[str, Any] | None:
        workouts = [
            workout for workout in self._state["workouts"].setdefault(user_id, [])
            if workout.get("provider") == provider
        ]
        return max(workouts, key=lambda workout: workout.get("end_time") or "", default=None)

    def _sleep_native_value(self, sleep_event: dict[str, Any]) -> int | None:
        efficiency = sleep_event.get("efficiency_percent")
        if efficiency is None:
            return None
        return max(0, min(100, round(float(efficiency))))

    def _qualifier(self, value: Any) -> str | None:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        if numeric >= 85:
            return "excellent"
        if numeric >= 70:
            return "good"
        if numeric >= 50:
            return "fair"
        return "low"

    def _import_apple_records(self, user_id: str, root: ElementTree.Element) -> int:
        count = 0
        for record in root.findall("Record"):
            record_type = record.attrib.get("type")
            if record_type == "HKCategoryTypeIdentifierSleepAnalysis":
                continue
            mapped = APPLE_RECORD_TYPES.get(record_type or "")
            if not mapped:
                continue
            metric_type, unit = mapped
            value = self._float_or_none(record.attrib.get("value"))
            if value is None:
                continue
            self._state["timeseries"][user_id].append(
                {
                    "timestamp": self._apple_timestamp(record.attrib.get("endDate") or record.attrib.get("startDate")),
                    "type": metric_type,
                    "value": value,
                    "unit": unit,
                    "provider": "apple_health_xml",
                    "device": record.attrib.get("sourceName") or "Apple Health Export",
                    "device_type": "apple_health_export",
                }
            )
            count += 1
        return count

    def _import_apple_workouts(self, user_id: str, root: ElementTree.Element) -> int:
        count = 0
        for workout in root.findall("Workout"):
            duration = self._float_or_none(workout.attrib.get("duration")) or 0
            duration_unit = workout.attrib.get("durationUnit") or "min"
            duration_minutes = self._duration_to_minutes(duration, duration_unit)
            stats = self._apple_workout_statistics(workout)
            self._state["workouts"][user_id].append(
                {
                    "id": f"apple-health-workout-{count + 1}",
                    "type": APPLE_WORKOUT_TYPES.get(
                        workout.attrib.get("workoutActivityType") or "",
                        self._clean_apple_type(workout.attrib.get("workoutActivityType")),
                    ),
                    "start_time": self._apple_timestamp(workout.attrib.get("startDate")),
                    "end_time": self._apple_timestamp(workout.attrib.get("endDate")),
                    "duration_minutes": duration_minutes,
                    "calories": self._float_or_none(workout.attrib.get("totalEnergyBurned"))
                    or stats.get("calories"),
                    "distance": self._float_or_none(workout.attrib.get("totalDistance"))
                    or stats.get("distance"),
                    "average_heart_rate": stats.get("average_heart_rate"),
                    "provider": "apple_health_xml",
                    "device": workout.attrib.get("sourceName") or "Apple Health Export",
                }
            )
            count += 1
        return count

    def _import_apple_sleep(self, user_id: str, root: ElementTree.Element) -> int:
        records = sorted(
            [
                record
                for record in root.findall("Record")
                if record.attrib.get("type") == "HKCategoryTypeIdentifierSleepAnalysis"
            ],
            key=lambda record: record.attrib.get("startDate") or "",
        )
        if not records:
            return 0

        sessions: list[list[dict[str, Any]]] = []
        current_session: list[dict[str, Any]] = []
        previous_end: datetime | None = None
        for record in records:
            start = self._apple_datetime(record.attrib.get("startDate"))
            end = self._apple_datetime(record.attrib.get("endDate"))
            if not start or not end:
                continue
            minutes = round((end - start).total_seconds() / 60)
            stage = {
                "stage": APPLE_SLEEP_STAGES.get(record.attrib.get("value") or "", "unknown"),
                "minutes": minutes,
                "startTime": start.isoformat(),
                "endTime": end.isoformat(),
                "_start": start,
                "_end": end,
            }
            if previous_end and (start - previous_end).total_seconds() > 6 * 3600:
                if current_session:
                    sessions.append(current_session)
                current_session = []
            current_session.append(stage)
            previous_end = max(previous_end, end) if previous_end else end
        if current_session:
            sessions.append(current_session)
        if not sessions:
            return 0

        for index, session in enumerate(sessions, start=1):
            starts = [stage["_start"] for stage in session]
            ends = [stage["_end"] for stage in session]
            total_minutes = round((max(ends) - min(starts)).total_seconds() / 60)
            awake_minutes = sum(stage["minutes"] for stage in session if stage["stage"] == "awake")
            efficiency = round((total_minutes - awake_minutes) / total_minutes * 100, 1) if total_minutes else None
            clean_stages = [
                {key: value for key, value in stage.items() if not key.startswith("_")}
                for stage in session
            ]
            self._state["sleep"][user_id].append(
                {
                    "id": f"apple-health-sleep-{index}",
                    "start_time": min(starts).isoformat(),
                    "end_time": max(ends).isoformat(),
                    "duration_minutes": total_minutes,
                    "efficiency_percent": efficiency,
                    "stages": clean_stages,
                    "interruptions": sum(1 for stage in session if stage["stage"] == "awake"),
                    "provider": "apple_health_xml",
                }
            )
        return len(sessions)

    def _apple_workout_statistics(self, workout: ElementTree.Element) -> dict[str, float]:
        stats: dict[str, float] = {}
        for item in workout.findall("WorkoutStatistics"):
            stat_type = item.attrib.get("type")
            if stat_type == "HKQuantityTypeIdentifierActiveEnergyBurned":
                stats["calories"] = self._float_or_none(item.attrib.get("sum")) or 0
            elif stat_type in {
                "HKQuantityTypeIdentifierDistanceWalkingRunning",
                "HKQuantityTypeIdentifierDistanceCycling",
                "HKQuantityTypeIdentifierDistanceSwimming",
            }:
                stats["distance"] = self._float_or_none(item.attrib.get("sum")) or 0
            elif stat_type == "HKQuantityTypeIdentifierHeartRate":
                stats["average_heart_rate"] = (
                    self._float_or_none(item.attrib.get("average"))
                    or self._float_or_none(item.attrib.get("avg"))
                    or 0
                )
        return stats

    def _apple_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S %z")
        except ValueError:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None

    def _apple_timestamp(self, value: str | None) -> str | None:
        parsed = self._apple_datetime(value)
        if parsed is None:
            return None
        return parsed.isoformat()

    def _float_or_none(self, value: str | None) -> float | None:
        try:
            return float(value) if value is not None else None
        except ValueError:
            return None

    def _duration_to_minutes(self, value: float, unit: str) -> float:
        normalized = unit.lower()
        if normalized in {"s", "sec", "second", "seconds"}:
            return round(value / 60, 1)
        if normalized in {"h", "hr", "hour", "hours"}:
            return round(value * 60, 1)
        return round(value, 1)

    def _clean_apple_type(self, value: str | None) -> str | None:
        if not value:
            return None
        return value.replace("HKWorkoutActivityType", "").lower()

    def _build_real_authorization_url(
        self, provider: str, user_id: str, redirect_uri: str | None = None
    ) -> dict[str, Any]:
        if provider != "strava":
            raise OpenWearablesClientError(f"Real OAuth is not implemented for {provider}")
        if not self._strava_client_id:
            raise OpenWearablesClientError("STRAVA_CLIENT_ID is not configured")

        state = uuid.uuid4().hex
        self._state["oauth_states"][state] = {"provider": provider, "user_id": user_id}
        query = urlencode(
            {
                "client_id": self._strava_client_id,
                "redirect_uri": redirect_uri or self._strava_redirect_uri,
                "response_type": "code",
                "approval_prompt": "auto",
                "scope": "read,activity:read_all",
                "state": state,
            }
        )
        return {
            "authorization_url": f"{self._strava_authorize_url}?{query}",
            "state": state,
            "mode": "real",
        }

    async def _exchange_strava_code(self, code: str) -> dict[str, Any]:
        if not self._strava_client_id or not self._strava_client_secret:
            raise OpenWearablesClientError("Strava OAuth credentials are not configured")
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    self._strava_token_url,
                    data={
                        "client_id": self._strava_client_id,
                        "client_secret": self._strava_client_secret,
                        "code": code,
                        "grant_type": "authorization_code",
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OpenWearablesClientError("Strava token exchange failed") from exc
        return response.json()

    async def _import_strava_activities(self, user_id: str, access_token: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(
                    f"{self._strava_api_base_url}/athlete/activities",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"per_page": 10},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OpenWearablesClientError("Strava activity import failed") from exc

        activities = response.json()
        if not isinstance(activities, list):
            return
        self._remove_provider_records(user_id, "strava")
        for activity in activities:
            if not isinstance(activity, dict):
                continue
            start = activity.get("start_date") or activity.get("start_date_local")
            elapsed_seconds = activity.get("elapsed_time")
            self._state["workouts"][user_id].append(
                {
                    "id": str(activity.get("id") or uuid.uuid4().hex),
                    "type": activity.get("sport_type") or activity.get("type"),
                    "start_time": start,
                    "end_time": None,
                    "duration_minutes": round(float(elapsed_seconds or 0) / 60, 1),
                    "calories": None,
                    "distance": activity.get("distance"),
                    "average_heart_rate": activity.get("average_heartrate"),
                    "provider": "strava",
                }
            )


OpenWearablesClient = OpenWearablesBackend
