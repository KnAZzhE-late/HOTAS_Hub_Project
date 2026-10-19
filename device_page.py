from __future__ import annotations

from functools import partial

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from hotas_hub.protocol import (
    DeviceSettings,
    DeviceType,
    Telemetry,
)
from hotas_hub.widgets import (
    AxisBar,
    ButtonGrid,
    XYAxisWidget,
)


class DevicePage(QWidget):
    calibration_requested = Signal(object)

    inversion_changed = Signal(
        object,
        str,
        bool,
    )
    deadzone_changed = Signal(
        object,
        str,
        int,
    )
    filter_changed = Signal(
        object,
        int,
        float,
    )
    jitter_changed = Signal(
        object,
        int,
    )
    atb_changed = Signal(
        object,
        int,
        bool,
    )
    settings_requested = Signal(object)

    def __init__(
        self,
        device_type: DeviceType,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self.device_type = device_type
        self._updating_settings = False
        self._connected = False

        if device_type in (
            DeviceType.STICK,
            DeviceType.THROTTLE,
        ):
            self.axes = [
                "X",
                "Y",
                "Z",
                "RX",
                "RY",
                "RZ",
            ]
        else:
            self.axes = [
                "RUDDER",
                "RX",
                "RY",
            ]

        self.button_count = {
            DeviceType.STICK: 28,
            DeviceType.THROTTLE: 31,
            DeviceType.PEDALS: 0,
        }[device_type]

        self.axis_bars: dict[
            str,
            AxisBar,
        ] = {}

        self.inversion_boxes: dict[
            str,
            QCheckBox,
        ] = {}

        self.deadzone_boxes: dict[
            str,
            QSpinBox,
        ] = {}

        self.atb_boxes: list[
            QCheckBox
        ] = []

        self._build_ui()
        self.set_connected(False)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # -------------------------------------------------
        # Верхняя панель страницы
        # -------------------------------------------------

        header = QFrame()
        header.setObjectName("pageHeader")

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(
            24,
            14,
            24,
            14,
        )
        header_layout.setSpacing(10)

        title = QLabel(
            self.device_type.title
        )
        title.setObjectName("pageTitle")

        self.port_label = QLabel("")
        self.port_label.setObjectName(
            "mutedLabel"
        )

        self.status_label = QLabel(
            "Не подключено"
        )
        self.status_label.setObjectName(
            "connectionStatus"
        )

        # Индивидуальная калибровка теперь находится
        # в верхней части страницы.
        self.calibrate_button = QPushButton(
            "Калибровать"
        )
        self.calibrate_button.setObjectName(
            "primaryButton"
        )
        self.calibrate_button.clicked.connect(
            lambda: self.calibration_requested.emit(
                self.device_type,
            )
        )

        self.refresh_button = QPushButton(
            "Считать настройки"
        )
        self.refresh_button.clicked.connect(
            lambda: self.settings_requested.emit(
                self.device_type,
            )
        )

        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(
            self.port_label
        )
        header_layout.addWidget(
            self.status_label
        )
        header_layout.addWidget(
            self.calibrate_button
        )
        header_layout.addWidget(
            self.refresh_button
        )

        root.addWidget(header)

        # -------------------------------------------------
        # Прокручиваемое содержимое страницы
        # -------------------------------------------------

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(
            QFrame.Shape.NoFrame
        )

        content = QWidget()

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(
            20,
            20,
            20,
            30,
        )
        content_layout.setSpacing(16)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(16)

        # Квадратный индикатор X/Y нужен для РУС и РУД.
        if self.device_type in (
            DeviceType.STICK,
            DeviceType.THROTTLE,
        ):
            xy_title = (
                "Положение РУС"
                if self.device_type
                == DeviceType.STICK
                else "Мини-стик РУД"
            )

            self.xy_widget = XYAxisWidget(
                xy_title
            )

            top_layout.addWidget(
                self.xy_widget
            )

        # -------------------------------------------------
        # Линейные индикаторы осей
        # -------------------------------------------------

        axes_card = QFrame()
        axes_card.setObjectName("card")

        axes_layout = QVBoxLayout(
            axes_card
        )
        axes_layout.setContentsMargins(
            16,
            16,
            16,
            16,
        )
        axes_layout.setSpacing(6)

        axes_title = QLabel(
            "Состояние осей"
        )
        axes_title.setObjectName(
            "sectionTitle"
        )

        axes_layout.addWidget(
            axes_title
        )

        if self.device_type in (
            DeviceType.STICK,
            DeviceType.THROTTLE,
        ):
            displayed_axes = [
                "Z",
                "RX",
                "RY",
                "RZ",
            ]
        else:
            displayed_axes = list(
                self.axes
            )

        for axis in displayed_axes:
            bar = AxisBar(axis)

            self.axis_bars[axis] = bar
            axes_layout.addWidget(bar)

        axes_layout.addStretch()

        top_layout.addWidget(
            axes_card,
            1,
        )

        content_layout.addLayout(
            top_layout
        )

        # -------------------------------------------------
        # Индикация кнопок
        # -------------------------------------------------

        if self.button_count:
            self.button_grid = ButtonGrid(
                self.button_count
            )

            content_layout.addWidget(
                self.button_grid
            )
        else:
            self.button_grid = None

        # -------------------------------------------------
        # Настройки устройства
        # -------------------------------------------------

        settings_card = QFrame()
        settings_card.setObjectName("card")

        settings_layout = QVBoxLayout(
            settings_card
        )
        settings_layout.setContentsMargins(
            18,
            18,
            18,
            18,
        )
        settings_layout.setSpacing(12)

        settings_title = QLabel(
            "Настройки устройства"
        )
        settings_title.setObjectName(
            "sectionTitle"
        )

        settings_layout.addWidget(
            settings_title
        )

        settings_grid = QGridLayout()
        settings_grid.setHorizontalSpacing(18)
        settings_grid.setVerticalSpacing(8)

        settings_grid.addWidget(
            QLabel("Ось"),
            0,
            0,
        )
        settings_grid.addWidget(
            QLabel("Инверсия"),
            0,
            1,
        )
        settings_grid.addWidget(
            QLabel("Мёртвая зона"),
            0,
            2,
        )

        for row, axis in enumerate(
            self.axes,
            start=1,
        ):
            axis_label = QLabel(axis)
            axis_label.setObjectName(
                "axisName"
            )

            inversion = QCheckBox()

            inversion.toggled.connect(
                partial(
                    self._on_inversion,
                    axis,
                )
            )

            deadzone = QSpinBox()
            deadzone.setRange(0, 8000)
            deadzone.setSingleStep(50)
            deadzone.setSuffix(" ед.")

            deadzone.editingFinished.connect(
                partial(
                    self._on_deadzone,
                    axis,
                )
            )

            self.inversion_boxes[
                axis
            ] = inversion

            self.deadzone_boxes[
                axis
            ] = deadzone

            settings_grid.addWidget(
                axis_label,
                row,
                0,
            )
            settings_grid.addWidget(
                inversion,
                row,
                1,
            )
            settings_grid.addWidget(
                deadzone,
                row,
                2,
            )

        filters_frame = QFrame()
        filters_frame.setObjectName(
            "settingsSubFrame"
        )

        filters_form = QFormLayout(
            filters_frame
        )
        filters_form.setContentsMargins(
            14,
            8,
            14,
            8,
        )

        self.filter_1 = QDoubleSpinBox()
        self.filter_1.setRange(
            0.01,
            1.0,
        )
        self.filter_1.setSingleStep(0.01)
        self.filter_1.setDecimals(2)

        self.filter_1.editingFinished.connect(
            lambda: self._on_filter(
                1,
                self.filter_1.value(),
            )
        )

        self.filter_2 = QDoubleSpinBox()
        self.filter_2.setRange(
            0.01,
            1.0,
        )
        self.filter_2.setSingleStep(0.01)
        self.filter_2.setDecimals(2)

        self.filter_2.editingFinished.connect(
            lambda: self._on_filter(
                2,
                self.filter_2.value(),
            )
        )

        self.jitter = QSpinBox()
        self.jitter.setRange(0, 2000)
        self.jitter.setSuffix(" ед.")

        self.jitter.editingFinished.connect(
            lambda: self._on_jitter(
                self.jitter.value()
            )
        )

        filters_form.addRow(
            "Фильтр 1:",
            self.filter_1,
        )
        filters_form.addRow(
            "Фильтр 2:",
            self.filter_2,
        )
        filters_form.addRow(
            "Гистерезис:",
            self.jitter,
        )

        settings_grid.addWidget(
            filters_frame,
            1,
            3,
            max(3, len(self.axes)),
            1,
        )

        settings_layout.addLayout(
            settings_grid
        )

        if self.device_type == DeviceType.STICK:
            self._add_atb(
                settings_layout,
                "ATB 1: мини-стик → HAT",
            )
            self._add_atb(
                settings_layout,
                "ATB 2: тормоз → кнопка",
            )

        elif (
            self.device_type
            == DeviceType.THROTTLE
        ):
            self._add_atb(
                settings_layout,
                "ATB 1: мини-стик → HAT",
            )

        content_layout.addWidget(
            settings_card
        )

        content_layout.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll)

    def _add_atb(
        self,
        layout: QVBoxLayout,
        text: str,
    ) -> None:
        number = len(self.atb_boxes) + 1

        checkbox = QCheckBox(text)

        checkbox.toggled.connect(
            lambda enabled, n=number:
            self._on_atb(
                n,
                enabled,
            )
        )

        self.atb_boxes.append(
            checkbox
        )

        layout.addWidget(checkbox)

    def _on_inversion(
        self,
        axis: str,
        enabled: bool,
    ) -> None:
        if self._updating_settings:
            return

        self.inversion_changed.emit(
            self.device_type,
            axis,
            enabled,
        )

    def _on_deadzone(
        self,
        axis: str,
    ) -> None:
        if self._updating_settings:
            return

        self.deadzone_changed.emit(
            self.device_type,
            axis,
            self.deadzone_boxes[
                axis
            ].value(),
        )

    def _on_filter(
        self,
        number: int,
        value: float,
    ) -> None:
        if self._updating_settings:
            return

        self.filter_changed.emit(
            self.device_type,
            number,
            value,
        )

    def _on_jitter(
        self,
        value: int,
    ) -> None:
        if self._updating_settings:
            return

        self.jitter_changed.emit(
            self.device_type,
            value,
        )

    def _on_atb(
        self,
        number: int,
        enabled: bool,
    ) -> None:
        if self._updating_settings:
            return

        self.atb_changed.emit(
            self.device_type,
            number,
            enabled,
        )

    def set_connected(
        self,
        connected: bool,
        port: str = "",
        firmware: str = "",
    ) -> None:
        self._connected = bool(connected)

        self.status_label.setText(
            "Подключено"
            if connected
            else "Не подключено"
        )

        self.status_label.setProperty(
            "connected",
            connected,
        )

        self.status_label.style().unpolish(
            self.status_label
        )
        self.status_label.style().polish(
            self.status_label
        )

        # Без подключения эти кнопки не должны
        # отправлять команды в устройство.
        self.calibrate_button.setEnabled(
            connected
        )
        self.refresh_button.setEnabled(
            connected
        )

        if connected:
            self.port_label.setText(
                f"{port} · FW {firmware}"
            )
        else:
            self.port_label.clear()
            self.reset_telemetry()

    def update_telemetry(
        self,
        telemetry: Telemetry,
    ) -> None:
        if (
            telemetry.device_type
            != self.device_type
        ):
            return

        if hasattr(
            self,
            "xy_widget",
        ):
            self.xy_widget.set_axes(
                telemetry.axes.get(
                    "X",
                    0,
                ),
                telemetry.axes.get(
                    "Y",
                    0,
                ),
            )

        for axis, bar in (
            self.axis_bars.items()
        ):
            bar.set_value(
                telemetry.axes.get(
                    axis,
                    0,
                )
            )

        if self.button_grid:
            self.button_grid.set_mask(
                telemetry.buttons
            )

    def apply_settings(
        self,
        settings: DeviceSettings,
    ) -> None:
        if (
            settings.device_type
            != self.device_type
        ):
            return

        self._updating_settings = True

        try:
            for (
                axis,
                value,
            ) in settings.inversions.items():
                box = self.inversion_boxes.get(
                    axis
                )

                if box:
                    box.setChecked(value)

            for (
                axis,
                value,
            ) in settings.deadzones.items():
                box = self.deadzone_boxes.get(
                    axis
                )

                if box:
                    box.setValue(value)

            if len(settings.filters) >= 1:
                self.filter_1.setValue(
                    settings.filters[0]
                )

            if len(settings.filters) >= 2:
                self.filter_2.setValue(
                    settings.filters[1]
                )

            self.jitter.setValue(
                settings.jitter
            )

            for (
                index,
                enabled,
            ) in enumerate(settings.atb):
                if index < len(
                    self.atb_boxes
                ):
                    self.atb_boxes[
                        index
                    ].setChecked(enabled)

        finally:
            self._updating_settings = False

    def reset_telemetry(self) -> None:
        if hasattr(
            self,
            "xy_widget",
        ):
            self.xy_widget.reset()

        for bar in self.axis_bars.values():
            bar.reset()

        if self.button_grid:
            self.button_grid.reset()
