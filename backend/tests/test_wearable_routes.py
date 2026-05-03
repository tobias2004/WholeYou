import unittest

from fastapi.testclient import TestClient

import data_sources.wearables.routes as wearable_routes
from main import app
from session_store import SESSION_DATA


class FakeWearableDataService:
    def __init__(self):
        self.compute_calls = []

    async def get_providers(self):
        return [{"id": "oura", "name": "Oura", "supportsOAuth": True, "supportsImport": False}]

    async def get_summary(self, user_id, summary_type):
        del user_id
        return {"source": "open_wearables", "summaryType": summary_type}

    async def get_timeseries(self, user_id, filters=None):
        del user_id, filters
        return [
            {
                "timestamp": "2026-05-02T08:00:00Z",
                "type": "heart_rate",
                "value": 64,
                "unit": "bpm",
                "source": {"provider": "oura"},
            }
        ]

    async def get_workouts(self, user_id, filters=None):
        del user_id, filters
        return [{"id": "w1", "type": "walk", "source": {"provider": "oura"}}]

    async def get_sleep(self, user_id, filters=None):
        del user_id, filters
        return [{"id": "s1", "durationMinutes": 420, "source": {"provider": "oura"}}]

    async def get_data_sources(self, user_id):
        del user_id
        return {"source": "open_wearables", "dataSources": []}

    async def get_health_scores(self, user_id, filters=None):
        del user_id, filters
        return [
            {
                "id": "score-1",
                "category": "sleep",
                "value": 82,
                "qualifier": "good",
                "recordedAt": "2026-05-02T06:30:00Z",
                "provider": "internal",
                "components": {"duration": {"value": 95}},
            }
        ]

    async def compute_health_scores(self, user_id):
        self.compute_calls.append(user_id)
        return {"status": "computed", "scoresComputed": 1}

    async def start_provider_connection(self, user_id, provider, mode="synthetic", redirect_uri=None):
        del user_id, redirect_uri
        return {
            "provider": provider,
            "authorizationUrl": "https://connect.example/authorize" if mode == "real" else None,
            "state": "state-1",
            "mode": mode,
        }

    async def clear_connections(self, user_id):
        del user_id
        return {"status": "cleared"}

    async def generate_synthetic_data(self, seed=None, preset="minimal", num_users=1):
        return {
            "task_id": "task-1",
            "status": "dispatched",
            "seed_used": seed,
            "preset": preset,
            "num_users": num_users,
        }

    async def sync(self, user_id, provider=None, async_=None):
        del user_id, async_
        return {"status": "synced", "provider": provider}

    async def sync_history(self, user_id, start_date=None, end_date=None, provider=None):
        del user_id, start_date, end_date
        return {"status": "synced", "provider": provider}

    async def handle_oauth_callback(self, provider, code=None, state=None, error=None):
        del code, state, error
        return {"status": "connected", "provider": provider}

    async def import_apple_health_xml_direct(self, user_id, filename, content):
        del user_id, content
        return {"status": "imported", "filename": filename}


