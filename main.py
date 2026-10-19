import sys

from PySide6.QtWidgets import QApplication

from hotas_hub.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("HOTAS Hub")
    app.setOrganizationName("HFB")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
