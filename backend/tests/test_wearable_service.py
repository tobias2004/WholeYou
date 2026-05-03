import unittest

from data_sources.wearables.service import WearableDataService


class FakeOpenWearablesClient:
    def __init__(self):
        self.created_users = []
        self.auth_requests = []
        self.sync_requests = []
        self.seed_requests = []

    async def get_users(self, params=None):
        del params
        return {"items": []}

    async def create_user(self, payload):
        self.created_users.append(payload)
        return {"id": "ow-user-1", **payload}

    async def get_authorization_url(self, provider, user_id, redirect_uri=None, mode="synthetic"):
        self.auth_requests.append(
            {
                "provider": provider,
                "user_id": user_id,
                "redirect_uri": redirect_uri,
                "mode": mode,
            }
        )
        return {
            "authorization_url": "https://connect.example/authorize",
            "state": "abc",
            "mode": mode,
        }

    async def get_connections(self, user_id):
        del user_id
        return [
            {
                "provider": "oura",
                "status": "active",
                "provider_user_id": "oura-user",
                "created_at": "2026-05-01T00:00:00Z",
            }
        ]

    async def sync_user(self, user_id, payload):
        self.sync_requests.append({"user_id": user_id, "payload": payload})
        return {"status": "queued", "user_id": user_id}

    async def get_seed_presets(self):
        return [
            {
                "id": "minimal",
                "label": "Minimal (Quick)",
                "description": "Small test dataset.",
                "profile": {
                    "preset": "minimal",
                    "generate_workouts": True,
                    "generate_sleep": True,
                    "generate_time_series": False,
                },
            }
        ]

    async def generate_seed_data(self, payload):
        self.seed_requests.append(payload)
        return {"task_id": "task-1", "status": "dispatched", "seed_used": payload["random_seed"]}

    async def clear_connections(self, user_id):
        return {"status": "cleared", "user_id": user_id}


class WearableDataServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_or_create_user_stores_minimal_mapping(self):
        session_data = {}
        fake_client = FakeOpenWearablesClient()
        service = WearableDataService(
            session_data=session_data,
            client=fake_client,
            configured=True,
            seed_configured=False,
        )

        user_id = await service.get_or_create_open_wearables_user("local")

        self.assertEqual(user_id, "ow-user-1")
        self.assertEqual(session_data["open_wearables_user_ids"]["local"], "ow-user-1")
        self.assertEqual(fake_client.created_users[0]["external_user_id"], "local")

    async def test_start_provider_connection_uses_open_wearables_user(self):
        session_data = {"open_wearables_user_ids": {"local": "ow-user-1"}}
        fake_client = FakeOpenWearablesClient()
        service = WearableDataService(
            session_data=session_data,
            client=fake_client,
            configured=True,
            seed_configured=False,
        )

        result = await service.start_provider_connection("local", "oura")

        self.assertEqual(result["provider"], "oura")
        self.assertEqual(result["authorizationUrl"], "https://connect.example/authorize")
        self.assertEqual(fake_client.auth_requests[0]["user_id"], "ow-user-1")

    async def test_unconfigured_service_returns_disconnected_summary(self):
        service = WearableDataService(session_data={}, configured=False)

        summary = await service.get_wearable_summary("local")

        self.assertFalse(summary["connected"])
        self.assertEqual(summary["connections"], [])
        self.assertIn("not configured", summary["message"])

    async def test_unconfigured_service_returns_empty_read_models(self):
        service = WearableDataService(session_data={}, configured=False)

        self.assertEqual(await service.get_providers(), [])
        self.assertEqual(await service.get_timeseries("local"), [])
        self.assertEqual(await service.get_workouts("local"), [])
        self.assertEqual(await service.get_sleep("local"), [])
        self.assertEqual(
            (await service.get_summary("local", "activity"))["message"],
            "Open Wearables base URL is not configured.",
        )

    async def test_generate_synthetic_data_uses_backend_seed_generator(self):
        fake_client = FakeOpenWearablesClient()
        service = WearableDataService(
            session_data={},
            client=fake_client,
            configured=True,
            seed_configured=True,
        )

        result = await service.generate_synthetic_data(seed=12345, preset="minimal")

        self.assertEqual(result["task_id"], "task-1")
        self.assertEqual(result["seed_used"], 12345)
        self.assertEqual(fake_client.seed_requests[0]["num_users"], 1)
        self.assertEqual(fake_client.seed_requests[0]["profile"]["preset"], "minimal")

    async def test_default_service_uses_local_open_wearables_backend(self):
        session_data = {}
        service = WearableDataService(session_data=session_data)

        await service.get_or_create_open_wearables_user("local")
        result = await service.generate_synthetic_data(seed=12345, preset="minimal")
        heart_rate = await service.get_timeseries("local", {"type": "heart_rate"})
        workouts = await service.get_workouts("local")
        sleep = await service.get_sleep("local")

        self.assertEqual(result["status"], "completed")
        self.assertGreater(len(heart_rate), 0)
        self.assertGreater(len(workouts), 0)
        self.assertGreater(len(sleep), 0)


if __name__ == "__main__":
    unittest.main()
