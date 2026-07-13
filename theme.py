"""Themes, color palettes, and the global application stylesheet."""
from PyQt6.QtGui import QColor

THEMES = {
    "Dark Black": {
        "window": (26, 27, 38), "window_text": (192, 202, 245),
        "base": (36, 40, 59), "alt_base": (26, 27, 38),
        "text": (192, 202, 245), "button": (36, 40, 59),
        "button_text": (192, 202, 245), "bright": (247, 118, 142),
        "highlight": (122, 162, 247), "highlight_text": (26, 27, 38),
    },
    "AMOLED": {
        "window": (0, 0, 0), "window_text": (222, 222, 222),
        "base": (10, 10, 10), "alt_base": (0, 0, 0),
        "text": (222, 222, 222), "button": (16, 16, 16),
        "button_text": (222, 222, 222), "bright": (255, 122, 122),
        "highlight": (80, 140, 255), "highlight_text": (0, 0, 0),
    },
    "Blue": {
        "window": (17, 24, 39), "window_text": (187, 210, 245),
        "base": (24, 34, 56), "alt_base": (17, 24, 39),
        "text": (187, 210, 245), "button": (24, 34, 56),
        "button_text": (187, 210, 245), "bright": (96, 165, 250),
        "highlight": (59, 130, 246), "highlight_text": (255, 255, 255),
    },
    "Purple": {
        "window": (30, 20, 44), "window_text": (220, 200, 245),
        "base": (42, 28, 62), "alt_base": (30, 20, 44),
        "text": (220, 200, 245), "button": (42, 28, 62),
        "button_text": (220, 200, 245), "bright": (192, 132, 252),
        "highlight": (147, 51, 234), "highlight_text": (255, 255, 255),
    },
    "Sepia": {
        "window": (62, 49, 37), "window_text": (230, 213, 189),
        "base": (75, 60, 45), "alt_base": (62, 49, 37),
        "text": (230, 213, 189), "button": (75, 60, 45),
        "button_text": (230, 213, 189), "bright": (217, 119, 6),
        "highlight": (180, 120, 60), "highlight_text": (255, 255, 255),
    },
}

def apply_theme(app, theme_name):
    t = THEMES.get(theme_name, THEMES["Dark Black"])
    palette = app.palette()
    palette.setColor(palette.ColorRole.Window, QColor(*t["window"]))
    palette.setColor(palette.ColorRole.WindowText, QColor(*t["window_text"]))
    palette.setColor(palette.ColorRole.Base, QColor(*t["base"]))
    palette.setColor(palette.ColorRole.AlternateBase, QColor(*t["alt_base"]))
    palette.setColor(palette.ColorRole.ToolTipBase, QColor(*t["window_text"]))
    palette.setColor(palette.ColorRole.ToolTipText, QColor(*t["window_text"]))
    palette.setColor(palette.ColorRole.Text, QColor(*t["text"]))
    palette.setColor(palette.ColorRole.Button, QColor(*t["button"]))
    palette.setColor(palette.ColorRole.ButtonText, QColor(*t["button_text"]))
    palette.setColor(palette.ColorRole.BrightText, QColor(*t["bright"]))
    palette.setColor(palette.ColorRole.Highlight, QColor(*t["highlight"]))
    palette.setColor(palette.ColorRole.HighlightedText, QColor(*t["highlight_text"]))
    app.setPalette(palette)

    # Global stylesheet: flat, minimal, consistent spacing
    win = "rgb(%d,%d,%d)" % t["window"]
    base = "rgb(%d,%d,%d)" % t["base"]
    btn = "rgb(%d,%d,%d)" % t["button"]
    txt = "rgb(%d,%d,%d)" % t["text"]
    hl = "rgb(%d,%d,%d)" % t["highlight"]
    border = "rgba(%d,%d,%d,60)" % t["text"]
    app.setStyleSheet(f"""
        QToolBar {{
            background: {win};
            border: none;
            border-bottom: 1px solid {border};
            padding: 4px 6px;
            spacing: 4px;
        }}
        QToolBar QToolButton, QToolBar QPushButton {{
            background: transparent;
            color: {txt};
            border: none;
            border-radius: 6px;
            padding: 5px 10px;
        }}
        QToolBar QToolButton:hover, QToolBar QPushButton:hover {{
            background: {base};
        }}
        QToolBar QToolButton:checked {{
            background: {hl};
            color: {win};
        }}
        QToolBar::separator {{
            background: {border};
            width: 1px;
            margin: 6px 6px;
        }}
        QLineEdit {{
            background: {base};
            color: {txt};
            border: 1px solid {border};
            border-radius: 6px;
            padding: 4px 8px;
            selection-background-color: {hl};
        }}
        QComboBox {{
            background: {base};
            color: {txt};
            border: 1px solid {border};
            border-radius: 6px;
            padding: 4px 8px;
        }}
        QComboBox::drop-down {{ border: none; width: 18px; }}
        QTreeWidget {{
            background: {base};
            color: {txt};
            border: none;
            border-radius: 6px;
            padding: 4px;
        }}
        QTreeWidget::item {{ padding: 3px 2px; border-radius: 4px; }}
        QTreeWidget::item:selected {{ background: {hl}; color: {win}; }}
        QTabWidget::pane {{ border: none; background: {win}; }}
        QTabBar::tab {{
            background: transparent;
            color: {txt};
            padding: 7px 16px;
            border: none;
            border-bottom: 2px solid transparent;
        }}
        QTabBar::tab:selected {{
            color: {hl};
            border-bottom: 2px solid {hl};
        }}
        QStatusBar {{
            background: {win};
            color: {txt};
            border-top: 1px solid {border};
        }}
        QMenu {{
            background: {base};
            color: {txt};
            border: 1px solid {border};
            border-radius: 6px;
            padding: 4px;
        }}
        QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
        QMenu::item:selected {{ background: {hl}; color: {win}; }}
        QScrollArea {{ border: none; }}
        QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {border}; border-radius: 5px; min-height: 30px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
        QScrollBar::handle:horizontal {{ background: {border}; border-radius: 5px; min-width: 30px; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    """)


# ── Highlight Colors ─────────────────────────────────────────────────────────
HIGHLIGHT_COLORS = {
    "Yellow": (1.0, 0.92, 0.23),
    "Green":  (0.40, 0.85, 0.42),
    "Pink":   (0.96, 0.45, 0.71),
    "Blue":   (0.38, 0.65, 0.98),
    "Orange": (1.0, 0.62, 0.26),
}

def hl_qcolor(name, alpha=100):
    r, g, b = HIGHLIGHT_COLORS.get(name, HIGHLIGHT_COLORS["Yellow"])
    return QColor(int(r*255), int(g*255), int(b*255), alpha)

# ── Pen (ink) Colors ─────────────────────────────────────────────────────────
PEN_COLORS = {
    "Red":   (0.90, 0.13, 0.13),
    "Black": (0.05, 0.05, 0.05),
    "Blue":  (0.15, 0.39, 0.92),
    "Green": (0.13, 0.63, 0.30),
    "White": (0.98, 0.98, 0.98),
}

def pen_qcolor(name, alpha=255):
    r, g, b = PEN_COLORS.get(name, PEN_COLORS["Red"])
    return QColor(int(r*255), int(g*255), int(b*255), alpha)


