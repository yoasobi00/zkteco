import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import zkteco


class ExtractionTests(unittest.TestCase):
    def test_group_export_uses_saved_ids_names_and_cutoff(self):
        records = [
            (10, "2026-08-01 08:00:00"),
            (10, "2026-07-31 08:00:00"),
            (20, "2026-08-01 09:00:00"),
        ]
        groups = {
            "Team": {
                "file": "team.csv",
                "cutoff": "2026-08-01",
                "members": [{"id": 10, "name": "Renamed"}],
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "team.csv"
            with patch("zkteco.fetch_attendance", return_value=(records, {})):
                count = zkteco.export_group("Team", output, groups=groups)

            self.assertEqual(count, 1)
            self.assertEqual(output.read_text(encoding="utf-8").splitlines(), [
                "User ID,Name,Date,Time",
                "10,Renamed,2026-08-01,08:00:00",
            ])

    def test_all_logs_export_includes_ids_not_in_a_group(self):
        records = [(99, "2026-08-02 10:30:00")]
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "all.csv"
            with patch("zkteco.fetch_attendance", return_value=(records, {99: "Device User"})):
                count = zkteco.export_group(None, output, groups={})

            self.assertEqual(count, 1)
            self.assertIn("99,Device User,2026-08-02,10:30:00", output.read_text(encoding="utf-8"))

    def test_labeled_device_configuration_round_trips(self):
        devices = {"Warehouse": {"ip": "10.0.0.25", "port": 4370}}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "devices.json"
            zkteco.save_devices(devices, path)
            self.assertEqual(zkteco.load_devices(path), devices)

    def test_network_warning_detects_different_local_network(self):
        warning = zkteco.network_warning("192.168.1.25", "192.168.48.20")
        self.assertIn("Network mismatch", warning)

    def test_network_warning_is_quiet_on_same_local_network(self):
        self.assertIsNone(zkteco.network_warning("192.168.48.25", "192.168.48.20"))

    def test_ping_machine_retries_three_times_before_failing(self):
        calls = []

        class FailedPing:
            returncode = 1

        def runner(*args, **kwargs):
            calls.append((args, kwargs))
            return FailedPing()

        self.assertFalse(zkteco.ping_machine("192.168.48.20", runner=runner))
        self.assertEqual(len(calls), 3)

    def test_ping_machine_stops_when_a_retry_succeeds(self):
        calls = []

        class PingResult:
            def __init__(self, returncode):
                self.returncode = returncode

        def runner(*args, **kwargs):
            calls.append((args, kwargs))
            return PingResult(0 if len(calls) == 2 else 1)

        self.assertTrue(zkteco.ping_machine("192.168.48.20", runner=runner))
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
