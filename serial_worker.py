from __future__ import annotations

import queue
import threading
import time

import serial
from PySide6.QtCore import QThread, Signal

from hotas_hub.protocol import (
    CalibrationEvent,
    DeviceSettings,
    DeviceType,
    Identity,
    Telemetry,
    parse_line,
)


class SerialWorker(QThread):
    identified = Signal(str, object)
    telemetry_received = Signal(object)
    settings_received = Signal(object)
    calibration_received = Signal(object)

    message_received = Signal(str, str)
    error_received = Signal(str, str)
    disconnected = Signal(str)

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self.port = port
        self.baudrate = baudrate

        self.identity: Identity | None = None
        self.device_type: DeviceType | None = None

        self._commands: queue.Queue[str] = queue.Queue()
        self._stop_event = threading.Event()
        self._serial: serial.Serial | None = None

    def send(self, command: str) -> None:
        command = command.strip()

        if command:
            self._commands.put(command)

    def stop(self) -> None:
        self._stop_event.set()

    def _write(self, command: str) -> None:
        if not self._serial or not self._serial.is_open:
            return

        packet = (command.strip() + "\n").encode(
            "utf-8",
            errors="ignore",
        )

        self._serial.write(packet)
        self._serial.flush()

    def _handle_line(self, line: str) -> None:
        parsed = parse_line(line)

        if parsed is None:
            return

        kind, value = parsed

        if kind == "identity":
            identity: Identity = value

            self.identity = identity
            self.device_type = identity.device_type

            self.identified.emit(self.port, identity)

            self._write("GET SETTINGS")
            self._write("RATE 30")
            self._write("STREAM 1")
            return

        if kind == "telemetry":
            telemetry: Telemetry = value
            self.telemetry_received.emit(telemetry)
            return

        if kind == "settings":
            settings: DeviceSettings = value
            self.settings_received.emit(settings)
            return

        if kind == "calibration":
            event: CalibrationEvent = value
            self.calibration_received.emit(event)
            return

        if kind == "error":
            self.error_received.emit(self.port, str(value))
            return

        self.message_received.emit(self.port, str(value))

    def run(self) -> None:
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.05,
                write_timeout=0.5,
            )

            # Pro Micro обычно перезапускается после открытия CDC-порта.
            time.sleep(1.8)

            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()

            self._write("IDENT")

            next_identification = time.monotonic() + 1.0
            identification_deadline = time.monotonic() + 5.0

            while not self._stop_event.is_set():
                while True:
                    try:
                        command = self._commands.get_nowait()
                    except queue.Empty:
                        break

                    self._write(command)

                try:
                    raw = self._serial.readline()
                except serial.SerialException:
                    break

                if raw:
                    line = raw.decode(
                        "utf-8",
                        errors="replace",
                    ).strip()

                    if line:
                        self._handle_line(line)

                now = time.monotonic()

                if self.identity is None:
                    if now >= identification_deadline:
                        break

                    if now >= next_identification:
                        self._write("IDENT")
                        next_identification = now + 1.0

        except (serial.SerialException, OSError) as exc:
            self.error_received.emit(self.port, str(exc))

        finally:
            try:
                if self._serial and self._serial.is_open:
                    self._write("STREAM 0")
                    self._serial.close()
            except (serial.SerialException, OSError):
                pass

            self.disconnected.emit(self.port)
