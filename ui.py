import os
import threading

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QSlider,
    QProgressBar, QFrame, QFileDialog, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor

from engine import CrawlerEngine, CrawlerSignals


# ── Theme ──

STYLESHEET = """
QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #0f1120, stop:0.5 #131627, stop:1 #0d0f1a);
}
QWidget#centralWidget { background: transparent; }

QFrame#card {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(25, 28, 50, 230), stop:1 rgba(20, 23, 42, 240));
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 14px;
}

QLabel#title {
    color: #e8eaf6;
    font-size: 22px;
    font-weight: 700;
    font-family: 'Segoe UI', sans-serif;
    letter-spacing: 1px;
}
QLabel#sectionLabel {
    color: rgba(200, 210, 255, 0.85);
    font-size: 13px;
    font-weight: 600;
    font-family: 'Segoe UI', sans-serif;
}
QLabel#accentLabel {
    color: #6c8cff;
    font-size: 13px;
    font-weight: 700;
    font-family: 'Consolas', monospace;
}

QSlider::groove:horizontal {
    background: rgba(40, 45, 75, 0.5);
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #6c8cff, stop:1 #5a7aff);
    width: 18px; height: 18px;
    margin: -6px 0;
    border-radius: 9px;
    border: 2px solid rgba(108, 140, 255, 0.3);
}
QSlider::handle:horizontal:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #7d9cff, stop:1 #6b8aff);
    border: 2px solid rgba(108, 140, 255, 0.5);
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #4c6cf5, stop:1 #6c8cff);
    border-radius: 3px;
}

QTextEdit#logBox {
    background: rgba(8, 10, 22, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.04);
    border-radius: 10px;
    padding: 12px;
    color: rgba(170, 180, 210, 0.85);
    font-size: 12px;
    font-family: 'Consolas', 'Fira Code', monospace;
    selection-background-color: rgba(108, 140, 255, 0.25);
}
QTextEdit#logBox:focus {
    border: 1px solid rgba(108, 140, 255, 0.2);
}

QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 4px 2px;
}
QScrollBar::handle:vertical {
    background: rgba(108, 140, 255, 0.2);
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(108, 140, 255, 0.35);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


# ── Helpers ──

def make_card():
    frame = QFrame()
    frame.setObjectName("card")
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(30)
    shadow.setOffset(0, 4)
    shadow.setColor(QColor(0, 0, 0, 80))
    frame.setGraphicsEffect(shadow)
    return frame


# ── Main window ──

class WebScraperApp(QMainWindow):

    CHIP_ON = """
        QPushButton {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #5a7aff, stop:1 #4c6cf5);
            color: white; border: none; border-radius: 16px;
            padding: 6px 18px; font-size: 12px; font-weight: 600; font-family: 'Segoe UI';
        }
        QPushButton:hover {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #6b8aff, stop:1 #5d7dff);
        }
    """
    CHIP_OFF = """
        QPushButton {
            background: rgba(30, 34, 55, 0.6);
            color: rgba(160, 170, 200, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 16px;
            padding: 6px 18px; font-size: 12px; font-weight: 500; font-family: 'Segoe UI';
        }
        QPushButton:hover {
            background: rgba(45, 50, 80, 0.7);
            color: rgba(190, 200, 230, 0.8);
            border: 1px solid rgba(108, 140, 255, 0.2);
        }
    """
    CTRL_BTN = """
        QPushButton {{
            background: {bg}; color: {fg}; border: none; border-radius: 20px;
            padding: 10px 28px; font-size: 13px; font-weight: 600;
            font-family: 'Segoe UI', sans-serif;
        }}
        QPushButton:hover {{ background: {hover}; }}
        QPushButton:disabled {{
            background: rgba(40, 44, 70, 0.3); color: rgba(150, 160, 190, 0.25);
        }}
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Website Scrapper")
        self.setMinimumSize(860, 580)
        self.resize(900, 620)

        self.crawler = None
        self._options_open = False

        self.signals = CrawlerSignals()
        self.signals.log_signal.connect(self._append_log)
        self.signals.progress_signal.connect(self._update_progress)
        self.signals.complete_signal.connect(self._on_complete)

        self._build_ui()

    # ── UI construction ──

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(24, 14, 24, 14)
        root.setSpacing(8)

        # Title
        title = QLabel("Website Scrapper")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        # URL input
        url_label = QLabel("Target URL")
        url_label.setObjectName("sectionLabel")
        url_label.setAlignment(Qt.AlignCenter)
        url_label.setStyleSheet("font-weight: 800; font-size: 17px;")
        root.addWidget(url_label)

        url_row = QHBoxLayout()
        url_row.addStretch()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com")
        self.url_input.setFixedHeight(46)
        self.url_input.setFixedWidth(560)
        self.url_input.setStyleSheet("""
            QLineEdit {
                background: rgba(12, 14, 28, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 23px; padding: 10px 22px;
                color: #d0d5f0; font-size: 14px; font-family: 'Consolas', monospace;
            }
            QLineEdit:focus {
                border: 1px solid rgba(108, 140, 255, 0.5);
                background: rgba(15, 17, 32, 0.9);
            }
            QLineEdit:disabled {
                background: rgba(12, 14, 28, 0.4);
                color: rgba(160, 170, 200, 0.4);
            }
        """)
        self.url_input.returnPressed.connect(self._start_crawl)
        url_row.addWidget(self.url_input)
        url_row.addStretch()
        root.addLayout(url_row)
        root.addSpacing(10)

        # Options toggle
        opt_btn_row = QHBoxLayout()
        opt_btn_row.addStretch()
        self.options_toggle_btn = QPushButton("Options")
        self.options_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.options_toggle_btn.setFixedSize(140, 38)
        self.options_toggle_btn.setStyleSheet("""
            QPushButton {
                background: rgba(40, 45, 75, 0.6);
                color: rgba(190, 200, 230, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 19px;
                font-size: 13px; font-weight: 600; font-family: 'Segoe UI', sans-serif;
            }
            QPushButton:hover {
                background: rgba(55, 62, 100, 0.7);
                border: 1px solid rgba(108, 140, 255, 0.3);
            }
        """)
        self.options_toggle_btn.clicked.connect(self._toggle_options)
        opt_btn_row.addWidget(self.options_toggle_btn)
        opt_btn_row.addStretch()
        root.addLayout(opt_btn_row)

        self._build_options_panel(root)
        root.addSpacing(10)
        self._build_controls(root)
        self._build_status_bar(root)

        # Activity log
        log_header = QLabel("Activity Log")
        log_header.setObjectName("sectionLabel")
        root.addWidget(log_header)

        self.log_box = QTextEdit()
        self.log_box.setObjectName("logBox")
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(110)
        root.addWidget(self.log_box)

    def _build_options_panel(self, root):
        self.options_panel = make_card()
        self.options_panel.setVisible(False)
        self.options_panel.setMaximumHeight(0)

        layout = QVBoxLayout(self.options_panel)
        layout.setContentsMargins(26, 18, 26, 18)
        layout.setSpacing(16)

        # Depth slider
        depth_row = QHBoxLayout()
        depth_row.setSpacing(14)
        dlbl = QLabel("Crawl Depth")
        dlbl.setStyleSheet(
            "color: rgba(200,210,255,0.85); font-size: 13px;"
            "font-weight: 600; font-family: 'Segoe UI';"
        )
        depth_row.addWidget(dlbl)

        self.depth_slider = QSlider(Qt.Horizontal)
        self.depth_slider.setRange(1, 10)
        self.depth_slider.setValue(2)
        self.depth_slider.setFixedWidth(180)
        self.depth_slider.valueChanged.connect(self._update_depth)
        depth_row.addWidget(self.depth_slider)

        self.depth_label = QLabel("2")
        self.depth_label.setObjectName("accentLabel")
        self.depth_label.setFixedWidth(24)
        depth_row.addWidget(self.depth_label)
        depth_row.addStretch()
        layout.addLayout(depth_row)

        # Asset chips
        assets_label = QLabel("Assets")
        assets_label.setStyleSheet(
            "color: rgba(200,210,255,0.85); font-size: 13px;"
            "font-weight: 600; font-family: 'Segoe UI';"
        )
        layout.addWidget(assets_label)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(10)
        self._asset_chips = {}
        for label, default_on in [
            ("Images", True), ("CSS", True), ("JavaScript", True),
            ("Fonts", True), ("Media", False), ("Documents", False),
            ("Same domain", True),
        ]:
            chip = QPushButton(label)
            chip.setCursor(Qt.PointingHandCursor)
            chip.setFixedHeight(32)
            chip.setCheckable(True)
            chip.setChecked(default_on)
            chip.setStyleSheet(self.CHIP_ON if default_on else self.CHIP_OFF)
            chip.toggled.connect(
                lambda checked, c=chip: c.setStyleSheet(self.CHIP_ON if checked else self.CHIP_OFF)
            )
            chips_row.addWidget(chip)
            self._asset_chips[label] = chip
        chips_row.addStretch()
        layout.addLayout(chips_row)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.05);")
        layout.addWidget(sep)

        # Output directory
        dir_row = QHBoxLayout()
        dir_row.setSpacing(10)
        default_out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

        dir_label = QLabel("Active Directory :")
        dir_label.setStyleSheet(
            "color: rgba(180,190,220,0.7); font-size: 12px; font-family: 'Segoe UI';"
        )
        dir_row.addWidget(dir_label)

        self.dir_path_label = QLabel(default_out)
        self.dir_path_label.setStyleSheet(
            "color: rgba(130,145,195,0.55); font-size: 12px; font-family: 'Consolas';"
        )
        dir_row.addWidget(self.dir_path_label)
        dir_row.addStretch()

        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setCursor(Qt.PointingHandCursor)
        self.browse_btn.setFixedSize(80, 30)
        self.browse_btn.setStyleSheet("""
            QPushButton {
                background: rgba(40, 45, 75, 0.5);
                color: rgba(190, 200, 230, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 15px;
                font-size: 12px; font-family: 'Segoe UI';
            }
            QPushButton:hover {
                background: rgba(55, 62, 100, 0.6);
                border: 1px solid rgba(108, 140, 255, 0.3);
            }
        """)
        self.browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(self.browse_btn)
        layout.addLayout(dir_row)

        root.addWidget(self.options_panel)

    def _build_controls(self, root):
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addStretch()

        self.start_btn = self._make_ctrl_btn("Start", 130,
            bg="qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #5a7aff, stop:1 #4c6cf5)",
            fg="white",
            hover="qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #6b8aff, stop:1 #5d7dff)")
        self.start_btn.clicked.connect(self._start_crawl)
        row.addWidget(self.start_btn)

        self.pause_btn = self._make_ctrl_btn("Pause", 110,
            bg="qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #e0a040, stop:1 #d09030)",
            fg="#1a1b26",
            hover="qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #e8b050, stop:1 #d8a040)")
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._pause_crawl)
        row.addWidget(self.pause_btn)

        self.stop_btn = self._make_ctrl_btn("Stop", 110,
            bg="qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #ff5570, stop:1 #e84460)",
            fg="white",
            hover="qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #ff6580, stop:1 #f05470)")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_crawl)
        row.addWidget(self.stop_btn)

        self.open_btn = self._make_ctrl_btn("Open Output", 130,
            bg="rgba(40, 45, 75, 0.6)",
            fg="rgba(190, 200, 230, 0.85)",
            hover="rgba(55, 62, 100, 0.7)")
        self.open_btn.clicked.connect(self._open_output)
        row.addWidget(self.open_btn)

        row.addStretch()
        root.addLayout(row)

    def _make_ctrl_btn(self, text, width, bg, fg, hover):
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(width, 40)
        btn.setStyleSheet(self.CTRL_BTN.format(bg=bg, fg=fg, hover=hover))
        return btn

    def _build_status_bar(self, root):
        row = QHBoxLayout()
        row.setContentsMargins(8, 0, 8, 0)

        self.status_dot = QLabel()
        self.status_dot.setFixedSize(8, 8)
        self.status_dot.setStyleSheet("background: rgba(100,120,180,0.4); border-radius: 4px;")
        row.addWidget(self.status_dot)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(
            "color: rgba(140,150,180,0.6); font-size: 11px; font-family: 'Consolas';"
        )
        row.addWidget(self.status_label)
        row.addStretch()

        self.stats_label = QLabel("0 files  \u00b7  0 B")
        self.stats_label.setStyleSheet(
            "color: rgba(140,150,180,0.5); font-size: 11px; font-family: 'Consolas';"
        )
        row.addWidget(self.stats_label)
        root.addLayout(row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: rgba(25, 28, 48, 0.4); border: none; border-radius: 2px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #4c6cf5, stop:0.5 #6c8cff, stop:1 #8cacff);
                border-radius: 2px;
            }
        """)
        root.addWidget(self.progress_bar)

    # ── Slots ──

    def _toggle_options(self):
        if self._options_open:
            self._anim = QPropertyAnimation(self.options_panel, b"maximumHeight")
            self._anim.setDuration(250)
            self._anim.setStartValue(self.options_panel.sizeHint().height())
            self._anim.setEndValue(0)
            self._anim.setEasingCurve(QEasingCurve.OutCubic)
            self._anim.finished.connect(lambda: self.options_panel.setVisible(False))
            self._anim.start()
            self._options_open = False
        else:
            self.options_panel.setVisible(True)
            target_h = self.options_panel.sizeHint().height()
            self._anim = QPropertyAnimation(self.options_panel, b"maximumHeight")
            self._anim.setDuration(250)
            self._anim.setStartValue(0)
            self._anim.setEndValue(target_h)
            self._anim.setEasingCurve(QEasingCurve.OutCubic)
            self._anim.finished.connect(lambda: self.options_panel.setMaximumHeight(16777215))
            self._anim.start()
            self._options_open = True

    def _update_depth(self, val):
        self.depth_label.setText(str(val))

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if path:
            self.dir_path_label.setText(path)

    def _append_log(self, msg):
        colors = {
            "[ERROR]": "#ff6b81",
            "[WARN]":  "#e0a845",
            "Saved:":  "#5fdd97",
            "Base64":  "#a78bfa",
        }
        color = "#8890b0"
        for key, c in colors.items():
            if key in msg:
                color = c
                break
        if "complete" in msg.lower():
            color = "#5fdd97"
        self.log_box.append(f'<span style="color:{color}">{msg}</span>')

    def _set_status(self, text, color):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            f"color: {color}; font-size: 11px; font-family: 'Consolas'; border: none;"
        )
        self.status_dot.setStyleSheet(
            f"background: {color}; border-radius: 4px; border: none;"
        )

    def _update_progress(self, files, size):
        self.stats_label.setText(f"{files} files  \u00b7  {CrawlerEngine.format_size(size)}")
        self.stats_label.setStyleSheet(
            "color: rgba(180,190,220,0.7); font-size: 11px; font-family: 'Consolas'; border: none;"
        )
        if self.crawler:
            pending = len(self.crawler.queue)
            pct = int(min(files / max(files + pending, 1), 1.0) * 100)
            self.progress_bar.setValue(pct)

    def _on_complete(self, files, size):
        self.stats_label.setText(f"{files} files  \u00b7  {CrawlerEngine.format_size(size)}")
        self._set_status("Complete", "#5fdd97")
        self.progress_bar.setValue(100)
        self._set_idle()

    def _set_running(self):
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.url_input.setEnabled(False)
        self.depth_slider.setEnabled(False)
        self._set_status("Mirroring...", "#6c8cff")

    def _set_idle(self):
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("Pause")
        self.stop_btn.setEnabled(False)
        self.url_input.setEnabled(True)
        self.depth_slider.setEnabled(True)

    def _start_crawl(self):
        url = self.url_input.text().strip()
        if not url:
            self.signals.log_signal.emit("[ERROR] Please enter a URL.")
            return

        self.log_box.clear()
        self.progress_bar.setValue(0)

        self.crawler = CrawlerEngine(
            url=url,
            output_dir=self.dir_path_label.text().strip(),
            depth=self.depth_slider.value(),
            same_domain=self._asset_chips["Same domain"].isChecked(),
            download_images=self._asset_chips["Images"].isChecked(),
            download_css=self._asset_chips["CSS"].isChecked(),
            download_js=self._asset_chips["JavaScript"].isChecked(),
            download_fonts=self._asset_chips["Fonts"].isChecked(),
            download_media=self._asset_chips["Media"].isChecked(),
            download_docs=self._asset_chips["Documents"].isChecked(),
            on_progress=lambda f, s: self.signals.progress_signal.emit(f, s),
            on_log=lambda m: self.signals.log_signal.emit(m),
            on_complete=lambda f, s: self.signals.complete_signal.emit(f, s),
        )
        self._set_running()
        threading.Thread(target=self.crawler.start, daemon=True).start()

    def _pause_crawl(self):
        if not self.crawler:
            return
        if self.crawler.paused:
            self.crawler.resume()
            self.pause_btn.setText("Pause")
            self._set_status("Mirroring...", "#6c8cff")
        else:
            self.crawler.pause()
            self.pause_btn.setText("Resume")
            self._set_status("Paused", "#e0a845")

    def _stop_crawl(self):
        if self.crawler:
            self.crawler.stop()
            self._set_status("Stopped", "#ff6b81")
            self._set_idle()

    def _open_output(self):
        path = self.dir_path_label.text().strip()
        if os.path.isdir(path):
            os.startfile(path)
        else:
            self.signals.log_signal.emit("[WARN] Output folder does not exist yet.")