class WearableRoutesTests(unittest.TestCase):
    def setUp(self):
        SESSION_DATA.clear()
        self.original_service = wearable_routes._service
        self.fake_service = FakeWearableDataService()
        wearable_routes._service = lambda: self.fake_service
        self.client = TestClient(app)

    def tearDown(self):
        wearable_routes._service = self.original_service
        SESSION_DATA.clear()

    def test_providers_route_returns_open_wearables_providers(self):
        response = self.client.get("/api/wearables/providers")

        self.assertEqual(response.status_code, 200)
        providers = response.json()
        self.assertTrue(any(provider["id"] == "oura" for provider in providers))

    def test_summary_routes_return_normalized_data(self):
        activity = self.client.get("/api/wearables/summary/activity")
        sleep = self.client.get("/api/wearables/summary/sleep")
        body = self.client.get("/api/wearables/summary/body")
        data = self.client.get("/api/wearables/summary/data")

        self.assertEqual(activity.status_code, 200)
        self.assertEqual(sleep.status_code, 200)
        self.assertEqual(body.status_code, 200)
        self.assertEqual(data.status_code, 200)
        self.assertEqual(activity.json()["source"], "open_wearables")

    def test_timeseries_and_events_routes_return_normalized_data(self):
        timeseries = self.client.get("/api/wearables/timeseries?type=heart_rate")
        workouts = self.client.get("/api/wearables/events/workouts")
        sleep = self.client.get("/api/wearables/events/sleep")
        sources = self.client.get("/api/wearables/data-sources")

        self.assertEqual(timeseries.status_code, 200)
        self.assertEqual(workouts.status_code, 200)
        self.assertEqual(sleep.status_code, 200)
        self.assertEqual(sources.status_code, 200)
        self.assertEqual(timeseries.json()[0]["source"]["provider"], "oura")
        self.assertEqual(workouts.json()[0]["source"]["provider"], "oura")
        self.assertEqual(sleep.json()[0]["source"]["provider"], "oura")

    def test_health_scores_routes_compute_and_return_scores(self):
        computed = self.client.post("/api/wearables/health-scores/compute")
        scores = self.client.get("/api/wearables/health-scores")

        self.assertEqual(computed.status_code, 200)
        self.assertEqual(computed.json()["scoresComputed"], 1)
        self.assertEqual(scores.status_code, 200)
        self.assertEqual(scores.json()[0]["category"], "sleep")
        self.assertEqual(scores.json()[0]["provider"], "internal")

    def test_connect_route_returns_authorization_url(self):
        response = self.client.post("/api/wearables/connect/oura", json={"mode": "real"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider"], "oura")
        self.assertEqual(response.json()["authorizationUrl"], "https://connect.example/authorize")
        self.assertEqual(self.fake_service.compute_calls, [])

    def test_synthetic_connect_route_does_not_require_authorization_url(self):
        response = self.client.post("/api/wearables/connect/oura", json={"mode": "synthetic"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider"], "oura")
        self.assertIsNone(response.json()["authorizationUrl"])
        self.assertEqual(response.json()["mode"], "synthetic")
        self.assertEqual(self.fake_service.compute_calls, [wearable_routes.DEMO_USER_ID])

    def test_clear_connections_route(self):
        response = self.client.delete("/api/wearables/connections")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "cleared")

    def test_generate_synthetic_data_route_dispatches_seed_generation(self):
        response = self.client.post(
            "/api/wearables/synthetic-data",
            json={"seed": 12345, "preset": "minimal", "numUsers": 1},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["task_id"], "task-1")
        self.assertEqual(response.json()["seed_used"], 12345)
        self.assertEqual(self.fake_service.compute_calls, [wearable_routes.DEMO_USER_ID])

    def test_sync_routes_compute_health_scores_after_data_sync(self):
        synced = self.client.post("/api/wearables/sync", json={"provider": "oura"})
        history = self.client.post(
            "/api/wearables/sync-history",
            json={"provider": "oura", "startDate": "2026-05-01", "endDate": "2026-05-02"},
        )

        self.assertEqual(synced.status_code, 200)
        self.assertEqual(history.status_code, 200)
        self.assertEqual(
            self.fake_service.compute_calls,
            [wearable_routes.DEMO_USER_ID, wearable_routes.DEMO_USER_ID],
        )

    def test_oauth_callback_computes_health_scores_after_provider_connects(self):
        response = self.client.get(
            "/api/wearables/oauth/oura/callback?code=code-1&state=state-1",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "http://localhost:3000/")
        self.assertEqual(self.fake_service.compute_calls, [wearable_routes.DEMO_USER_ID])

    def test_apple_health_xml_direct_import_computes_health_scores(self):
        response = self.client.post(
            "/api/wearables/import/apple-health/xml/direct",
            files={"file": ("export.xml", b"<HealthData/>", "application/xml")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "imported")
        self.assertEqual(self.fake_service.compute_calls, [wearable_routes.DEMO_USER_ID])


class WearableRoutesLocalBackendTests(unittest.TestCase):
    def setUp(self):
        SESSION_DATA.clear()
        self.client = TestClient(app)

    def tearDown(self):
        SESSION_DATA.clear()

    def test_synthetic_generation_populates_wearable_routes(self):
        generated = self.client.post(
            "/api/wearables/synthetic-data",
            json={"seed": 12345, "preset": "minimal", "numUsers": 1},
        )
        heart_rate = self.client.get("/api/wearables/timeseries?type=heart_rate&limit=3")
        workouts = self.client.get("/api/wearables/events/workouts")
        sleep = self.client.get("/api/wearables/events/sleep")

        self.assertEqual(generated.status_code, 200)
        self.assertEqual(generated.json()["status"], "completed")
        self.assertEqual(heart_rate.status_code, 200)
        self.assertGreater(len(heart_rate.json()), 0)
        self.assertGreater(len(workouts.json()), 0)
        self.assertGreater(len(sleep.json()), 0)

    def test_synthetic_connect_populates_only_selected_provider(self):
        connected = self.client.post("/api/wearables/connect/oura", json={"mode": "synthetic"})
        heart_rate = self.client.get("/api/wearables/timeseries?type=heart_rate&limit=3")
        connections = self.client.get("/api/wearables/connections")

        self.assertEqual(connected.status_code, 200)
        self.assertIsNone(connected.json()["authorizationUrl"])
        self.assertEqual(connections.json()[0]["provider"], "oura")
        self.assertGreater(len(heart_rate.json()), 0)
        self.assertTrue(all(point["source"]["provider"] == "oura" for point in heart_rate.json()))

    def test_clear_connections_removes_local_wearable_state(self):
        self.client.post("/api/wearables/connect/oura", json={"mode": "synthetic"})

        cleared = self.client.delete("/api/wearables/connections")
        heart_rate = self.client.get("/api/wearables/timeseries?type=heart_rate")
        connections = self.client.get("/api/wearables/connections")

        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json()["status"], "cleared")
        self.assertEqual(heart_rate.json(), [])
        self.assertEqual(connections.json(), [])

    def test_compute_health_scores_route_stores_internal_and_native_scores(self):
        self.client.post("/api/wearables/connect/garmin", json={"mode": "synthetic"})
        self.client.post("/api/wearables/connect/whoop", json={"mode": "synthetic"})

        computed = self.client.post("/api/wearables/health-scores/compute")
        scores = self.client.get("/api/wearables/health-scores")
        categories = {(score["provider"], score["category"]) for score in scores.json()}

        self.assertEqual(computed.status_code, 200)
        self.assertGreaterEqual(computed.json()["scoresComputed"], 4)
        self.assertIn(("internal", "sleep"), categories)
        self.assertIn(("internal", "resilience"), categories)
        self.assertIn(("garmin", "body_battery"), categories)
        self.assertIn(("whoop", "strain"), categories)

    def test_apple_health_xml_upload_adds_dashboard_data(self):
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="en_US">
  <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Apple Watch" unit="count/min" startDate="2026-05-01 08:00:00 -0700" endDate="2026-05-01 08:00:00 -0700" value="72"/>
  <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Apple Watch" startDate="2026-05-01 23:00:00 -0700" endDate="2026-05-02 06:30:00 -0700" value="HKCategoryValueSleepAnalysisAsleepCore"/>
  <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="38" durationUnit="min" totalDistance="6200" totalDistanceUnit="m" totalEnergyBurned="410" totalEnergyBurnedUnit="kcal" startDate="2026-05-01 17:00:00 -0700" endDate="2026-05-01 17:38:00 -0700"/>
</HealthData>"""

        uploaded = self.client.post(
            "/api/wearables/import/apple-health/xml/direct",
            files={"file": ("export.xml", xml, "application/xml")},
        )
        heart_rate = self.client.get("/api/wearables/timeseries?type=heart_rate")
        workouts = self.client.get("/api/wearables/events/workouts")
        sleep = self.client.get("/api/wearables/events/sleep")

        self.assertEqual(uploaded.status_code, 200)
        self.assertEqual(uploaded.json()["status"], "imported")
        self.assertEqual(heart_rate.json()[0]["source"]["provider"], "apple_health_xml")
        self.assertEqual(workouts.json()[0]["source"]["provider"], "apple_health_xml")
        self.assertEqual(sleep.json()[0]["source"]["provider"], "apple_health_xml")

    def test_apple_health_xml_upload_rejects_non_xml_file(self):
        uploaded = self.client.post(
            "/api/wearables/import/apple-health/xml/direct",
            files={"file": ("export.txt", b"nope", "text/plain")},
        )

        self.assertEqual(uploaded.status_code, 400)


if __name__ == "__main__":
    unittest.main()
