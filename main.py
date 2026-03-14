import sys
from PySide6.QtWidgets import QApplication
from ui import WebScraperApp, STYLESHEET


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    window = WebScraperApp()
    window.show()
    sys.exit(app.exec())
