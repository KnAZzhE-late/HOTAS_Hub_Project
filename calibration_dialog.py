from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from hotas_hub.device_manager import DeviceManager
from hotas_hub.protocol import CalibrationEvent, DeviceType


class CalibrationDialog(QDialog):
    def __init__(
        self,
        manager: DeviceManager,
        devices: list[DeviceType],
        parent=None,
    ) -> None:
        super().__init__(parent)

        self.manager = manager
        self.devices = [
            device
            for device in devices
            if manager.is_connected(device)
        ]

        self.current_index = -1
        self.current_device: DeviceType | None = None
        self.calibration_started = False

        self.setWindowTitle("Мастер калибровки")
        self.setMinimumSize(570, 360)
        self.setModal(True)

        self._build_ui()

        self.manager.calibration_received.connect(
            self._on_calibration_event
        )
        self.manager.device_disconnected.connect(
            self._on_disconnected
        )

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 26, 26, 26)
        layout.setSpacing(16)

        title = QLabel("Мастер калибровки HOTAS")
        title.setObjectName("dialogTitle")

        self.device_label = QLabel("Готов к запуску")
        self.device_label.setObjectName("sectionTitle")

        self.axis_label = QLabel(
            "После запуска следуйте инструкциям."
        )
        self.axis_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.axis_label.setWordWrap(True)

        self.range_label = QLabel("")
        self.range_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.range_label.setObjectName("calibrationRange")

        self.progress = QProgressBar()
        self.progress.setRange(0, max(1, len(self.devices)))
        self.progress.setValue(0)

        layout.addWidget(title)
        layout.addWidget(self.device_label)
        layout.addWidget(self.axis_label, 1)
        layout.addWidget(self.range_label)
        layout.addWidget(self.progress)

        button_layout = QHBoxLayout()

        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.clicked.connect(self.reject)

        self.next_button = QPushButton("Начать")
        self.next_button.setObjectName("primaryButton")
        self.next_button.clicked.connect(self._next_clicked)

        button_layout.addWidget(self.cancel_button)
        button_layout.addStretch()
        button_layout.addWidget(self.next_button)

        layout.addLayout(button_layout)

    def _next_clicked(self) -> None:
        if not self.devices:
            QMessageBox.information(
                self,
                "Калибровка",
                "Нет подключённых устройств.",
            )
            return

        if not self.calibration_started:
            self.calibration_started = True
            self.next_button.setText("Сохранить ось и продолжить")
            self._start_next_device()
            return

        if self.current_device:
            self.manager.calibration_next(
                self.current_device,
            )

    def _start_next_device(self) -> None:
        self.current_index += 1

        while self.current_index < len(self.devices):
            device = self.devices[self.current_index]

            if self.manager.is_connected(device):
                self.current_device = device

                self.device_label.setText(
                    f"Устройство: {device.title}"
                )
                self.axis_label.setText(
                    "Запуск режима калибровки..."
                )
                self.range_label.clear()

                self.manager.start_calibration(device)
                return

            self.current_index += 1

        self.current_device = None
        self.progress.setValue(len(self.devices))
        self.device_label.setText("Калибровка завершена")
        self.axis_label.setText(
            "Все подключённые устройства откалиброваны."
        )
        self.range_label.clear()
        self.next_button.setText("Закрыть")
        self.next_button.clicked.disconnect()
        self.next_button.clicked.connect(self.accept)

    def _on_calibration_event(
        self,
        event: CalibrationEvent,
    ) -> None:
        if event.device_type != self.current_device:
            return

        if event.event == "BEGIN":
            self.axis_label.setText(
                f"Переместите ось {event.axis} "
                "по всему физическому диапазону.\n"
                "После этого нажмите «Сохранить ось "
                "и продолжить»."
            )
            return

        if event.event == "VALUE":
            self.range_label.setText(
                f"{event.axis}: "
                f"min = {event.minimum}, "
                f"max = {event.maximum}"
            )
            return

        if event.event == "DONE":
            self.progress.setValue(self.current_index + 1)
            self._start_next_device()
            return

        if event.event == "CANCELLED":
            self.axis_label.setText("Калибровка отменена.")

    def _on_disconnected(
        self,
        device_type: DeviceType,
    ) -> None:
        if device_type == self.current_device:
            self._start_next_device()

    def reject(self) -> None:
        if self.current_device:
            self.manager.calibration_cancel(
                self.current_device,
            )

        super().reject()
