"""Reusable attendance extraction helpers.

The original project had one script per group.  This module keeps the
backwards-compatible helpers used by the existing tests, while exposing the
same operations to the desktop UI.
"""

from __future__ import annotations

import csv
import ipaddress
import json
import platform
import socket
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

try:
    from zk import ZK
except ImportError:  # pragma: no cover - the UI can still open without zk
    ZK = None


BASE_DIR = Path(__file__).resolve().parent
GROUPS_FILE = BASE_DIR / "groups.json"
DEVICES_FILE = BASE_DIR / "devices.json"
DEFAULT_IP = "192.168.48.20"
DEFAULT_PORT = 4370
DEFAULT_CUTOFF = "2026-08-01"

# Legacy device handle retained so callers can replace ``zkteco.zk`` in tests
# or in small scripts without needing to know about the newer fetch helper.
zk = ZK("192.168.48.28", port=DEFAULT_PORT, timeout=100) if ZK else None

# Kept for compatibility with the original zkteco.py tests.
TARGET_USER_IDS = {49, 62, 65, 75, 76, 106, 157, 176, 197, 233, 317, 331, 348, 349, 351, 353, 361, 373}
USER_NAMES = {
    49: "Nicole", 62: "Ritehly", 65: "Andrea", 75: "Nicely", 76: "Davy",
    106: "SY", 157: "Mark", 176: "James", 197: "Jerome", 233: "Jessie",
    317: "Weinand", 331: "Renee", 348: "Dan", 349: "Rica", 351: "Jen",
    353: "Dex", 361: "Kristine", 373: "Harrie",
}


