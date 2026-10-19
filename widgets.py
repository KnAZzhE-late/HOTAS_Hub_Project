from __future__ import annotations

from PySide6.QtCore import (
    QPointF,
    QRectF,
    QSize,
    Qt,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


AXIS_MIN = -16384
AXIS_MAX = 16384


class XYAxisWidget(QWidget):
    def __init__(
        self,
        title: str,
        caption: str = "Ось X / Ось Y",
        parent=None,
    ) -> None:
        super().__init__(parent)

        self._title = title
        self._caption = caption

        self._x = 0
        self._y = 0

        self.setMinimumSize(280, 320)

        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )

    def set_axes(
        self,
        x: int,
        y: int,
    ) -> None:
        self._x = max(
            AXIS_MIN,
            min(AXIS_MAX, int(x)),
        )

        self._y = max(
            AXIS_MIN,
            min(AXIS_MAX, int(y)),
        )

        self.update()

    def reset(self) -> None:
        self.set_axes(0, 0)

    def paintEvent(self, event) -> None:
        del event

        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
        )

        painter.fillRect(
            self.rect(),
            QColor("#151b24"),
        )

        title_font = QFont("Segoe UI", 11)
        title_font.setWeight(
            QFont.Weight.DemiBold,
        )

        painter.setFont(title_font)
        painter.setPen(QColor("#f1f5f9"))

        painter.drawText(
            QRectF(
                18,
                14,
                self.width() - 36,
                28,
            ),
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter,
            self._title,
        )

        margin = 28.0
        top = 56.0

        size = min(
            self.width() - margin * 2,
            210.0,
        )

        field = QRectF(
            (self.width() - size) / 2,
            top,
            size,
            size,
        )

        painter.fillRect(
            field,
            QColor("#0b1017"),
        )

        grid_pen = QPen(
            QColor("#26303d"),
            1,
        )
        grid_pen.setStyle(
            Qt.PenStyle.DashLine,
        )

        painter.setPen(grid_pen)

        painter.drawLine(
            QPointF(
                field.center().x(),
                field.top(),
            ),
            QPointF(
                field.center().x(),
                field.bottom(),
            ),
        )

        painter.drawLine(
            QPointF(
                field.left(),
                field.center().y(),
            ),
            QPointF(
                field.right(),
                field.center().y(),
            ),
        )

        painter.setPen(
            QPen(
                QColor("#5e6b7a"),
                1.3,
            )
        )

        painter.drawRect(field)

        normalized_x = (
            self._x - AXIS_MIN
        ) / (AXIS_MAX - AXIS_MIN)

        normalized_y = (
            self._y - AXIS_MIN
        ) / (AXIS_MAX - AXIS_MIN)

        point = QPointF(
            field.left()
            + normalized_x * field.width(),
            field.bottom()
            - normalized_y * field.height(),
        )

        # Свечение вокруг маркера.
        painter.setPen(
            QPen(
                QColor(0, 214, 255, 70),
                8,
            )
        )
        painter.drawEllipse(point, 5, 5)

        # Основной крест.
        painter.setPen(
            QPen(
                QColor("#00d6ff"),
                2,
            )
        )

        cross_size = 9

        painter.drawLine(
            QPointF(
                point.x() - cross_size,
                point.y(),
            ),
            QPointF(
                point.x() + cross_size,
                point.y(),
            ),
        )

        painter.drawLine(
            QPointF(
                point.x(),
                point.y() - cross_size,
            ),
            QPointF(
                point.x(),
                point.y() + cross_size,
            ),
        )

        painter.setBrush(
            QColor("#00d6ff")
        )
        painter.setPen(
            Qt.PenStyle.NoPen,
        )
        painter.drawEllipse(
            point,
            2.5,
            2.5,
        )

        painter.setPen(
            QColor("#dce6ef")
        )
        painter.setFont(
            QFont("Segoe UI", 9)
        )

        painter.drawText(
            QRectF(
                10,
                field.bottom() + 12,
                self.width() - 20,
                22,
            ),
            Qt.AlignmentFlag.AlignCenter,
            self._caption,
        )

        painter.setPen(
            QColor("#8b99aa")
        )

        painter.drawText(
            QRectF(
                10,
                field.bottom() + 35,
                self.width() - 20,
                22,
            ),
            Qt.AlignmentFlag.AlignCenter,
            (
                f"X: {self._x:+6d}    "
                f"Y: {self._y:+6d}"
            ),
        )


