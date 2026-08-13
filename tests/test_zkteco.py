import tempfile
import unittest
from pathlib import Path

import zkteco


class ZkTecoFilteringTests(unittest.TestCase):
    def test_filter_and_sort_records_for_target_ids(self):
        records = [
            (176, "2024-05-05 08:00:00"),
            (62, "2024-04-01 08:00:00"),
            (200, "2024-04-02 08:00:00"),
            (75, "2024-04-01 09:00:00"),
            (76, "2024-03-01 07:00:00"),
        ]

        filtered = zkteco.filter_and_sort_records(records)

        self.assertEqual(filtered, [
            (62, "2024-04-01", "08:00:00"),
            (75, "2024-04-01", "09:00:00"),
            (76, "2024-03-01", "07:00:00"),
            (176, "2024-05-05", "08:00:00"),
        ])

    def test_export_does_not_write_when_device_is_unreachable(self):
        class BrokenConnection:
            def connect(self):
                raise OSError("device unreachable")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "attendance.csv"
            path.write_text("existing-data", encoding="utf-8")

            original_zk = zkteco.zk
            zkteco.zk = BrokenConnection()
            try:
                zkteco.export_attendance_records(path)
            finally:
                zkteco.zk = original_zk

            self.assertEqual(path.read_text(encoding="utf-8"), "existing-data")


if __name__ == "__main__":
    unittest.main()
