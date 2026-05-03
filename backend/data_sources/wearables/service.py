from datetime import datetime, timedelta, timezone
from typing import Any

from integrations.open_wearables.client import (
    OpenWearablesBackend,
    OpenWearablesClientError,
    OpenWearablesNotAvailable,
)
from integrations.open_wearables.normalize import (
    OPEN_WEARABLES_SOURCE,
    generated_at,
    normalize_connections,
    normalize_health_scores,
    normalize_providers,
    normalize_sleep_events,
    normalize_summary_payload,
    normalize_timeseries,
    normalize_workouts,
)

DEMO_USER_ID = "local"


class WearableDataService:
    def __init__(
        self,
        session_data: dict[str, Any],
        client: OpenWearablesBackend | None = None,
        configured: bool | None = None,
        seed_configured: bool | None = None,
    ):
        self._session_data = session_data
        self._client = client or OpenWearablesBackend(session_data)
        self._configured = self._client.configured if configured is None else configured
        self._seed_configured = (
            self._client.seed_configured if seed_configured is None else seed_configured
        )

    async def get_or_create_open_wearables_user(self, wholeyou_user_id: str) -> str:
        self._require_configured()

        user_map = self._session_data.setdefault("open_wearables_user_ids", {})
        if wholeyou_user_id in user_map:
            return user_map[wholeyou_user_id]

        existing = await self._client.get_users(
            {"external_user_id": wholeyou_user_id, "limit": 1}
        )
        users = existing.get("items", []) if isinstance(existing, dict) else []
        if users:
            open_wearables_user_id = users[0]["id"]
        else:
            # Local MVP demo user only. TODO: replace with authenticated user
            # profile data when WholeYou has real auth.
            created = await self._client.create_user(
                {
                    "external_user_id": wholeyou_user_id,
                    "email": f"{wholeyou_user_id}@local.wholeyou",
                }
            )
            open_wearables_user_id = created["id"]

        user_map[wholeyou_user_id] = open_wearables_user_id
        return open_wearables_user_id

    async def get_providers(self) -> list[dict[str, Any]]:
        if not self._configured:
            return []
        return normalize_providers(await self._client.get_providers())

    async def start_provider_connection(
        self,
        wholeyou_user_id: str,
        provider: str,
        redirect_uri: str | None = None,
        mode: str = "synthetic",
    ) -> dict[str, Any]:
        open_wearables_user_id = await self.get_or_create_open_wearables_user(
            wholeyou_user_id
        )
        payload = await self._client.get_authorization_url(
            provider,
            open_wearables_user_id,
            redirect_uri=redirect_uri,
            mode=mode,
        )
        return {
            "provider": provider,
            "authorizationUrl": payload.get("authorization_url")
            or payload.get("authorizationUrl"),
            "state": payload.get("state"),
            "mode": payload.get("mode") or mode,
        }

    async def get_connections(self, wholeyou_user_id: str) -> list[dict[str, Any]]:
        if not self._configured:
            return []
        open_wearables_user_id = await self.get_or_create_open_wearables_user(
            wholeyou_user_id
        )
        return normalize_connections(await self._client.get_connections(open_wearables_user_id))

    async def disconnect(self, wholeyou_user_id: str, provider: str) -> dict[str, Any]:
        open_wearables_user_id = await self.get_or_create_open_wearables_user(
            wholeyou_user_id
        )
        # TODO: production disconnect should also update local cache and audit metadata.
        return await self._client.delete_connection(open_wearables_user_id, provider)

    async def clear_connections(self, wholeyou_user_id: str) -> dict[str, Any]:
        open_wearables_user_id = await self.get_or_create_open_wearables_user(
            wholeyou_user_id
        )
        return await self._client.clear_connections(open_wearables_user_id)

    async def handle_oauth_callback(
        self,
        provider: str,
        code: str | None,
        state: str | None,
        error: str | None = None,
    ) -> dict[str, Any]:
        return await self._client.handle_oauth_callback(
            provider,
            code=code,
            state=state,
            error=error,
        )

    async def sync(
        self, wholeyou_user_id: str, provider: str | None = None, async_: bool | None = None
    ) -> dict[str, Any]:
        open_wearables_user_id = await self.get_or_create_open_wearables_user(
            wholeyou_user_id
        )
        payload: dict[str, Any] = {}
        if async_ is not None:
            payload["async"] = async_
        if provider:
            return await self._client.sync_provider(provider, open_wearables_user_id, payload)
        return await self._client.sync_user(open_wearables_user_id, payload)

    async def sync_history(
        self,
        wholeyou_user_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        provider: str | None = None,
    ) -> dict[str, Any]:
        end = end_date or datetime.now(timezone.utc).date().isoformat()
        start = start_date or (datetime.now(timezone.utc).date() - timedelta(days=30)).isoformat()
        open_wearables_user_id = await self.get_or_create_open_wearables_user(
            wholeyou_user_id
        )
        payload = {"start_date": start, "end_date": end}
        if provider:
            return await self._client.sync_provider(provider, open_wearables_user_id, payload)
        return await self._client.sync_user(open_wearables_user_id, payload)

    async def get_wearable_summary(self, wholeyou_user_id: str) -> dict[str, Any]:
        if not self._configured:
            return {
                "connected": False,
                "source": OPEN_WEARABLES_SOURCE,
                "connections": [],
                "timeseries": [],
                "workouts": [],
                "sleep": [],
                "generatedAt": None,
                "message": "Open Wearables base URL is not configured.",
            }

        try:
            connections = await self.get_connections(wholeyou_user_id)
            return {
                "connected": bool(connections),
                "source": OPEN_WEARABLES_SOURCE,
                "connections": connections,
                "timeseries": await self.get_timeseries(wholeyou_user_id, {"limit": 20}),
                "workouts": await self.get_workouts(wholeyou_user_id),
                "sleep": await self.get_sleep(wholeyou_user_id),
                "generatedAt": generated_at(),
            }
        except OpenWearablesClientError as exc:
            return {
                "connected": False,
                "source": OPEN_WEARABLES_SOURCE,
                "connections": [],
                "timeseries": [],
                "workouts": [],
                "sleep": [],
                "generatedAt": None,
                "message": str(exc),
            }

    async def get_summary(self, wholeyou_user_id: str, summary_type: str) -> dict[str, Any]:
        if not self._configured:
            return self._unconfigured_payload(summary_type=summary_type)
        open_wearables_user_id = await self.get_or_create_open_wearables_user(
            wholeyou_user_id
        )
        return normalize_summary_payload(
            await self._client.get_summary(open_wearables_user_id, summary_type)
        )

    async def get_timeseries(
        self, wholeyou_user_id: str, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        if not self._configured:
            return []
        open_wearables_user_id = await self.get_or_create_open_wearables_user(
            wholeyou_user_id
        )
        params = dict(filters or {})
        if "type" in params and "types" not in params:
            params["types"] = params.pop("type")
        return normalize_timeseries(await self._client.get_timeseries(open_wearables_user_id, params))

    async def get_workouts(
        self, wholeyou_user_id: str, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        if not self._configured:
            return []
        open_wearables_user_id = await self.get_or_create_open_wearables_user(
            wholeyou_user_id
        )
        return normalize_workouts(await self._client.get_workouts(open_wearables_user_id, filters))

    async def get_sleep(
        self, wholeyou_user_id: str, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        if not self._configured:
            return []
        open_wearables_user_id = await self.get_or_create_open_wearables_user(
            wholeyou_user_id
        )
        return normalize_sleep_events(await self._client.get_sleep(open_wearables_user_id, filters))

    async def compute_health_scores(self, wholeyou_user_id: str) -> dict[str, Any]:
        open_wearables_user_id = await self.get_or_create_open_wearables_user(
            wholeyou_user_id
        )
        return await self._client.compute_health_scores(open_wearables_user_id)

    async def get_health_scores(
        self, wholeyou_user_id: str, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        if not self._configured:
            return []
        open_wearables_user_id = await self.get_or_create_open_wearables_user(
            wholeyou_user_id
        )
        return normalize_health_scores(await self._client.get_health_scores(open_wearables_user_id, filters))

    async def get_data_sources(self, wholeyou_user_id: str) -> dict[str, Any]:
        if not self._configured:
            return {
                "source": OPEN_WEARABLES_SOURCE,
                "dataSources": [],
                "message": "Open Wearables base URL is not configured.",
            }
        open_wearables_user_id = await self.get_or_create_open_wearables_user(
            wholeyou_user_id
        )
        return normalize_summary_payload(await self._client.get_data_sources(open_wearables_user_id))

    async def create_apple_health_upload_url(
        self, wholeyou_user_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        open_wearables_user_id = await self.get_or_create_open_wearables_user(
            wholeyou_user_id
        )
        return await self._client.create_apple_health_upload_url(open_wearables_user_id, payload)

    async def import_apple_health_xml_direct(
        self, wholeyou_user_id: str, filename: str, content: bytes
    ) -> dict[str, Any]:
        open_wearables_user_id = await self.get_or_create_open_wearables_user(
            wholeyou_user_id
        )
        return await self._client.import_apple_health_xml_file(
            open_wearables_user_id,
            filename=filename,
            content=content,
        )

    async def generate_synthetic_data(
        self,
        seed: int | None = None,
        preset: str = "minimal",
        num_users: int = 1,
    ) -> dict[str, Any]:
        self._require_seed_configured()
        presets = await self._client.get_seed_presets()
        profile = self._profile_for_preset(presets, preset)
        payload = {
            "num_users": num_users,
            "profile": profile,
            "random_seed": seed,
        }
        response = await self._client.generate_seed_data(payload)
        if isinstance(response, dict):
            response.setdefault("preset", preset)
            response.setdefault("num_users", num_users)
        return response

    def _require_configured(self) -> None:
        if not self._configured:
            raise OpenWearablesNotAvailable("Open Wearables base URL is not configured")

    def _require_seed_configured(self) -> None:
        if not self._seed_configured:
            raise OpenWearablesNotAvailable("Open Wearables base URL is not configured")

    def _profile_for_preset(self, presets: Any, preset: str) -> dict[str, Any]:
        if isinstance(presets, list):
            for item in presets:
                if isinstance(item, dict) and item.get("id") == preset:
                    profile = item.get("profile")
                    if isinstance(profile, dict):
                        return profile
        raise OpenWearablesClientError(f"Open Wearables seed preset not found: {preset}")

    def _unconfigured_payload(self, summary_type: str) -> dict[str, Any]:
        return {
            "source": OPEN_WEARABLES_SOURCE,
            "summaryType": summary_type,
            "message": "Open Wearables base URL is not configured.",
        }
