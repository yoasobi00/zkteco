import tempfile
from threading import Event
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import zkteco


class ExtractionTests(unittest.TestCase):
    def test_cancel_during_csv_write_preserves_existing_output(self):
        cancel = Event()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "all.csv"
            output.write_text("existing export")

            def progress(message, percent):
                if percent and percent > 0:
                    cancel.set()

            with self.assertRaises(zkteco.ExtractionCancelled), patch("builtins.print"):
                zkteco.export_rows([(1, "Name", "2026-08-01", "08:00:00")] * 205,
                                   output, progress=progress, cancel_event=cancel)
            self.assertEqual(output.read_text(), "existing export")
            self.assertEqual(list(Path(tmpdir).iterdir()), [output])

    def test_cancel_after_device_read_disconnects_without_reading_users(self):
        cancel = Event()
        conn = Mock()

        def read():
            cancel.set()
            return []

        conn.get_attendance.side_effect = read
        factory = Mock()
        factory.return_value.connect.return_value = conn
        with self.assertRaises(zkteco.ExtractionCancelled), patch("builtins.print"):
            zkteco.fetch_attendance(zk_factory=factory, cancel_event=cancel)
        conn.disconnect.assert_called_once()
        conn.get_users.assert_not_called()

    def test_cancel_stops_ping_retries(self):
        cancel = Event()
        runner = Mock()

        def ping(*args, **kwargs):
            cancel.set()
            return Mock(returncode=1)

        runner.side_effect = ping
        with self.assertRaises(zkteco.ExtractionCancelled):
            zkteco.ping_machine("192.168.48.20", runner=runner, cancel_event=cancel)
        runner.assert_called_once()

    def test_cancel_before_export_does_not_connect(self):
        cancel = Event()
        cancel.set()
        with patch("zkteco.fetch_attendance") as fetch:
            with self.assertRaises(zkteco.ExtractionCancelled):
                zkteco.export_group(None, Path("unused.csv"), cancel_event=cancel)
        fetch.assert_not_called()

    def test_progress_completes_only_after_csv_is_saved(self):
        for records in ([], [(99, "2026-08-02 10:30:00")] * 205):
            with self.subTest(count=len(records)), tempfile.TemporaryDirectory() as tmpdir:
                output = Path(tmpdir) / "all.csv"
                events = []

                def progress(message, percent):
                    events.append((message, percent))
                    if percent == 100:
                        self.assertEqual(len(output.read_text().splitlines()), len(records) + 1)

                with patch("zkteco.fetch_attendance", return_value=(records, {})), patch("builtins.print"):
                    zkteco.export_group(None, output, groups={}, progress=progress)
                percentages = [percent for _, percent in events if percent is not None]
                self.assertEqual(percentages[0], 0)
                self.assertEqual(percentages[-1], 100)
                self.assertEqual(percentages, sorted(percentages))

    def test_failed_write_never_reports_completion(self):
        progress = Mock()
        with patch("zkteco.fetch_attendance", return_value=([], {})), patch("zkteco.export_rows", side_effect=OSError("disk full")), patch("builtins.print"):
            with self.assertRaises(OSError):
                zkteco.export_group(None, Path("unused.csv"), progress=progress)
        self.assertFalse(any(call.args[1] == 100 for call in progress.call_args_list))

    def test_device_read_failure_disconnects_and_reports_stage(self):
        conn = Mock()
        conn.get_attendance.side_effect = OSError("read failed")
        factory = Mock()
        factory.return_value.connect.return_value = conn
        progress = Mock()
        with patch("builtins.print"), self.assertRaises(OSError):
            zkteco.fetch_attendance(zk_factory=factory, progress=progress)
        conn.disconnect.assert_called_once()
        self.assertTrue(any("Reading attendance" in call.args[0] for call in progress.call_args_list))

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
