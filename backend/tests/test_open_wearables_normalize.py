import unittest

from integrations.open_wearables.normalize import (
    normalize_connection,
    normalize_provider,
    normalize_sleep_event,
    normalize_timeseries_point,
    normalize_workout_event,
)


class OpenWearablesNormalizeTests(unittest.TestCase):
    def test_normalizes_provider_shape(self):
        provider = normalize_provider(
            {
                "id": "oura",
                "name": "Oura",
                "type": "ring",
                "supports_oauth": True,
                "supports_import": False,
                "requires_mobile": False,
                "logo_url": "https://example.test/oura.svg",
                "enabled": True,
            }
        )

        self.assertEqual(provider["id"], "oura")
        self.assertEqual(provider["supportsOAuth"], True)
        self.assertEqual(provider["supportsImport"], False)
        self.assertEqual(provider["requiresMobile"], False)
        self.assertEqual(provider["logoUrl"], "https://example.test/oura.svg")

    def test_normalizes_connection_without_provider_tokens(self):
        connection = normalize_connection(
            {
                "provider": "garmin",
                "status": "active",
                "provider_user_id": "provider-user-1",
                "scopes": ["activity", "sleep"],
                "created_at": "2026-05-01T00:00:00Z",
                "last_synced_at": "2026-05-02T00:00:00Z",
                "access_token": "must-not-leak",
            }
        )

        self.assertEqual(connection["provider"], "garmin")
        self.assertEqual(connection["providerUserId"], "provider-user-1")
        self.assertEqual(connection["connectedAt"], "2026-05-01T00:00:00Z")
        self.assertEqual(connection["lastSyncedAt"], "2026-05-02T00:00:00Z")
        self.assertEqual(connection["source"], "open_wearables")
        self.assertNotIn("access_token", connection)

    def test_normalizes_timeseries_source_metadata(self):
        point = normalize_timeseries_point(
            {
                "timestamp": "2026-05-02T12:00:00Z",
                "type": "heart_rate",
                "value": 68,
                "unit": "bpm",
                "zone_offset": "-07:00",
                "provider": "fitbit",
                "device": "Charge",
                "device_type": "watch",
            }
        )

        self.assertEqual(point["timestamp"], "2026-05-02T12:00:00Z")
        self.assertEqual(point["type"], "heart_rate")
        self.assertEqual(point["source"]["provider"], "fitbit")
        self.assertEqual(point["source"]["deviceType"], "watch")

    def test_normalizes_workout_and_sleep_events(self):
        workout = normalize_workout_event(
            {
                "id": "w1",
                "type": "run",
                "start_time": "2026-05-01T14:00:00Z",
                "end_time": "2026-05-01T14:45:00Z",
                "duration_minutes": 45,
                "calories": 420,
                "distance": 6.3,
                "average_heart_rate": 142,
                "provider": "strava",
            }
        )
        sleep = normalize_sleep_event(
            {
                "id": "s1",
                "start_time": "2026-05-01T06:00:00Z",
                "end_time": "2026-05-01T13:30:00Z",
                "duration_minutes": 450,
                "efficiency_percent": 91,
                "stages": [{"stage": "deep", "minutes": 82}],
                "interruptions": 2,
                "provider": "oura",
            }
        )

        self.assertEqual(workout["durationMinutes"], 45)
        self.assertEqual(workout["averageHeartRate"], 142)
        self.assertEqual(sleep["durationMinutes"], 450)
        self.assertEqual(sleep["efficiencyPercent"], 91)
        self.assertEqual(sleep["source"]["provider"], "oura")


if __name__ == "__main__":
    unittest.main()
