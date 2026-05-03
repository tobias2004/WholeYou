import unittest

from integrations.open_wearables.client import OpenWearablesBackend


class OpenWearablesBackendTests(unittest.IsolatedAsyncioTestCase):
    APPLE_HEALTH_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="en_US">
  <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Apple Watch" unit="count/min" startDate="2026-05-01 08:00:00 -0700" endDate="2026-05-01 08:00:00 -0700" value="72"/>
  <Record type="HKQuantityTypeIdentifierStepCount" sourceName="iPhone" unit="count" startDate="2026-05-01 09:00:00 -0700" endDate="2026-05-01 09:10:00 -0700" value="840"/>
  <Record type="HKQuantityTypeIdentifierActiveEnergyBurned" sourceName="Apple Watch" unit="kcal" startDate="2026-05-01 10:00:00 -0700" endDate="2026-05-01 10:30:00 -0700" value="118"/>
  <Record type="HKQuantityTypeIdentifierBodyMass" sourceName="Health" unit="kg" startDate="2026-05-01 07:00:00 -0700" endDate="2026-05-01 07:00:00 -0700" value="74.5"/>
  <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Apple Watch" startDate="2026-05-01 23:00:00 -0700" endDate="2026-05-02 02:00:00 -0700" value="HKCategoryValueSleepAnalysisAsleepDeep"/>
  <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Apple Watch" startDate="2026-05-02 02:00:00 -0700" endDate="2026-05-02 06:30:00 -0700" value="HKCategoryValueSleepAnalysisAsleepCore"/>
  <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="38" durationUnit="min" sourceName="Apple Watch" startDate="2026-05-01 17:00:00 -0700" endDate="2026-05-01 17:38:00 -0700">
    <WorkoutStatistics type="HKQuantityTypeIdentifierDistanceWalkingRunning" startDate="2026-05-01 17:00:00 -0700" endDate="2026-05-01 17:38:00 -0700" sum="6200" unit="m"/>
    <WorkoutStatistics type="HKQuantityTypeIdentifierActiveEnergyBurned" startDate="2026-05-01 17:00:00 -0700" endDate="2026-05-01 17:38:00 -0700" sum="410" unit="kcal"/>
    <WorkoutStatistics type="HKQuantityTypeIdentifierHeartRate" startDate="2026-05-01 17:00:00 -0700" endDate="2026-05-01 17:38:00 -0700" average="148" unit="count/min"/>
  </Workout>
