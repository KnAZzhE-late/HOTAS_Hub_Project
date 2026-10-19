from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from hotas_hub.calibration_dialog import (
    CalibrationDialog,
)
from hotas_hub.device_manager import (
    DeviceManager,
)
from hotas_hub.device_page import DevicePage
from hotas_hub.protocol import (
    DeviceSettings,
    DeviceType,
    Telemetry,
)


class DeviceNavItem(QFrame):
    """
    Элемент бокового меню устройства.

    Справа от кнопки расположен цветной сегмент:
    зелёный — устройство подключено;
    красный — устройство не подключено.
    """

    clicked = Signal()

    def __init__(
        self,
        title: str,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self._connected = False

        self.setObjectName("navItem")
        self.setFixedHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.button = QPushButton(title)
        self.button.setObjectName(
            "navButton"
        )
        self.button.setCheckable(True)
        self.button.setFixedHeight(44)

        self.status_segment = QFrame()
        self.status_segment.setObjectName(
            "deviceStatusSegment"
        )
        self.status_segment.setFixedSize(
            8,
            44,
        )

        self.status_segment.setProperty(
            "connected",
            False,
        )

        self.button.clicked.connect(
            self.clicked
        )

        layout.addWidget(
            self.button,
            1,
        )
        layout.addWidget(
            self.status_segment,
        )

    def set_checked(
        self,
        checked: bool,
    ) -> None:
        self.button.setChecked(checked)

    def set_connected(
        self,
        connected: bool,
    ) -> None:
        connected = bool(connected)

        if connected == self._connected:
            return

        self._connected = connected

        self.status_segment.setProperty(
            "connected",
            connected,
        )

        self.status_segment.style().unpolish(
            self.status_segment
        )
        self.status_segment.style().polish(
            self.status_segment
        )

        if connected:
            self.setToolTip(
                "Устройство подключено"
            )
        else:
            self.setToolTip(
                "Устройство не подключено"
            )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("HOTAS Hub")
        self.resize(1280, 820)
        self.setMinimumSize(1050, 680)

        self.manager = DeviceManager(self)

        self.pages: dict[
            DeviceType,
            DevicePage,
        ] = {}

        self.nav_items: dict[
            DeviceType,
            DeviceNavItem,
        ] = {}

        self._load_style()
        self._build_ui()
        self._connect_manager()

        # При запуске автоматически начинается
        # 30-секундный поиск устройств.
        self.manager.start()

    def _load_style(self) -> None:
        style_path = Path(
            __file__
        ).with_name("style.qss")

        if style_path.exists():
            self.setStyleSheet(
                style_path.read_text(
                    encoding="utf-8"
                )
            )

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # -------------------------------------------------
        # Боковая панель
        # -------------------------------------------------

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(240)

        sidebar_layout = QVBoxLayout(
            sidebar
        )
        sidebar_layout.setContentsMargins(
            14,
            20,
            14,
            20,
        )
        sidebar_layout.setSpacing(8)

        logo = QLabel("HOTAS")
        logo.setObjectName("logo")

        logo_subtitle = QLabel(
            "CONTROL HUB"
        )
        logo_subtitle.setObjectName(
            "logoSubtitle"
        )

        sidebar_layout.addWidget(logo)
        sidebar_layout.addWidget(
            logo_subtitle
        )
        sidebar_layout.addSpacing(24)

        self.stack = QStackedWidget()

        for device_type in (
            DeviceType.STICK,
            DeviceType.THROTTLE,
            DeviceType.PEDALS,
        ):
            nav_item = DeviceNavItem(
                device_type.title
            )

            page = DevicePage(
                device_type
            )

            nav_item.clicked.connect(
                lambda d=device_type:
                self._show_device(d)
            )

            page.calibration_requested.connect(
                self._open_single_calibration
            )
            page.inversion_changed.connect(
                self.manager.set_inversion
            )
            page.deadzone_changed.connect(
                self.manager.set_deadzone
            )
            page.filter_changed.connect(
                self.manager.set_filter
            )
            page.jitter_changed.connect(
                self.manager.set_jitter
            )
            page.atb_changed.connect(
                self.manager.set_atb
            )
            page.settings_requested.connect(
                self.manager.request_settings
            )

            self.nav_items[
                device_type
            ] = nav_item

            self.pages[
                device_type
            ] = page

            sidebar_layout.addWidget(
                nav_item
            )
            self.stack.addWidget(page)

        sidebar_layout.addStretch()

        # Кнопка повторного ограниченного поиска.
        self.scan_button = QPushButton(
            "Обновить устройства"
        )
        self.scan_button.setObjectName(
            "scanButton"
        )
        self.scan_button.clicked.connect(
            self._start_manual_scan
        )

        master_button = QPushButton(
            "Мастер калибровки"
        )
        master_button.setObjectName(
            "primaryButton"
        )
        master_button.clicked.connect(
            self._open_master_calibration
        )

        sidebar_layout.addWidget(
            self.scan_button
        )
        sidebar_layout.addWidget(
            master_button
        )

        version = QLabel(
            "HOTAS Hub 0.2.0"
        )
        version.setObjectName(
            "mutedLabel"
        )

        sidebar_layout.addWidget(version)

        root.addWidget(sidebar)
        root.addWidget(
            self.stack,
            1,
        )

        self.setStatusBar(
            QStatusBar()
        )

        self._show_device(
            DeviceType.STICK
        )

    def _connect_manager(self) -> None:
        self.manager.device_connected.connect(
            self._on_connected
        )
        self.manager.device_disconnected.connect(
            self._on_disconnected
        )
        self.manager.telemetry_received.connect(
            self._on_telemetry
        )
        self.manager.settings_received.connect(
            self._on_settings
        )

        self.manager.scan_started.connect(
            self._on_scan_started
        )
        self.manager.scan_finished.connect(
            self._on_scan_finished
        )

        self.manager.log_message.connect(
            lambda message:
            self.statusBar().showMessage(
                message,
                5000,
            )
        )

        self.manager.error_message.connect(
            lambda message:
            self.statusBar().showMessage(
                message,
                8000,
            )
        )

    def _show_device(
        self,
        device_type: DeviceType,
    ) -> None:
        page = self.pages[device_type]

        self.stack.setCurrentWidget(page)

        for (
            item_type,
            nav_item,
        ) in self.nav_items.items():
            nav_item.set_checked(
                item_type == device_type
            )

    def _start_manual_scan(self) -> None:
        """
        Запускает новое 30-секундное окно поиска.
        """
        self.manager.start_scan()

    def _on_scan_started(self) -> None:
        self.scan_button.setText(
            "Поиск устройств..."
        )
        self.scan_button.setEnabled(False)

        self.statusBar().showMessage(
            "Выполняется поиск HOTAS-устройств...",
            30_000,
        )

    def _on_scan_finished(self) -> None:
        self.scan_button.setText(
            "Обновить устройства"
        )
        self.scan_button.setEnabled(True)

        count = len(
            self.manager.connected_devices()
        )

        self.statusBar().showMessage(
            (
                "Поиск завершён. "
                f"Подключено устройств: {count}."
            ),
            5000,
        )

    def _on_connected(
        self,
        device_type: DeviceType,
        port: str,
        firmware: str,
    ) -> None:
        page = self.pages.get(
            device_type
        )

        if page:
            page.set_connected(
                True,
                port,
                firmware,
            )

        nav_item = self.nav_items.get(
            device_type
        )

        if nav_item:
            nav_item.set_connected(True)

    def _on_disconnected(
        self,
        device_type: DeviceType,
    ) -> None:
        page = self.pages.get(
            device_type
        )

        if page:
            page.set_connected(False)

        nav_item = self.nav_items.get(
            device_type
        )

        if nav_item:
            nav_item.set_connected(False)

    def _on_telemetry(
        self,
        telemetry: Telemetry,
    ) -> None:
        page = self.pages.get(
            telemetry.device_type
        )

        if page:
            page.update_telemetry(
                telemetry
            )

    def _on_settings(
        self,
        settings: DeviceSettings,
    ) -> None:
        page = self.pages.get(
            settings.device_type
        )

        if page:
            page.apply_settings(
                settings
            )

    def _open_single_calibration(
        self,
        device_type: DeviceType,
    ) -> None:
        if not self.manager.is_connected(
            device_type
        ):
            QMessageBox.warning(
                self,
                "Калибровка",
                (
                    f"{device_type.title} "
                    "не подключён."
                ),
            )
            return

        dialog = CalibrationDialog(
            self.manager,
            [device_type],
            self,
        )

        dialog.exec()

    def _open_master_calibration(self) -> None:
        devices = (
            self.manager.connected_devices()
        )

        if not devices:
            QMessageBox.warning(
                self,
                "Калибровка",
                (
                    "Нет подключённых "
                    "совместимых устройств."
                ),
            )
            return

        dialog = CalibrationDialog(
            self.manager,
            devices,
            self,
        )

        dialog.exec()

    def closeEvent(self, event) -> None:
        self.manager.stop()
        event.accept()
