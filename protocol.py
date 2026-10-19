from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DeviceType(str, Enum):
    STICK = "STICK"
    THROTTLE = "THROTTLE"
    PEDALS = "PEDALS"

    @property
    def title(self) -> str:
        return {
            DeviceType.STICK: "РУС",
            DeviceType.THROTTLE: "РУД",
            DeviceType.PEDALS: "Педали",
        }[self]


@dataclass(slots=True)
class Identity:
    device_type: DeviceType
    firmware: str
    protocol: int


@dataclass(slots=True)
class Telemetry:
    device_type: DeviceType
    axes: dict[str, int] = field(default_factory=dict)
    buttons: int = 0
    hat: int = -1


@dataclass(slots=True)
class DeviceSettings:
    device_type: DeviceType
    inversions: dict[str, bool] = field(default_factory=dict)
    deadzones: dict[str, int] = field(default_factory=dict)
    filters: list[float] = field(default_factory=lambda: [0.35, 0.15])
    jitter: int = 15
    atb: list[bool] = field(default_factory=list)


@dataclass(slots=True)
class CalibrationEvent:
    device_type: DeviceType
    event: str
    axis: str = ""
    minimum: int | None = None
    maximum: int | None = None


def parse_identity(line: str) -> Identity | None:
    # ID|HFB|STICK|2026.11|2
    parts = line.strip().split("|")

    if len(parts) != 5:
        return None

    if parts[0] != "ID" or parts[1] != "HFB":
        return None

    try:
        return Identity(
            device_type=DeviceType(parts[2]),
            firmware=parts[3],
            protocol=int(parts[4]),
        )
    except (ValueError, KeyError):
        return None


def parse_telemetry(line: str) -> Telemetry | None:
    # DATA|STICK|X|Y|Z|RX|RY|RZ|HAT|BUTTON_MASK
    parts = line.strip().split("|")

    if len(parts) < 3 or parts[0] != "DATA":
        return None

    try:
        device_type = DeviceType(parts[1])

        if device_type in (DeviceType.STICK, DeviceType.THROTTLE):
            if len(parts) != 10:
                return None

            return Telemetry(
                device_type=device_type,
                axes={
                    "X": int(parts[2]),
                    "Y": int(parts[3]),
                    "Z": int(parts[4]),
                    "RX": int(parts[5]),
                    "RY": int(parts[6]),
                    "RZ": int(parts[7]),
                },
                hat=int(parts[8]),
                buttons=int(parts[9], 16),
            )

        if device_type == DeviceType.PEDALS:
            if len(parts) != 5:
                return None

            return Telemetry(
                device_type=device_type,
                axes={
                    "RUDDER": int(parts[2]),
                    "RX": int(parts[3]),
                    "RY": int(parts[4]),
                },
            )

    except (ValueError, KeyError):
        return None

    return None


def _parse_csv_bool_map(
    axes: list[str],
    value: str,
) -> dict[str, bool]:
    values = value.split(",")

    result: dict[str, bool] = {}

    for index, axis in enumerate(axes):
        if index < len(values):
            result[axis] = values[index].strip() == "1"

    return result


def _parse_csv_int_map(
    axes: list[str],
    value: str,
) -> dict[str, int]:
    values = value.split(",")

    result: dict[str, int] = {}

    for index, axis in enumerate(axes):
        if index < len(values):
            try:
                result[axis] = int(values[index])
            except ValueError:
                result[axis] = 0

    return result


def parse_settings(line: str) -> DeviceSettings | None:
    # CFG|STICK|INV=0,1,0,0,0,1|FILTER=0.35,0.15|
    # JITTER=15|ATB=0,0|DZ=0,0,0,0,0,0

    parts = line.strip().split("|")

    if len(parts) < 3 or parts[0] != "CFG":
        return None

    try:
        device_type = DeviceType(parts[1])
    except ValueError:
        return None

    if device_type in (DeviceType.STICK, DeviceType.THROTTLE):
        axes = ["X", "Y", "Z", "RX", "RY", "RZ"]
    else:
        axes = ["RUDDER", "RX", "RY"]

    values: dict[str, str] = {}

    for item in parts[2:]:
        if "=" not in item:
            continue

        key, value = item.split("=", 1)
        values[key.strip().upper()] = value.strip()

    settings = DeviceSettings(device_type=device_type)

    if "INV" in values:
        settings.inversions = _parse_csv_bool_map(
            axes,
            values["INV"],
        )

    if "DZ" in values:
        settings.deadzones = _parse_csv_int_map(
            axes,
            values["DZ"],
        )

    if "FILTER" in values:
        try:
            settings.filters = [
                float(value)
                for value in values["FILTER"].split(",")
            ]
        except ValueError:
            pass

    if "JITTER" in values:
        try:
            settings.jitter = int(values["JITTER"])
        except ValueError:
            pass

    if "ATB" in values:
        settings.atb = [
            value.strip() == "1"
            for value in values["ATB"].split(",")
        ]

    return settings


def parse_calibration(line: str) -> CalibrationEvent | None:
    # CAL|STICK|BEGIN|X
    # CAL|STICK|VALUE|X|100|900
    # CAL|STICK|DONE
    # CAL|STICK|CANCELLED

    parts = line.strip().split("|")

    if len(parts) < 3 or parts[0] != "CAL":
        return None

    try:
        device_type = DeviceType(parts[1])
    except ValueError:
        return None

    event = parts[2].upper()
    axis = parts[3].upper() if len(parts) >= 4 else ""

    minimum = None
    maximum = None

    if event == "VALUE" and len(parts) >= 6:
        try:
            minimum = int(parts[4])
            maximum = int(parts[5])
        except ValueError:
            return None

    return CalibrationEvent(
        device_type=device_type,
        event=event,
        axis=axis,
        minimum=minimum,
        maximum=maximum,
    )


def parse_line(line: str) -> tuple[str, Any] | None:
    line = line.strip()

    if not line:
        return None

    if line.startswith("ID|"):
        value = parse_identity(line)
        return ("identity", value) if value else None

    if line.startswith("DATA|"):
        value = parse_telemetry(line)
        return ("telemetry", value) if value else None

    if line.startswith("CFG|"):
        value = parse_settings(line)
        return ("settings", value) if value else None

    if line.startswith("CAL|"):
        value = parse_calibration(line)
        return ("calibration", value) if value else None

    if line.startswith("ACK|"):
        return "ack", line

    if line.startswith("ERR|"):
        return "error", line

    if line.startswith("WARN|"):
        return "warning", line

    return "text", line
