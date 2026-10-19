from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal
from serial.tools import list_ports

from hotas_hub.protocol import (
    DeviceType,
    Identity,
)
from hotas_hub.serial_worker import SerialWorker


class DeviceManager(QObject):
    device_connected = Signal(object, str, str)
    device_disconnected = Signal(object)

    telemetry_received = Signal(object)
    settings_received = Signal(object)
    calibration_received = Signal(object)

    log_message = Signal(str)
    error_message = Signal(str)

    scan_started = Signal()
    scan_finished = Signal()

    SCAN_INTERVAL_MS = 1500
    DEFAULT_SCAN_DURATION_MS = 30_000

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._workers_by_port: dict[str, SerialWorker] = {}
        self._ports_by_type: dict[DeviceType, str] = {}

        self._scan_active = False

        # Периодический таймер используется только внутри
        # ограниченного окна поиска устройств.
        self._scan_timer = QTimer(self)
        self._scan_timer.setInterval(self.SCAN_INTERVAL_MS)
        self._scan_timer.timeout.connect(self.scan_ports)

        # После истечения этого таймера периодический поиск
        # COM-портов полностью прекращается.
        self._scan_timeout_timer = QTimer(self)
        self._scan_timeout_timer.setSingleShot(True)
        self._scan_timeout_timer.timeout.connect(
            self._finish_scan,
        )

    @property
    def scan_active(self) -> bool:
        return self._scan_active

    def start(self) -> None:
        """
        Запускает первоначальное сканирование COM-портов.

        Поиск продолжается 30 секунд, после чего
        автоматически прекращается.
        """
        self.start_scan()

    def start_scan(
        self,
        duration_ms: int = DEFAULT_SCAN_DURATION_MS,
    ) -> None:
        """
        Запускает или перезапускает ограниченное по времени
        сканирование COM-портов.
        """
        duration_ms = max(1000, int(duration_ms))

        # Если поиск уже шёл, его временное окно начинается
        # заново.
        self._scan_timer.stop()
        self._scan_timeout_timer.stop()

        self._scan_active = True
        self.scan_started.emit()

        self.log_message.emit(
            "Запущен поиск HOTAS-устройств..."
        )

        # Первая проверка выполняется немедленно.
        self.scan_ports()

        self._scan_timer.start()
        self._scan_timeout_timer.start(duration_ms)

    def _finish_scan(self) -> None:
        """
        Останавливает только поиск новых COM-портов.

        Уже подключённые SerialWorker продолжают работать.
        """
        if not self._scan_active:
            return

        self._scan_timer.stop()
        self._scan_timeout_timer.stop()

        self._scan_active = False
        self.scan_finished.emit()

        connected_count = len(self.connected_devices())

        self.log_message.emit(
            "Поиск устройств завершён. "
            f"Подключено: {connected_count}."
        )

    def stop(self) -> None:
        """
        Полностью останавливает менеджер и все SerialWorker.

        Вызывается при закрытии приложения.
        """
        self._scan_timer.stop()
        self._scan_timeout_timer.stop()
        self._scan_active = False

        workers = list(self._workers_by_port.values())

        for worker in workers:
            worker.stop()

        for worker in workers:
            worker.wait(1500)

        self._workers_by_port.clear()
        self._ports_by_type.clear()

    def scan_ports(self) -> None:
        """
        Выполняет один проход по доступным COM-портам.
        """
        if not self._scan_active:
            return

        try:
            available_ports = {
                port_info.device
                for port_info in list_ports.comports()
            }
        except Exception as exc:
            self.error_message.emit(
                f"Ошибка получения списка COM-портов: {exc}"
            )
            return

        # Если во время активного сканирования обнаружено,
        # что порт пропал, просим его worker завершиться.
        for port, worker in list(
            self._workers_by_port.items()
        ):
            if port not in available_ports:
                worker.stop()

        # Запускаем worker только для тех портов,
        # которые ещё не проверяются и не обслуживаются.
        for port in sorted(available_ports):
            if port in self._workers_by_port:
                continue

            self._start_worker(port)

    def _start_worker(self, port: str) -> None:
        worker = SerialWorker(port)

        worker.identified.connect(self._on_identified)
        worker.telemetry_received.connect(
            self.telemetry_received,
        )
        worker.settings_received.connect(
            self.settings_received,
        )
        worker.calibration_received.connect(
            self.calibration_received,
        )

        worker.message_received.connect(
            self._on_message,
        )
        worker.error_received.connect(
            self._on_error,
        )
        worker.disconnected.connect(
            self._on_disconnected,
        )

        self._workers_by_port[port] = worker
        worker.start()

        self.log_message.emit(
            f"Проверка порта {port}..."
        )

    def _on_identified(
        self,
        port: str,
        identity: Identity,
    ) -> None:
        old_port = self._ports_by_type.get(
            identity.device_type,
        )

        # Если устройство того же типа уже было найдено
        # на другом порту, старый worker останавливается.
        if old_port and old_port != port:
            old_worker = self._workers_by_port.get(
                old_port,
            )

            if old_worker:
                old_worker.stop()

        self._ports_by_type[identity.device_type] = port

        self.device_connected.emit(
            identity.device_type,
            port,
            identity.firmware,
        )

        self.log_message.emit(
            f"{identity.device_type.title}: "
            f"{port}, прошивка {identity.firmware}"
        )

    def _on_message(
        self,
        port: str,
        message: str,
    ) -> None:
        self.log_message.emit(
            f"{port}: {message}"
        )

    def _on_error(
        self,
        port: str,
        message: str,
    ) -> None:
        self.error_message.emit(
            f"{port}: {message}"
        )

    def _on_disconnected(self, port: str) -> None:
        worker = self._workers_by_port.pop(
            port,
            None,
        )

        if worker is None:
            return

        device_type = worker.device_type

        if (
            device_type is not None
            and self._ports_by_type.get(device_type) == port
        ):
            del self._ports_by_type[device_type]

            self.device_disconnected.emit(
                device_type,
            )

            self.log_message.emit(
                f"{device_type.title} отключён."
            )

        worker.deleteLater()

    def is_connected(
        self,
        device_type: DeviceType,
    ) -> bool:
        port = self._ports_by_type.get(device_type)

        if not port:
            return False

        worker = self._workers_by_port.get(port)

        return bool(
            worker
            and worker.isRunning()
            and worker.identity is not None
        )

    def connected_devices(self) -> list[DeviceType]:
        return [
            device_type
            for device_type in (
                DeviceType.STICK,
                DeviceType.THROTTLE,
                DeviceType.PEDALS,
            )
            if self.is_connected(device_type)
        ]

    def send(
        self,
        device_type: DeviceType,
        command: str,
    ) -> bool:
        port = self._ports_by_type.get(device_type)

        if not port:
            return False

        worker = self._workers_by_port.get(port)

        if not worker or not worker.isRunning():
            return False

        worker.send(command)
        return True

    def request_settings(
        self,
        device_type: DeviceType,
    ) -> None:
        self.send(
            device_type,
            "GET SETTINGS",
        )

    def set_inversion(
        self,
        device_type: DeviceType,
        axis: str,
        enabled: bool,
    ) -> None:
        self.send(
            device_type,
            f"SET INV {axis.upper()} {int(enabled)}",
        )

    def set_deadzone(
        self,
        device_type: DeviceType,
        axis: str,
        value: int,
    ) -> None:
        self.send(
            device_type,
            f"SET DZ {axis.upper()} {int(value)}",
        )

    def set_filter(
        self,
        device_type: DeviceType,
        number: int,
        value: float,
    ) -> None:
        self.send(
            device_type,
            f"SET FILTER {int(number)} {float(value):.3f}",
        )

    def set_jitter(
        self,
        device_type: DeviceType,
        value: int,
    ) -> None:
        self.send(
            device_type,
            f"SET JITTER {int(value)}",
        )

    def set_atb(
        self,
        device_type: DeviceType,
        number: int,
        enabled: bool,
    ) -> None:
        self.send(
            device_type,
            f"SET ATB {int(number)} {int(enabled)}",
        )

    def start_calibration(
        self,
        device_type: DeviceType,
    ) -> None:
        self.send(
            device_type,
            "CAL START",
        )

    def calibration_next(
        self,
        device_type: DeviceType,
    ) -> None:
        self.send(
            device_type,
            "CAL NEXT",
        )

    def calibration_cancel(
        self,
        device_type: DeviceType,
    ) -> None:
        self.send(
            device_type,
            "CAL CANCEL",
        )
