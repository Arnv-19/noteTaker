"""Themes, color palettes, and the global application stylesheet."""
from PyQt6.QtGui import QColor

THEMES = {
    "AMOLED": {
        "window": (0, 0, 0), "window_text": (222, 222, 222),
        "base": (10, 10, 10), "alt_base": (0, 0, 0),
        "text": (222, 222, 222), "button": (16, 16, 16),
        "button_text": (222, 222, 222), "bright": (255, 122, 122),
        "highlight": (80, 140, 255), "highlight_text": (0, 0, 0),
    },
    "Storm Harbour": {
        "window": (2, 12, 26), "window_text": (192, 210, 225),
        "base": (22, 22, 22), "alt_base": (11, 11, 11),
        "text": (192, 210, 225), "button": (22, 22, 22),
        "button_text": (192, 210, 225), "bright": (127, 9, 9),
        "highlight": (13, 107, 61), "highlight_text": (240, 240, 240),
    },
    "Amethyst": {
        "window": (15, 10, 26), "window_text": (210, 200, 230),
        "base": (26, 18, 48), "alt_base": (15, 10, 26),
        "text": (210, 200, 230), "button": (26, 18, 48),
        "button_text": (210, 200, 230), "bright": (232, 160, 140),
        "highlight": (139, 92, 246), "highlight_text": (240, 235, 250),
    },
    "Sepia": {
        "window": (62, 49, 37), "window_text": (230, 213, 189),
        "base": (75, 60, 45), "alt_base": (62, 49, 37),
        "text": (230, 213, 189), "button": (75, 60, 45),
        "button_text": (230, 213, 189), "bright": (217, 119, 6),
        "highlight": (180, 120, 60), "highlight_text": (255, 255, 255),
    },
    "Obsidian Grey": {
        "window": (22, 22, 22), "window_text": (200, 200, 200),
        "base": (30, 30, 30), "alt_base": (22, 22, 22),
        "text": (200, 200, 200), "button": (30, 30, 30),
        "button_text": (200, 200, 200), "bright": (255, 140, 60),
        "highlight": (90, 90, 90), "highlight_text": (240, 240, 240),
    },
    "Void Eclipse": {
        "window": (11, 11, 11), "window_text": (190, 190, 200),
        "base": (18, 18, 20), "alt_base": (11, 11, 11),
        "text": (190, 190, 200), "button": (18, 18, 20),
        "button_text": (190, 190, 200), "bright": (120, 80, 220),
        "highlight": (60, 40, 140), "highlight_text": (220, 220, 230),
    },
    "Slytherin": {
        "window": (8, 18, 12), "window_text": (180, 220, 195),
        "base": (14, 28, 20), "alt_base": (8, 18, 12),
        "text": (180, 220, 195), "button": (14, 28, 20),
        "button_text": (180, 220, 195), "bright": (190, 200, 180),
        "highlight": (13, 107, 61), "highlight_text": (230, 245, 235),
    },
    "Gryffindor": {
        "window": (24, 8, 8), "window_text": (225, 190, 185),
        "base": (36, 14, 14), "alt_base": (24, 8, 8),
        "text": (225, 190, 185), "button": (36, 14, 14),
        "button_text": (225, 190, 185), "bright": (218, 165, 32),
        "highlight": (127, 9, 9), "highlight_text": (240, 220, 210),
    },
}

def apply_theme(app, theme_name):
    t = THEMES.get(theme_name, THEMES["AMOLED"])
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


