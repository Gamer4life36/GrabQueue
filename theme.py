"""Dark theme for GrabQueue (same palette family as Image Downloader)."""

BG = "#0f1115"
PANEL = "#1a1d24"
PANEL_HI = "#22262f"
BORDER = "#2b3140"
TEXT = "#e6e9ef"
MUTED = "#8b93a3"
ACCENT = "#5b8cff"
ACCENT_HI = "#7aa2ff"
OK = "#46d18b"
ERR = "#ff6b6b"
WARN = "#f0b357"

QSS = f"""
* {{ font-family: 'Segoe UI'; font-size: 10pt; }}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget {{ color: {TEXT}; }}

QLineEdit, QPlainTextEdit, QSpinBox, QComboBox {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 6px 10px; selection-background-color: {ACCENT};
}}
QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {ACCENT}; }}

QPushButton {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 7px 16px;
}}
QPushButton:hover {{ background: {PANEL_HI}; }}
QPushButton:disabled {{ color: {MUTED}; }}
QPushButton#accent {{
    background: {ACCENT}; color: white; font-weight: 600; border: none;
}}
QPushButton#accent:hover {{ background: {ACCENT_HI}; }}
QPushButton#accent:disabled {{ background: #39414f; color: #9aa3b2; }}

QTableWidget {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px;
    gridline-color: {BORDER}; alternate-background-color: #171a21;
}}
QTableWidget::item {{ padding: 4px 8px; }}
QTableWidget::item:selected {{ background: #2a3550; color: {TEXT}; }}
QHeaderView::section {{
    background: {PANEL_HI}; color: {MUTED}; border: none;
    border-bottom: 1px solid {BORDER}; padding: 8px; font-weight: 600;
}}

QProgressBar {{
    background: {PANEL_HI}; border: none; border-radius: 4px;
    height: 10px; text-align: center; color: {TEXT}; font-size: 8pt;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}

QStatusBar {{ background: {PANEL}; color: {MUTED}; }}
QToolBar {{ background: {BG}; border: none; spacing: 6px; padding: 6px; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#title {{ font-size: 16pt; font-weight: 600; }}

QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {PANEL}; border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
}}
QScrollBar:vertical {{
    background: {PANEL}; width: 10px; border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 5px; min-height: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QMenu {{ background: {PANEL}; border: 1px solid {BORDER}; }}
QMenu::item:selected {{ background: {ACCENT}; }}
"""