</HealthData>"""

    APPLE_HEALTH_TWO_SLEEP_SESSIONS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="en_US">
  <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Apple Watch" startDate="2026-05-01 23:00:00 -0700" endDate="2026-05-02 02:00:00 -0700" value="HKCategoryValueSleepAnalysisAsleepDeep"/>
  <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Apple Watch" startDate="2026-05-02 02:00:00 -0700" endDate="2026-05-02 06:30:00 -0700" value="HKCategoryValueSleepAnalysisAsleepCore"/>
  <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Apple Watch" startDate="2026-05-03 00:30:00 -0700" endDate="2026-05-03 07:30:00 -0700" value="HKCategoryValueSleepAnalysisAsleepREM"/>
</HealthData>"""

    async def test_generate_seed_data_populates_local_wearable_records(self):
        store = {}
        backend = OpenWearablesBackend(store)

        user = await backend.create_user(
            {"external_user_id": "local", "email": "local@wholeyou.test"}
        )
        result = await backend.generate_seed_data(
            {"num_users": 1, "profile": {"preset": "minimal"}, "random_seed": 12345}
        )

        timeseries = (await backend.get_timeseries(user["id"], {"types": "heart_rate"}))["items"]
        workouts = (await backend.get_workouts(user["id"]))["items"]
        sleep = (await backend.get_sleep(user["id"]))["items"]
        connections = (await backend.get_connections(user["id"]))["connections"]

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["seed_used"], 12345)
        self.assertGreater(len(timeseries), 0)
        self.assertTrue(all(point["type"] == "heart_rate" for point in timeseries))
        self.assertGreater(len(workouts), 0)
        self.assertGreater(len(sleep), 0)
        self.assertEqual(connections[0]["provider"], "synthetic")

    async def test_provider_connection_is_local_demo_state(self):
        store = {}
        backend = OpenWearablesBackend(store)
        user = await backend.create_user({"external_user_id": "local"})

        connection = await backend.get_authorization_url("oura", user["id"], mode="synthetic")
        connections = (await backend.get_connections(user["id"]))["connections"]
        timeseries = (await backend.get_timeseries(user["id"], {"types": "heart_rate"}))["items"]

        self.assertIsNone(connection["authorization_url"])
        self.assertEqual(connections[0]["provider"], "oura")
        self.assertEqual(connections[0]["status"], "connected")
        self.assertGreater(len(timeseries), 0)
        self.assertTrue(all(point["provider"] == "oura" for point in timeseries))

    async def test_synthetic_strava_generates_workouts_only(self):
        store = {}
        backend = OpenWearablesBackend(store)
        user = await backend.create_user({"external_user_id": "local"})

        await backend.get_authorization_url("strava", user["id"], mode="synthetic")
        timeseries = (await backend.get_timeseries(user["id"]))["items"]
        workouts = (await backend.get_workouts(user["id"]))["items"]
        sleep = (await backend.get_sleep(user["id"]))["items"]

        self.assertEqual(timeseries, [])
        self.assertEqual(sleep, [])
        self.assertGreaterEqual(len(workouts), 3)
        self.assertGreater(len({workout["type"] for workout in workouts}), 1)
        self.assertGreater(len({workout["duration_minutes"] for workout in workouts}), 1)

    async def test_synthetic_whoop_generates_sleep_and_workouts_without_timeseries(self):
        store = {}
        backend = OpenWearablesBackend(store)
        user = await backend.create_user({"external_user_id": "local"})

        await backend.get_authorization_url("whoop", user["id"], mode="synthetic")
        timeseries = (await backend.get_timeseries(user["id"]))["items"]
        workouts = (await backend.get_workouts(user["id"]))["items"]
        sleep = (await backend.get_sleep(user["id"]))["items"]

        self.assertEqual(timeseries, [])
        self.assertGreaterEqual(len(workouts), 2)
        self.assertGreaterEqual(len(sleep), 2)

    async def test_synthetic_ultrahuman_generates_sleep_and_timeseries_without_workouts(self):
        store = {}
        backend = OpenWearablesBackend(store)
        user = await backend.create_user({"external_user_id": "local"})

        await backend.get_authorization_url("ultrahuman", user["id"], mode="synthetic")
        timeseries = (await backend.get_timeseries(user["id"]))["items"]
        workouts = (await backend.get_workouts(user["id"]))["items"]
        sleep = (await backend.get_sleep(user["id"]))["items"]

        self.assertGreater(len(timeseries), 0)
        self.assertEqual(workouts, [])
        self.assertGreaterEqual(len(sleep), 2)

    async def test_synthetic_oura_garmin_suunto_generate_supported_categories(self):
        for provider in ("oura", "garmin", "suunto"):
            store = {}
            backend = OpenWearablesBackend(store)
            user = await backend.create_user({"external_user_id": "local"})

            await backend.get_authorization_url(provider, user["id"], mode="synthetic")
            timeseries = (await backend.get_timeseries(user["id"]))["items"]
            workouts = (await backend.get_workouts(user["id"]))["items"]
            sleep = (await backend.get_sleep(user["id"]))["items"]

            self.assertGreater(len(timeseries), 0, provider)
            self.assertGreaterEqual(len(workouts), 2, provider)
            self.assertGreaterEqual(len(sleep), 2, provider)
            self.assertTrue(all(item["provider"] == provider for item in timeseries))
            self.assertTrue(all(item["provider"] == provider for item in workouts))
            self.assertTrue(all(item["provider"] == provider for item in sleep))

    async def test_synthetic_provider_coverage_matrix(self):
        expected = {
            "garmin": {"timeseries": True, "workouts": True, "sleep": True},
            "polar": {"timeseries": False, "workouts": True, "sleep": False},
            "suunto": {"timeseries": True, "workouts": True, "sleep": True},
            "oura": {"timeseries": True, "workouts": True, "sleep": True},
            "whoop": {"timeseries": False, "workouts": True, "sleep": True},
            "ultrahuman": {"timeseries": True, "workouts": False, "sleep": True},
            "strava": {"timeseries": False, "workouts": True, "sleep": False},
            "fitbit": {"timeseries": True, "workouts": True, "sleep": True},
            "withings": {"timeseries": True, "workouts": False, "sleep": True},
        }

        for provider, coverage in expected.items():
            with self.subTest(provider=provider):
                store = {}
                backend = OpenWearablesBackend(store)
                user = await backend.create_user({"external_user_id": "local"})

                await backend.get_authorization_url(provider, user["id"], mode="synthetic")
                timeseries = (await backend.get_timeseries(user["id"]))["items"]
                workouts = (await backend.get_workouts(user["id"]))["items"]
                sleep = (await backend.get_sleep(user["id"]))["items"]

                self.assertEqual(bool(timeseries), coverage["timeseries"])
                self.assertEqual(bool(workouts), coverage["workouts"])
                self.assertEqual(bool(sleep), coverage["sleep"])
                if coverage["timeseries"]:
                    self.assertTrue(all(item["provider"] == provider for item in timeseries))
                if coverage["workouts"]:
                    self.assertTrue(all(item["provider"] == provider for item in workouts))
                if coverage["sleep"]:
                    self.assertTrue(all(item["provider"] == provider for item in sleep))

    async def test_synthetic_record_counts_vary_within_provider_ranges(self):
        store = {}
        backend = OpenWearablesBackend(store)
        user = await backend.create_user({"external_user_id": "local"})

        backend._populate_synthetic_records(user["id"], __import__("random").Random(1), provider="oura")
        first_counts = (
            len((await backend.get_timeseries(user["id"]))["items"]),
            len((await backend.get_workouts(user["id"]))["items"]),
            len((await backend.get_sleep(user["id"]))["items"]),
        )
        await backend.clear_connections(user["id"])
        backend._populate_synthetic_records(user["id"], __import__("random").Random(9), provider="oura")
        second_counts = (
            len((await backend.get_timeseries(user["id"]))["items"]),
            len((await backend.get_workouts(user["id"]))["items"]),
            len((await backend.get_sleep(user["id"]))["items"]),
        )

        self.assertNotEqual(first_counts, second_counts)
        for timeseries_count, workout_count, sleep_count in (first_counts, second_counts):
            self.assertGreaterEqual(timeseries_count, 48)
            self.assertLessEqual(timeseries_count, 240)
            self.assertGreaterEqual(workout_count, 2)
            self.assertLessEqual(workout_count, 6)
            self.assertGreaterEqual(sleep_count, 2)
            self.assertLessEqual(sleep_count, 7)

    async def test_clear_connections_removes_local_wearable_state(self):
        store = {}
        backend = OpenWearablesBackend(store)
        user = await backend.create_user({"external_user_id": "local"})
        await backend.get_authorization_url("oura", user["id"], mode="synthetic")

        result = await backend.clear_connections(user["id"])
        connections = (await backend.get_connections(user["id"]))["connections"]
        timeseries = (await backend.get_timeseries(user["id"]))["items"]

        self.assertEqual(result["status"], "cleared")
        self.assertEqual(connections, [])
        self.assertEqual(timeseries, [])

    async def test_compute_health_scores_stores_internal_sleep_and_resilience_scores(self):
        store = {}
        backend = OpenWearablesBackend(store)
        user = await backend.create_user({"external_user_id": "local"})
        await backend.get_authorization_url("garmin", user["id"], mode="synthetic")

        result = await backend.compute_health_scores(user["id"])
        scores = (await backend.get_health_scores(user["id"]))["items"]
        internal_categories = {
            score["category"] for score in scores if score["provider"] == "internal"
        }

        self.assertEqual(result["status"], "computed")
        self.assertGreaterEqual(result["scoresComputed"], 2)
        self.assertIn("sleep", internal_categories)
        self.assertIn("resilience", internal_categories)
        sleep_score = next(
            score for score in scores if score["provider"] == "internal" and score["category"] == "sleep"
        )
        self.assertGreaterEqual(sleep_score["value"], 0)
        self.assertLessEqual(sleep_score["value"], 100)
        self.assertEqual(
            set(sleep_score["components"]),
            {"duration", "stages", "consistency", "interruptions"},
        )

    async def test_compute_health_scores_stores_provider_native_scores(self):
        store = {}
        backend = OpenWearablesBackend(store)
        user = await backend.create_user({"external_user_id": "local"})
        await backend.get_authorization_url("garmin", user["id"], mode="synthetic")
        await backend.get_authorization_url("whoop", user["id"], mode="synthetic")
        await backend.get_authorization_url("oura", user["id"], mode="synthetic")

        await backend.compute_health_scores(user["id"])
        scores = (await backend.get_health_scores(user["id"]))["items"]
        native_categories = {
            (score["provider"], score["category"])
            for score in scores
            if score["provider"] != "internal"
        }

        self.assertIn(("garmin", "body_battery"), native_categories)
        self.assertIn(("garmin", "stress"), native_categories)
        self.assertIn(("whoop", "strain"), native_categories)
        self.assertIn(("whoop", "recovery"), native_categories)
        self.assertIn(("oura", "readiness"), native_categories)
        self.assertIn(("oura", "activity"), native_categories)

    async def test_clear_connections_removes_health_scores(self):
        store = {}
        backend = OpenWearablesBackend(store)
        user = await backend.create_user({"external_user_id": "local"})
        await backend.get_authorization_url("garmin", user["id"], mode="synthetic")
        await backend.compute_health_scores(user["id"])

        await backend.clear_connections(user["id"])
        scores = (await backend.get_health_scores(user["id"]))["items"]

        self.assertEqual(scores, [])

    async def test_real_strava_connection_returns_oauth_url_without_synthetic_data(self):
        store = {}
        backend = OpenWearablesBackend(
            store,
            strava_client_id="12345",
            strava_client_secret="secret",
            strava_redirect_uri="http://localhost:8000/api/wearables/oauth/strava/callback",
        )
        user = await backend.create_user({"external_user_id": "local"})

        connection = await backend.get_authorization_url("strava", user["id"], mode="real")
        connections = (await backend.get_connections(user["id"]))["connections"]
        timeseries = (await backend.get_timeseries(user["id"]))["items"]

        self.assertIn("https://www.strava.com/oauth/authorize", connection["authorization_url"])
        self.assertIn("client_id=12345", connection["authorization_url"])
        self.assertIn("activity%3Aread_all", connection["authorization_url"])
        self.assertEqual(connections, [])
        self.assertEqual(timeseries, [])

    async def test_apple_health_xml_import_parses_standardized_records(self):
        store = {}
        backend = OpenWearablesBackend(store)
        user = await backend.create_user({"external_user_id": "local"})

        result = await backend.import_apple_health_xml_direct(
            user["id"],
            filename="export.xml",
            content=self.APPLE_HEALTH_XML,
        )
        timeseries = (await backend.get_timeseries(user["id"]))["items"]
        workouts = (await backend.get_workouts(user["id"]))["items"]
        sleep = (await backend.get_sleep(user["id"]))["items"]
        connections = (await backend.get_connections(user["id"]))["connections"]

        self.assertEqual(result["status"], "imported")
        self.assertEqual(result["provider"], "apple_health_xml")
        self.assertEqual(result["timeseriesImported"], 4)
        self.assertEqual(result["workoutsImported"], 1)
        self.assertEqual(result["sleepImported"], 1)
        self.assertEqual(connections[0]["provider"], "apple_health_xml")
        self.assertEqual({point["type"] for point in timeseries}, {"heart_rate", "steps", "energy", "weight"})
        self.assertEqual(workouts[0]["type"], "running")
        self.assertEqual(workouts[0]["calories"], 410)
        self.assertEqual(workouts[0]["distance"], 6200)
        self.assertEqual(workouts[0]["average_heart_rate"], 148)
        self.assertEqual(sleep[0]["duration_minutes"], 450)

    async def test_apple_health_xml_import_splits_sleep_sessions_by_gap(self):
        store = {}
        backend = OpenWearablesBackend(store)
        user = await backend.create_user({"external_user_id": "local"})

        result = await backend.import_apple_health_xml_direct(
            user["id"],
            filename="export.xml",
            content=self.APPLE_HEALTH_TWO_SLEEP_SESSIONS_XML,
        )
        sleep = (await backend.get_sleep(user["id"]))["items"]

        self.assertEqual(result["sleepImported"], 2)
        self.assertEqual(len(sleep), 2)
        self.assertEqual(sleep[0]["duration_minutes"], 450)
        self.assertEqual(sleep[1]["duration_minutes"], 420)

    async def test_apple_health_xml_import_rejects_non_healthdata_xml(self):
        backend = OpenWearablesBackend({})
        user = await backend.create_user({"external_user_id": "local"})

        with self.assertRaisesRegex(Exception, "Apple Health"):
            await backend.import_apple_health_xml_direct(
                user["id"],
                filename="export.xml",
                content=b"<notHealthData />",
            )


if __name__ == "__main__":
    unittest.main()