class AxisBar(QFrame):
    """
    Толстый линейный индикатор одной оси.
    """

    def __init__(
        self,
        name: str,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self._name = name
        self._value = 0

        self.setObjectName("axisBarFrame")
        self.setMinimumHeight(42)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            10,
            6,
            10,
            6,
        )
        layout.setSpacing(12)

        name_label = QLabel(name)
        name_label.setFixedWidth(62)
        name_label.setObjectName("axisName")

        self.bar = QProgressBar()
        self.bar.setObjectName("axisProgressBar")

        self.bar.setRange(
            0,
            AXIS_MAX - AXIS_MIN,
        )
        self.bar.setValue(-AXIS_MIN)
        self.bar.setTextVisible(False)

        # Толщина задаётся также здесь, чтобы она
        # сохранялась независимо от QSS.
        self.bar.setFixedHeight(18)

        self.value_label = QLabel("0")
        self.value_label.setFixedWidth(78)

        self.value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter
        )

        self.value_label.setObjectName(
            "axisValue"
        )

        layout.addWidget(name_label)
        layout.addWidget(self.bar, 1)
        layout.addWidget(self.value_label)

    def set_value(self, value: int) -> None:
        self._value = max(
            AXIS_MIN,
            min(AXIS_MAX, int(value)),
        )

        self.bar.setValue(
            self._value - AXIS_MIN
        )

        self.value_label.setText(
            f"{self._value:+d}"
        )

    def reset(self) -> None:
        self.set_value(0)


class ButtonIndicator(QWidget):
    """
    Индикатор состояния одной физической кнопки.

    Окантовка рисуется постоянно.
    При нажатии изменяется цвет фона, рамки и текста.
    """

    def __init__(
        self,
        number: int,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self._number = number
        self._pressed = False

        self.setFixedSize(42, 34)

        self.setAttribute(
            Qt.WidgetAttribute.WA_OpaquePaintEvent,
            False,
        )

    def sizeHint(self) -> QSize:
        return QSize(42, 34)

    def is_pressed(self) -> bool:
        return self._pressed

    def set_pressed(
        self,
        pressed: bool,
    ) -> None:
        pressed = bool(pressed)

        if self._pressed == pressed:
            return

        self._pressed = pressed
        self.update()

    def reset(self) -> None:
        self.set_pressed(False)

    def paintEvent(self, event) -> None:
        del event

        painter = QPainter(self)

        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
        )

        outer_rect = QRectF(
            1.5,
            1.5,
            self.width() - 3.0,
            self.height() - 3.0,
        )

        if self._pressed:
            # Внешнее свечение активной кнопки.
            glow_rect = QRectF(
                0.5,
                0.5,
                self.width() - 1.0,
                self.height() - 1.0,
            )

            painter.setBrush(
                QColor(0, 214, 255, 38)
            )
            painter.setPen(
                Qt.PenStyle.NoPen
            )
            painter.drawRoundedRect(
                glow_rect,
                6,
                6,
            )

            painter.setBrush(
                QColor("#00a8cc")
            )
            painter.setPen(
                QPen(
                    QColor("#36e5ff"),
                    1.8,
                )
            )

            text_color = QColor("#ffffff")

        else:
            painter.setBrush(
                QColor("#151d27")
            )
            painter.setPen(
                QPen(
                    QColor("#566577"),
                    1.3,
                )
            )

            text_color = QColor("#a5b3c2")

        painter.drawRoundedRect(
            outer_rect,
            5,
            5,
        )

        font = QFont("Segoe UI", 9)
        font.setWeight(
            QFont.Weight.DemiBold
            if self._pressed
            else QFont.Weight.Normal
        )

        painter.setFont(font)
        painter.setPen(text_color)

        painter.drawText(
            outer_rect,
            Qt.AlignmentFlag.AlignCenter,
            str(self._number),
        )


class ButtonGrid(QFrame):
    """
    Сетка индикаторов кнопок устройства.
    """

    def __init__(
        self,
        count: int,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self.count = count

        self._indicators: list[
            ButtonIndicator
        ] = []

        self.setObjectName("card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            14,
            14,
            14,
            14,
        )
        layout.setSpacing(12)

        title = QLabel("Кнопки")
        title.setObjectName("sectionTitle")

        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(8)

        # Максимум 10 кнопок в одной строке.
        columns = 10

        for index in range(count):
            indicator = ButtonIndicator(
                number=index + 1,
            )

            row = index // columns
            column = index % columns

            grid.addWidget(
                indicator,
                row,
                column,
                Qt.AlignmentFlag.AlignLeft,
            )

            self._indicators.append(
                indicator
            )

        # Не позволяет кнопкам растягиваться
        # на всю ширину карточки.
        grid.setColumnStretch(columns, 1)

        layout.addLayout(grid)

    def set_mask(self, mask: int) -> None:
        """
        Устанавливает состояние кнопок из битовой маски.

        Бит 0 соответствует кнопке 1,
        бит 1 соответствует кнопке 2 и так далее.
        """
        mask = int(mask)

        for index, indicator in enumerate(
            self._indicators
        ):
            pressed = bool(
                mask & (1 << index)
            )

            indicator.set_pressed(pressed)

    def reset(self) -> None:
        for indicator in self._indicators:
            indicator.reset()