def normalize_user_id(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None
    return None


def coerce_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _record_values(record: object) -> tuple[object, object]:
    if isinstance(record, (tuple, list)) and len(record) >= 2:
        return record[0], record[1]
    return getattr(record, "user_id", None), getattr(record, "timestamp", None)


def filter_records(
    records: Iterable[object],
    member_names: Mapping[int, str] | None = None,
    cutoff: datetime | None = None,
    include_all: bool = False,
) -> list[tuple[int, str, str, str]]:
    """Normalize, optionally filter, and sort device records.

    Returned values are ``(user_id, name, date, time)``.  ``include_all`` is
    used by the UI's all-logs export; groups filter against ``member_names``.
    """
    names = member_names or {}
    filtered: list[tuple[int, str, datetime]] = []
    for record in records:
        user_id, timestamp = _record_values(record)
        normalized_id = normalize_user_id(user_id)
        parsed_time = coerce_datetime(timestamp)
        if normalized_id is None or parsed_time is None:
            continue
        if not include_all and normalized_id not in names:
            continue
        if cutoff and parsed_time < cutoff:
            continue
        filtered.append((normalized_id, names.get(normalized_id, ""), parsed_time))

    filtered.sort(key=lambda item: (item[0], item[2]))
    return [
        (user_id, name, timestamp.strftime("%Y-%m-%d"), timestamp.strftime("%H:%M:%S"))
        for user_id, name, timestamp in filtered
    ]


def filter_and_sort_records(records: Iterable[object]) -> list[tuple[int, str, str]]:
    """Legacy Plato-style filter retained for existing callers/tests."""
    rows = filter_records(
        records,
        member_names=USER_NAMES,
        cutoff=None,
    )
    return [(user_id, date_value, time_value) for user_id, _name, date_value, time_value in rows]


def _default_groups() -> dict[str, dict]:
    return {
        "Plato": {
            "file": "plato_attendance_records.csv",
            "cutoff": DEFAULT_CUTOFF,
            "members": [{"id": user_id, "name": name} for user_id, name in USER_NAMES.items()],
        },
        "Aquaporin": {
            "file": "aquaporin_attendance_records.csv",
            "cutoff": "2026-07-26",
            "members": [{"id": 121, "name": "shunki-san"}, {"id": 159, "name": "danna-san"}],
        },
    }


def load_groups(path: Path = GROUPS_FILE) -> dict[str, dict]:
    """Load saved groups, falling back to the built-in Plato/Aquaporin setup."""
    if not path.exists():
        return _default_groups()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        groups = data.get("groups", data)
        if isinstance(groups, dict):
            return groups
    except (OSError, json.JSONDecodeError):
        pass
    return _default_groups()


def save_groups(groups: Mapping[str, dict], path: Path = GROUPS_FILE) -> None:
    path.write_text(json.dumps({"groups": groups}, indent=2), encoding="utf-8")


def _default_devices() -> dict[str, dict]:
    return {"Main machine": {"ip": DEFAULT_IP, "port": DEFAULT_PORT}}


def load_devices(path: Path = DEVICES_FILE) -> dict[str, dict]:
    """Load the labeled biometrics machines available to the UI."""
    if not path.exists():
        return _default_devices()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        devices = data.get("devices", data)
        if isinstance(devices, dict):
            valid_devices = {}
            for label, device in devices.items():
                if isinstance(device, Mapping) and str(device.get("ip", "")).strip():
                    try:
                        port = int(device.get("port", DEFAULT_PORT))
                    except (TypeError, ValueError):
                        port = DEFAULT_PORT
                    valid_devices[str(label)] = {"ip": str(device["ip"]).strip(), "port": port}
            if valid_devices:
                return valid_devices
    except (OSError, json.JSONDecodeError):
        pass
    return _default_devices()


def save_devices(devices: Mapping[str, dict], path: Path = DEVICES_FILE) -> None:
    path.write_text(json.dumps({"devices": devices}, indent=2), encoding="utf-8")


def detect_local_ip(target_ip: str, port: int = DEFAULT_PORT) -> str | None:
    """Find the local IPv4 address used for the route to a machine.

    UDP connect does not send attendance data; it only lets the operating
    system choose the interface and report its local address.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((target_ip, port))
        return str(sock.getsockname()[0])
    except (OSError, ValueError):
        return None
    finally:
        sock.close()


def network_warning(local_ip: str | None, machine_ip: str) -> str | None:
    """Return a user-facing warning when the local and machine networks differ."""
    try:
        local_address = ipaddress.ip_address(local_ip) if local_ip else None
        machine_address = ipaddress.ip_address(machine_ip)
    except ValueError:
        return f"⚠ The machine IP address '{machine_ip}' is not valid. Extraction may fail."

    if local_address is None:
        return "⚠ Unable to detect this computer's local IP address. Check the network before extracting."
    if local_address == machine_address:
        return f"⚠ This computer and the machine have the same IP address ({machine_ip}). Resolve the address conflict before extracting."
    if local_address.version == machine_address.version == 4:
        local_network = ".".join(str(local_address).split(".")[:3])
        machine_network = ".".join(str(machine_address).split(".")[:3])
        if local_network != machine_network:
            return (
                f"⚠ Network mismatch: this computer is {local_address}, but {machine_address} "
                "appears to be on a different local network. Extraction may fail; check Wi-Fi, Ethernet, or VPN."
            )
    return None


def machine_network_warning(machine_ip: str, port: int = DEFAULT_PORT) -> str | None:
    """Check the selected machine's network and return a warning, if needed."""
    return network_warning(detect_local_ip(machine_ip, port), machine_ip)


def ping_machine(
    machine_ip: str,
    attempts: int = 3,
    timeout: float = 1.0,
    runner: Callable[..., object] | None = None,
) -> bool:
    """Ping a machine up to ``attempts`` times and report whether it responds."""
    try:
        ipaddress.ip_address(machine_ip)
    except ValueError:
        return False
    if attempts < 1:
        return False

    if platform.system().lower() == "windows":
        command = ["ping", "-n", "1", "-w", str(max(1, int(timeout * 1000))), machine_ip]
    elif platform.system().lower() == "darwin":
        command = ["ping", "-c", "1", "-W", str(max(1, int(timeout * 1000))), machine_ip]
    else:
        command = ["ping", "-c", "1", "-W", str(max(1, int(timeout))), machine_ip]

    execute = runner or subprocess.run
    for _attempt in range(attempts):
        try:
            result = execute(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=timeout + 0.5,
            )
            if getattr(result, "returncode", 1) == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            continue
    return False


def group_members(group: Mapping[str, object]) -> dict[int, str]:
    result: dict[int, str] = {}
    for member in group.get("members", []):
        if isinstance(member, Mapping):
            user_id = normalize_user_id(member.get("id"))
            name = str(member.get("name", "")).strip()
            if user_id is not None:
                result[user_id] = name
    return result


def load_records_from_csv(path: Path) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    if not path.exists():
        return rows
    with path.open(mode="r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            user_id = normalize_user_id(row.get("User ID"))
            timestamp = row.get("Timestamp")
            if user_id is not None and timestamp:
                rows.append((user_id, timestamp))
    return rows


def fetch_attendance(
    ip: str = DEFAULT_IP,
    port: int = DEFAULT_PORT,
    zk_factory: Callable[..., object] | None = None,
) -> tuple[list[object], dict[int, str]]:
    """Read attendance and device user names, returning both as plain data."""
    factory = zk_factory or ZK
    if factory is None:
        raise RuntimeError("The pyzk package is not installed. Install it with: pip install pyzk")
    device = factory(ip, port=port, timeout=100)
    conn = device.connect()
    if not conn:
        raise ConnectionError("The device connection failed")
    try:
        attendance = list(conn.get_attendance())
        names: dict[int, str] = {}
        try:
            for user in conn.get_users():
                user_id = normalize_user_id(getattr(user, "user_id", None))
                if user_id is not None:
                    names[user_id] = str(getattr(user, "name", "") or "")
        except (AttributeError, OSError):
            # Some devices expose attendance but not the user directory.
            pass
        return attendance, names
    finally:
        conn.disconnect()


def export_rows(rows: Sequence[tuple[int, str, str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["User ID", "Name", "Date", "Time"])
        writer.writerows(rows)


def export_group(
    group_name: str | None,
    output_path: Path,
    ip: str = DEFAULT_IP,
    port: int = DEFAULT_PORT,
    groups: Mapping[str, dict] | None = None,
) -> int:
    """Fetch, filter, and export one group or all device logs."""
    groups = groups or load_groups()
    raw_records, device_names = fetch_attendance(ip, port)
    if group_name is None:
        rows = filter_records(raw_records, member_names=device_names, include_all=True)
    else:
        group = groups[group_name]
        members = group_members(group)
        # Names explicitly maintained in a group take precedence over device names.
        cutoff = coerce_datetime(group.get("cutoff")) if group.get("cutoff") else None
        rows = filter_records(raw_records, member_names=members, cutoff=cutoff)
    export_rows(rows, output_path)
    return len(rows)


def export_attendance_records(path: Path = BASE_DIR / "attendance_records.csv") -> None:
    """Legacy export entry point used by the original tests and scripts."""
    try:
        conn = zk.connect() if zk else None
        if not conn:
            print("Connection failed; no export performed.")
            return
        try:
            raw_records = list(conn.get_attendance())
        finally:
            conn.disconnect()
    except Exception as exc:
        print(f"An error occurred while reading from the device: {exc}")
        return

    rows = filter_records(raw_records, member_names=USER_NAMES)
    # Preserve the old three-column file shape for callers of this function.
    with path.open(mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["User ID", "Date", "Time"])
        writer.writerows((user_id, date_value, time_value) for user_id, _name, date_value, time_value in rows)


if __name__ == "__main__":
    export_attendance_records()
