import sys
import os
import json
import fitz  # PyMuPDF
import traceback
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QTreeWidget, QTreeWidgetItem,
    QLabel, QScrollArea, QSplitter, QRubberBand, QToolBar, QInputDialog,
    QMessageBox, QLineEdit, QMenu, QDialog, QGridLayout, QComboBox, QTabWidget, QCheckBox, QKeySequenceEdit,
    QWidgetAction
)
from PyQt6.QtCore import Qt, QRect, QPoint, QSize, pyqtProperty, QPropertyAnimation, QTimer
from PyQt6.QtGui import QPixmap, QImage, QAction, QKeySequence, QShortcut, QColor, QPainter, QPen, QTextDocument, QPdfWriter

# ── Toggle Switch Custom Widget ──────────────────────────────────────────────
class ToggleSwitch(QCheckBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._position = 0
        self.animation = QPropertyAnimation(self, b"position")
        self.animation.setDuration(150)
        self.stateChanged.connect(self.setup_animation)

    @pyqtProperty(float)
    def position(self):
        return self._position

    @position.setter
    def position(self, pos):
        self._position = pos
        self.update()

    def setup_animation(self, value):
        self.animation.stop()
        if value:
            self.animation.setEndValue(1.0)
        else:
            self.animation.setEndValue(0.0)
        self.animation.start()

    def hitButton(self, pos: QPoint):
        return self.contentsRect().contains(pos)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)

        rect = QRect(0, 0, self.width(), self.height())
        
        if not self.isChecked():
            p.setBrush(QColor("#777777"))
            p.drawRoundedRect(0, 0, rect.width(), self.height(), int(self.height() / 2), int(self.height() / 2))
        else:
            p.setBrush(QColor("#4cd964"))
            p.drawRoundedRect(0, 0, rect.width(), self.height(), int(self.height() / 2), int(self.height() / 2))
            
        p.setBrush(QColor("#ffffff"))
        x = self._position * (self.width() - self.height())
        p.drawEllipse(int(x) + 2, 2, self.height() - 4, self.height() - 4)
        p.end()

# ── Theme Definitions ────────────────────────────────────────────────────────
THEMES = {
    "Dark Black": {
        "window": (26, 27, 38), "window_text": (192, 202, 245),
        "base": (36, 40, 59), "alt_base": (26, 27, 38),
        "text": (192, 202, 245), "button": (36, 40, 59),
        "button_text": (192, 202, 245), "bright": (247, 118, 142),
        "highlight": (122, 162, 247), "highlight_text": (26, 27, 38),
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


class PDFViewer(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.start_point = QPoint()
        self.end_point = QPoint()
        self.selected_rects = []
        self.search_rects = []
        self.main_window = None
        self.screenshot_mode = False
        self.eraser_mode = False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                if self.main_window:
                    self.main_window.clear_accumulated_selection()
                self.selected_rects = []
            self.start_point = event.pos()
            self.end_point = event.pos()
            self.update()

    def mouseMoveEvent(self, event):
        if not self.start_point.isNull():
            self.end_point = event.pos()
            if self.main_window:
                if self.screenshot_mode:
                    # Show rectangle for screenshot
                    rect = QRect(self.start_point, self.end_point).normalized()
                    self.selected_rects = [rect]
                    self.update()
                else:
                    self.main_window.update_selection_overlay()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.end_point = event.pos()
            if self.main_window:
                if self.screenshot_mode:
                    self.main_window.capture_screenshot(self.start_point, self.end_point)
                    self.screenshot_mode = False
                else:
                    append = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                    self.main_window.handle_selection(append=append)

    def clear_selection(self):
        self.start_point = QPoint()
        self.end_point = QPoint()
        self.selected_rects = []
        self.screenshot_mode = False
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        
        # Draw search results (Green)
        if hasattr(self, 'search_rects') and self.search_rects:
            painter.setBrush(QColor(0, 255, 0, 80))
            painter.setPen(Qt.PenStyle.NoPen)
            for rect in self.search_rects:
                painter.drawRect(rect)
                
        # Draw selections (Yellow)
        if self.selected_rects:
            if self.screenshot_mode:
                painter.setBrush(QColor(0, 120, 255, 60))
                painter.setPen(QPen(QColor(0, 120, 255), 2))
            else:
                painter.setBrush(QColor(255, 255, 0, 100))
                painter.setPen(Qt.PenStyle.NoPen)
            for rect in self.selected_rects:
                painter.drawRect(rect)
                
        painter.end()


class MainWindow(QMainWindow):
    SETTINGS_FILE = "annotator_settings.json"
    DEFAULT_SHORTCUTS = {
        "h1": "Alt+1",
        "h2": "Alt+2",
        "h3": "Alt+3",
        "h4": "Alt+4",
        "note": "Ctrl+Shift+V",
        "custom_note": "Ctrl+N",
        "search": "Ctrl+F",
        "clear_selection": "Esc",
        "prev_page": "Left",
        "next_page": "Right",
        "cheatsheet": "F1",
        "screenshot": "Ctrl+Shift+S"
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Annotator for Obsidian")
        self.resize(1200, 800)

        # State
        self.doc = None
        self.pdf_path = ""
        self.current_page_idx = 0
        self.zoom_factor = 2.0
        self.annotations = []
        self.current_selection_text = ""
        self.current_selection_fitz_rects = []
        self.accumulated_qrects = []
        self.source_title = "Untitled_PDF"
        self.vault_path = ""
        self.night_mode = False
        self.save_to_pdf_mode = True
        self.theme_name = "Dark Black"
        self.recent_files = []
        self.bookmarks = {}  # {pdf_path: page_idx}
        self.screenshot_counter = 0

        # Debounced PDF save timer — prevents blocking UI on every annotation
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(2000)  # Save 2 seconds after last change
        self._save_timer.timeout.connect(self._do_save_pdf)

        # Heading context
        self.current_h1 = None
        self.current_h2 = None
        self.current_h3 = None
        self.current_h4 = None

        self.setup_ui()
        self.load_settings()
        self.setup_shortcuts()

    def setup_ui(self):
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        open_action = QAction("📂 Open", self)
        open_action.triggered.connect(self.open_pdf)
        toolbar.addAction(open_action)

        # Recent files button
        self.recent_btn = QPushButton("📋 Recent")
        self.recent_btn.setFlat(True)
        self.recent_btn.clicked.connect(self.show_recent_files)
        toolbar.addWidget(self.recent_btn)

        load_action = QAction("📄 Load MD", self)
        load_action.triggered.connect(self.load_markdown)
        toolbar.addAction(load_action)

        toolbar.addSeparator()

        prev_action = QAction("⬅", self)
        prev_action.triggered.connect(self.prev_page)
        toolbar.addAction(prev_action)

        self.page_input = QLineEdit("0")
        self.page_input.setFixedWidth(40)
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_input.returnPressed.connect(self.go_to_page)
        toolbar.addWidget(self.page_input)

        self.page_label = QLabel(" / 0 ")
        toolbar.addWidget(self.page_label)

        next_action = QAction("➡", self)
        next_action.triggered.connect(self.next_page)
        toolbar.addAction(next_action)

        # Bookmark button
        bookmark_action = QAction("🔖 Bookmark", self)
        bookmark_action.triggered.connect(self.goto_bookmark)
        toolbar.addAction(bookmark_action)

        toolbar.addSeparator()

        zoom_out_action = QAction("🔍-", self)
        zoom_out_action.triggered.connect(self.zoom_out)
        toolbar.addAction(zoom_out_action)

        zoom_in_action = QAction("🔍+", self)
        zoom_in_action.triggered.connect(self.zoom_in)
        toolbar.addAction(zoom_in_action)

        # Night mode toggle
        self.night_action = QAction("🌙 Night", self)
        self.night_action.setCheckable(True)
        self.night_action.triggered.connect(self.toggle_night_mode)
        toolbar.addAction(self.night_action)

        # Save to PDF toggle widget
        toggle_widget = QWidget()
        toggle_layout = QHBoxLayout(toggle_widget)
        toggle_layout.setContentsMargins(5, 0, 5, 0)
        toggle_label = QLabel("Save highlights to PDF:")
        self.save_pdf_switch = ToggleSwitch()
        self.save_pdf_switch.toggled.connect(self.toggle_save_pdf_mode)
        toggle_layout.addWidget(toggle_label)
        toggle_layout.addWidget(self.save_pdf_switch)
        toolbar.addWidget(toggle_widget)

        # Screenshot
        screenshot_action = QAction("📸 Screenshot", self)
        screenshot_action.triggered.connect(self.start_screenshot_mode)
        toolbar.addAction(screenshot_action)

        toolbar.addSeparator()

        # Theme selector
        toolbar.addWidget(QLabel(" Theme: "))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(THEMES.keys())
        self.theme_combo.currentTextChanged.connect(self.change_theme)
        self.theme_combo.setFixedWidth(110)
        toolbar.addWidget(self.theme_combo)

        toolbar.addSeparator()

        vault_action = QAction("⚙ Vault", self)
        vault_action.triggered.connect(self.set_vault)
        toolbar.addAction(vault_action)

        export_action = QAction("💾 Save", self)
        export_action.triggered.connect(self.export_markdown)
        toolbar.addAction(export_action)

        export_pdf_action = QAction("📄 Export PDF", self)
        export_pdf_action.triggered.connect(self.export_pdf)
        toolbar.addAction(export_pdf_action)

        # Central Widget -> Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        # Left side: Search Bar + PDF Viewer
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # Search Bar UI (hidden by default)
        self.search_bar_widget = QWidget()
        self.search_bar_widget.setStyleSheet("background: #24283b; border-bottom: 1px solid #1a1b26;")
        search_layout = QHBoxLayout(self.search_bar_widget)
        search_layout.setContentsMargins(10, 5, 10, 5)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Find in PDF (Ctrl+F)...")
        self.search_input.returnPressed.connect(self.search_next)
        
        self.search_prev_btn = QPushButton("↑ Prev")
        self.search_prev_btn.clicked.connect(self.search_prev)
        self.search_next_btn = QPushButton("↓ Next")
        self.search_next_btn.clicked.connect(self.search_next)
        
        self.search_close_btn = QPushButton("❌")
        self.search_close_btn.setFlat(True)
        self.search_close_btn.clicked.connect(self.hide_search)
        
        search_layout.addWidget(QLabel("🔍"))
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_prev_btn)
        search_layout.addWidget(self.search_next_btn)
        search_layout.addWidget(self.search_close_btn)
        self.search_bar_widget.hide()
        
        left_layout.addWidget(self.search_bar_widget)

        self.scroll_area = QScrollArea()
        self.viewer = PDFViewer()
        self.viewer.main_window = self
        self.scroll_area.setWidget(self.viewer)
        self.scroll_area.setWidgetResizable(True)
        left_layout.addWidget(self.scroll_area)
        
        splitter.addWidget(left_panel)

        # Right side: Tabbed Panel for Annotations and Outline
        right_panel = QTabWidget()
        
        # Annotations Tab
        annot_tab = QWidget()
        annot_layout = QVBoxLayout(annot_tab)
        annot_layout.setContentsMargins(5, 5, 5, 5)
        
        self.context_label = QLabel("Context: Root")
        self.context_label.setStyleSheet("font-weight: bold; color: #bb9af7;")
        annot_layout.addWidget(self.context_label)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Annotations"])
        self.tree_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_tree_context_menu)
        self.tree_widget.itemClicked.connect(self.on_tree_clicked)
        annot_layout.addWidget(self.tree_widget)
        
        right_panel.addTab(annot_tab, "Annotations")
        
        # Outline (TOC) Tab
        outline_tab = QWidget()
        outline_layout = QVBoxLayout(outline_tab)
        outline_layout.setContentsMargins(5, 5, 5, 5)
        
        self.outline_widget = QTreeWidget()
        self.outline_widget.setHeaderLabels(["Table of Contents"])
        self.outline_widget.itemClicked.connect(self.on_outline_clicked)
        outline_layout.addWidget(self.outline_widget)
        
        right_panel.addTab(outline_tab, "Outline")

        splitter.addWidget(right_panel)
        splitter.setSizes([800, 400])

    def setup_shortcuts(self):
        if hasattr(self, 'active_shortcuts'):
            for s in self.active_shortcuts:
                s.setEnabled(False)
                s.deleteLater()
        self.active_shortcuts = []

        def sc(keys, slot):
            if not keys: return None
            s = QShortcut(QKeySequence(keys), self)
            s.setContext(Qt.ShortcutContext.ApplicationShortcut)
            s.activated.connect(slot)
            self.active_shortcuts.append(s)
            return s

        sc(self.shortcuts.get("h1"), lambda: self.add_annotation("h1"))
        sc(self.shortcuts.get("h2"), lambda: self.add_annotation("h2"))
        sc(self.shortcuts.get("h3"), lambda: self.add_annotation("h3"))
        sc(self.shortcuts.get("h4"), lambda: self.add_annotation("h4"))
        sc(self.shortcuts.get("note"), lambda: self.add_annotation("note"))
        sc(self.shortcuts.get("custom_note"), lambda: self.add_annotation("custom_note"))
        sc(self.shortcuts.get("search"), self.show_search)
        sc(self.shortcuts.get("clear_selection"), self.handle_esc)
        sc(self.shortcuts.get("prev_page"), self.prev_page)
        sc(self.shortcuts.get("next_page"), self.next_page)
        sc(self.shortcuts.get("cheatsheet"), self.show_cheatsheet)
        sc(self.shortcuts.get("screenshot"), self.start_screenshot_mode)

    # ── Settings ─────────────────────────────────────────────────────────────
    def load_settings(self):
        self.shortcuts = dict(MainWindow.DEFAULT_SHORTCUTS)
        if os.path.exists(self.SETTINGS_FILE):
            try:
                with open(self.SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                self.vault_path = data.get("vault_path", "")
                self.recent_files = data.get("recent_files", [])
                self.bookmarks = data.get("bookmarks", {})
                self.theme_name = data.get("theme", "Dark Black")
                self.night_mode = data.get("night_mode", False)
                self.save_to_pdf_mode = data.get("save_to_pdf_mode", True)
                self.shortcuts.update(data.get("shortcuts", {}))
                self.night_action.setChecked(self.night_mode)
                self.save_pdf_switch.setChecked(self.save_to_pdf_mode)
                self.theme_combo.setCurrentText(self.theme_name)
                apply_theme(QApplication.instance(), self.theme_name)
            except:
                pass

    def save_settings(self):
        data = {
            "vault_path": self.vault_path,
            "recent_files": self.recent_files[:10],
            "bookmarks": self.bookmarks,
            "theme": self.theme_name,
            "night_mode": self.night_mode,
            "save_to_pdf_mode": self.save_to_pdf_mode,
            "shortcuts": self.shortcuts,
        }
        with open(self.SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def set_vault(self):
        path = QFileDialog.getExistingDirectory(self, "Select Obsidian Vault Directory", self.vault_path)
        if path:
            self.vault_path = path
            self.save_settings()
            QMessageBox.information(self, "Vault Set", f"Obsidian vault set to:\n{self.vault_path}")

    # ── Theme ────────────────────────────────────────────────────────────────
    def change_theme(self, name):
        self.theme_name = name
        apply_theme(QApplication.instance(), name)
        self.save_settings()

    # ── Night Mode & PDF Save ────────────────────────────────────────────────
    def toggle_night_mode(self, checked):
        self.night_mode = checked
        self.save_settings()
        if self.doc is not None and not getattr(self.doc, 'is_closed', False):
            self.show_page()

    def toggle_save_pdf_mode(self, checked):
        self.save_to_pdf_mode = checked
        self.save_settings()
        if checked and self.doc:
            self.save_pdf_highlights()

    # ── Recent Files ─────────────────────────────────────────────────────────
    def add_to_recent(self, path):
        path = os.path.abspath(path)
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:10]
        self.save_settings()

    def remove_recent_file(self, path):
        if path in self.recent_files:
            self.recent_files.remove(path)
            self.save_settings()

    def _remove_and_refresh_recent(self, menu, path):
        self.remove_recent_file(path)
        menu.close()
        if self.recent_files:
            self.show_recent_files()

    def show_recent_files(self):
        if not self.recent_files:
            QMessageBox.information(self, "Recent Files", "No recent files yet.")
            return

        menu = QMenu(self)
        for path in list(self.recent_files):
            name = os.path.basename(path)
            
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(10, 2, 10, 2)
            layout.setSpacing(10)
            
            btn_open = QPushButton(f"📄 {name}")
            btn_open.setToolTip(path)
            btn_open.setStyleSheet("text-align: left; background: transparent; border: none;")
            btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
            
            btn_remove = QPushButton("❌")
            btn_remove.setToolTip("Remove from recents")
            btn_remove.setStyleSheet("background: transparent; border: none; color: red;")
            btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_remove.setFixedWidth(24)
            
            layout.addWidget(btn_open)
            layout.addWidget(btn_remove)
            
            action = QWidgetAction(menu)
            action.setDefaultWidget(widget)
            
            btn_open.clicked.connect(lambda checked, p=path: (menu.close(), self.open_pdf_path(p)))
            btn_remove.clicked.connect(lambda checked, p=path, m=menu: self._remove_and_refresh_recent(m, p))
            
            menu.addAction(action)

        menu.exec(self.recent_btn.mapToGlobal(QPoint(0, self.recent_btn.height())))

    # ── Bookmark ─────────────────────────────────────────────────────────────
    def save_bookmark(self):
        if self.pdf_path:
            self.bookmarks[self.pdf_path] = self.current_page_idx
            self.save_settings()

    def goto_bookmark(self):
        if not self.pdf_path:
            self.statusBar().showMessage("No PDF open.", 3000)
            return
        page = self.bookmarks.get(self.pdf_path, None)
        if page is not None:
            self.current_page_idx = page
            self.show_page()
            self.statusBar().showMessage(f"Jumped to bookmarked page {page + 1}", 3000)
        else:
            self.statusBar().showMessage("No bookmark saved for this PDF.", 3000)

    # ── Screenshot ───────────────────────────────────────────────────────────
    def start_screenshot_mode(self):
        if self.doc is None or getattr(self.doc, 'is_closed', False):
            self.statusBar().showMessage("Open a PDF first.", 3000)
            return
        self.viewer.screenshot_mode = True
        self.statusBar().showMessage("📸 Screenshot mode: drag a rectangle on the PDF", 0)

    def capture_screenshot(self, p1, p2):
        if self.doc is None or getattr(self.doc, 'is_closed', False):
            return
        rect = QRect(p1, p2).normalized()
        if rect.width() < 10 or rect.height() < 10:
            self.viewer.clear_selection()
            return

        # Grab the pixmap region
        pixmap = self.viewer.pixmap()
        if not pixmap:
            return
        cropped = pixmap.copy(rect)

        # Save to vault
        if not self.vault_path:
            self.statusBar().showMessage("Set Obsidian Vault first to save screenshots.", 3000)
            return

        img_dir = os.path.join(self.vault_path, "attachments")
        os.makedirs(img_dir, exist_ok=True)
        self.screenshot_counter += 1
        safe_title = "".join([c for c in self.source_title if c.isalnum() or c in ' -_']).rstrip()
        filename = f"{safe_title}_p{self.current_page_idx + 1}_{self.screenshot_counter}.png"
        filepath = os.path.join(img_dir, filename)
        cropped.save(filepath, "PNG")

        # Add as annotation node
        node = {
            "text": f"![[attachments/{filename}]]",
            "custom_note": "",
            "role": "image",
            "children": [],
            "page": self.current_page_idx + 1,
            "fitz_rects": []
        }
        parent = self.current_h4 or self.current_h3 or self.current_h2 or self.current_h1
        if parent:
            parent["children"].append(node)
        else:
            self.annotations.append(node)

        self.render_tree()
        self.viewer.clear_selection()
        self.export_markdown()
        self.statusBar().showMessage(f"📸 Saved screenshot: {filename}", 3000)

    # ── Cheatsheet ───────────────────────────────────────────────────────────
    def show_cheatsheet(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("⌨ Keyboard Shortcuts")
        dlg.setMinimumSize(450, 450)
        layout = QGridLayout(dlg)

        shortcuts_map = [
            ("h1", "Add H1 Heading"),
            ("h2", "Add H2 Heading"),
            ("h3", "Add H3 Heading"),
            ("h4", "Add H4 Heading"),
            ("note", "Add Note (instant)"),
            ("custom_note", "Add Note (with custom text)"),
            ("screenshot", "Screenshot mode"),
            ("eraser", "Toggle eraser mode"),
            ("prev_page", "Previous page"),
            ("next_page", "Next page"),
            ("clear_selection", "Clear selection"),
            ("search", "Search"),
            ("cheatsheet", "This cheatsheet"),
        ]

        header_key = QLabel("Shortcut")
        header_key.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_action = QLabel("Action")
        header_action.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header_key, 0, 0)
        layout.addWidget(header_action, 0, 1)

        edits = {}
        for i, (key_id, action_desc) in enumerate(shortcuts_map, start=1):
            edit = QKeySequenceEdit(self.shortcuts.get(key_id, ""))
            edits[key_id] = edit
            action_label = QLabel(action_desc)
            action_label.setStyleSheet("font-size: 13px; padding: 4px;")
            layout.addWidget(edit, i, 0)
            layout.addWidget(action_label, i, 1)

        save_btn = QPushButton("Save && Close")
        def on_save():
            for key_id, edit in edits.items():
                self.shortcuts[key_id] = edit.keySequence().toString()
            self.save_settings()
            self.setup_shortcuts()
            dlg.accept()

        save_btn.clicked.connect(on_save)
        layout.addWidget(save_btn, len(shortcuts_map) + 1, 0, 1, 2)
        dlg.exec()

    # ── PDF Open / Navigate ──────────────────────────────────────────────────
    def open_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF Files (*.pdf)")
        if path:
            self.open_pdf_path(path)

    def open_pdf_path(self, path):
        if not os.path.exists(path):
            self.statusBar().showMessage(f"File not found: {path}", 3000)
            return

        # Save bookmark for the current PDF before switching
        self.save_bookmark()

        try:
            self.doc = fitz.open(path)
            # If the XREF is broken, PyMuPDF might report 0 pages
            if len(self.doc) == 0:
                raise ValueError("0 pages found, possible XREF corruption.")
        except Exception as e:
            print(f"Warning: PDF might be corrupted. Attempting auto-repair... ({e})")
            try:
                import pikepdf
                import shutil
                temp_path = path + ".repaired.pdf"
                with pikepdf.open(path) as pdf:
                    pdf.save(temp_path)
                shutil.move(temp_path, path)
                self.doc = fitz.open(path)
            except Exception as repair_e:
                print(f"Repair failed: {repair_e}")
                self.statusBar().showMessage(f"Failed to open or repair corrupted PDF: {path}", 5000)
                return
        self.pdf_path = os.path.abspath(path)
        self.source_title = os.path.splitext(os.path.basename(path))[0]
        self.add_to_recent(path)

        # Reset annotations
        self.annotations = []
        self.current_h1 = None
        self.current_h2 = None
        self.current_h3 = None
        self.current_h4 = None
        self.update_context_label()
        self.render_tree()
        self.load_toc()

        # Restore bookmark if available
        saved_page = self.bookmarks.get(self.pdf_path, 0)
        if 0 <= saved_page < len(self.doc):
            self.current_page_idx = saved_page
        else:
            self.current_page_idx = 0

        self.show_page()

        if saved_page > 0:
            self.statusBar().showMessage(f"Resumed at page {saved_page + 1} (bookmarked)", 3000)

    def prev_page(self):
        if self.doc is not None and not getattr(self.doc, 'is_closed', False) and self.current_page_idx > 0:
            self.current_page_idx -= 1
            self.show_page()
            self.save_bookmark()

    def next_page(self):
        if self.doc is not None and not getattr(self.doc, 'is_closed', False) and self.current_page_idx < len(self.doc) - 1:
            self.current_page_idx += 1
            self.show_page()
            self.save_bookmark()

    def go_to_page(self):
        if self.doc is None or getattr(self.doc, 'is_closed', False):
            return
        try:
            val = int(self.page_input.text()) - 1
            if 0 <= val < len(self.doc):
                self.current_page_idx = val
                self.show_page()
                self.save_bookmark()
            else:
                self.page_input.setText(str(self.current_page_idx + 1))
        except ValueError:
            self.page_input.setText(str(self.current_page_idx + 1))

    def zoom_in(self):
        self.zoom_factor += 0.5
        self.show_page()

    def zoom_out(self):
        if self.zoom_factor > 0.5:
            self.zoom_factor -= 0.5
            self.show_page()

    def show_page(self):
        if self.doc is None or getattr(self.doc, 'is_closed', False):
            return

        self.page_input.setText(str(self.current_page_idx + 1))
        self.page_label.setText(f" / {len(self.doc)} ")
        self.viewer.clear_selection()
        self.clear_accumulated_selection()

        page = self.doc[self.current_page_idx]
        mat = fitz.Matrix(self.zoom_factor, self.zoom_factor)

        # Use annots=False to prevent PyMuPDF crashes on malformed highlights
        pix = page.get_pixmap(matrix=mat, annots=False)

        fmt = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
        # Copy the image so we can safely draw on it
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()

        painter = QPainter(img)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)

            # Snapshot the annotations list to avoid iterator issues
            try:
                annot_list = list(page.annots())
            except Exception:
                annot_list = []

            for annot in annot_list:
                try:
                    if annot.type[0] in (8, 9, 10, 11): # Highlight, Underline, Squiggly, Strikeout
                        color = annot.colors.get("stroke") if annot.colors else None
                        if color and len(color) == 3:
                            r, g, b = int(color[0]*255), int(color[1]*255), int(color[2]*255)
                            painter.setBrush(QColor(r, g, b, 100))
                        else:
                            painter.setBrush(QColor(255, 255, 0, 100))

                        rect = annot.rect
                        x0 = rect.x0 * self.zoom_factor
                        y0 = rect.y0 * self.zoom_factor
                        x1 = rect.x1 * self.zoom_factor
                        y1 = rect.y1 * self.zoom_factor
                        painter.drawRect(int(x0), int(y0), int(x1-x0), int(y1-y0))
                except Exception as e:
                    print(f"Skipping malformed annotation: {e}")
                    continue

            # Draw highlights from our internal markdown tree as a fallback/guarantee
            # This ensures they ALWAYS show up even if save_to_pdf_mode is OFF or PyMuPDF is lagging
            def draw_app_nodes(nodes):
                for n in nodes:
                    if n.get("page") == self.current_page_idx + 1:
                        for rect_coords in n.get("fitz_rects", []):
                            if len(rect_coords) == 4:
                                x0, y0, x1, y1 = rect_coords
                                x0 *= self.zoom_factor
                                y0 *= self.zoom_factor
                                x1 *= self.zoom_factor
                                y1 *= self.zoom_factor
                                # Draw with a slightly different yellow to distinguish if needed, or just same
                                painter.setBrush(QColor(255, 255, 0, 100))
                                painter.drawRect(int(x0), int(y0), int(x1-x0), int(y1-y0))
                    draw_app_nodes(n.get("children", []))
            
            draw_app_nodes(self.annotations)
        finally:
            # CRITICAL: always end the painter, otherwise the QImage stays locked
            # and the entire UI freezes on the next render
            painter.end()

        if self.night_mode:
            img.invertPixels()

        self.viewer.setPixmap(QPixmap.fromImage(img))
        self.viewer.resize(pix.width, pix.height)

    # ── Text Selection ───────────────────────────────────────────────────────
    def handle_esc(self):
        self.viewer.clear_selection()
        self.hide_search()

    def clear_accumulated_selection(self):
        self.current_selection_text = ""
        self.current_selection_fitz_rects = []
        self.accumulated_qrects = []

    def update_selection_overlay(self):
        if self.doc is None or getattr(self.doc, 'is_closed', False) or self.viewer.start_point.isNull():
            return
        rects, _ = self._get_inline_selection(self.viewer.start_point, self.viewer.end_point)
        self.viewer.selected_rects = self.accumulated_qrects + rects
        self.viewer.update()

    def handle_selection(self, append=False):
        if self.doc is None or getattr(self.doc, 'is_closed', False) or self.viewer.start_point.isNull():
            return

        rects, text = self._get_inline_selection(self.viewer.start_point, self.viewer.end_point)

        if not text:
            # If no text is found, just keep whatever was accumulated
            self.viewer.selected_rects = self.accumulated_qrects
            self.viewer.update()
            return

        fitz_rects = []
        for r in rects:
            x0 = r.left() / self.zoom_factor
            y0 = r.top() / self.zoom_factor
            x1 = r.right() / self.zoom_factor
            y1 = r.bottom() / self.zoom_factor
            fitz_rects.append(fitz.Rect(x0, y0, x1, y1))

        if append:
            if self.current_selection_text:
                self.current_selection_text += " " + text
            else:
                self.current_selection_text = text
            self.current_selection_fitz_rects.extend(fitz_rects)
            self.accumulated_qrects.extend(rects)
        else:
            self.current_selection_text = text
            self.current_selection_fitz_rects = fitz_rects
            self.accumulated_qrects = rects

        self.viewer.selected_rects = self.accumulated_qrects
        self.viewer.update()

        self.statusBar().showMessage(f"Selected: {self.current_selection_text[:60]}...", 3000)

    def _get_inline_selection(self, p1, p2):
        if self.doc is None or getattr(self.doc, 'is_closed', False):
            return [], ""

        page = self.doc[self.current_page_idx]
        zf = self.zoom_factor

        sx, sy = p1.x() / zf, p1.y() / zf
        ex, ey = p2.x() / zf, p2.y() / zf

        words = page.get_text("words")
        if not words:
            return [], ""

        words.sort(key=lambda w: (w[1], w[0]))

        lines = []
        current_line = [words[0]]
        for w in words[1:]:
            prev = current_line[-1]
            prev_cy = (prev[1] + prev[3]) / 2
            cur_cy = (w[1] + w[3]) / 2
            line_height = prev[3] - prev[1]
            if abs(cur_cy - prev_cy) < line_height * 0.5:
                current_line.append(w)
            else:
                current_line.sort(key=lambda ww: ww[0])
                lines.append(current_line)
                current_line = [w]
        current_line.sort(key=lambda ww: ww[0])
        lines.append(current_line)

        if sy > ey or (abs(sy - ey) < 5 and sx > ex):
            sx, sy, ex, ey = ex, ey, sx, sy

        selected_words = []
        qrects = []

        for line in lines:
            line_top = min(w[1] for w in line)
            line_bot = max(w[3] for w in line)
            line_cy = (line_top + line_bot) / 2
            line_h = line_bot - line_top

            if line_cy < sy - line_h * 0.3 or line_cy > ey + line_h * 0.3:
                continue

            is_first_line = abs(line_cy - sy) < line_h
            is_last_line = abs(line_cy - ey) < line_h
            is_single_line = is_first_line and is_last_line

            for w in line:
                wcx = (w[0] + w[2]) / 2
                if is_single_line:
                    if wcx >= sx and wcx <= ex:
                        selected_words.append(w[4])
                        qrects.append(QRect(int(w[0]*zf), int(w[1]*zf), int((w[2]-w[0])*zf), int((w[3]-w[1])*zf)))
                elif is_first_line:
                    if wcx >= sx:
                        selected_words.append(w[4])
                        qrects.append(QRect(int(w[0]*zf), int(w[1]*zf), int((w[2]-w[0])*zf), int((w[3]-w[1])*zf)))
                elif is_last_line:
                    if wcx <= ex:
                        selected_words.append(w[4])
                        qrects.append(QRect(int(w[0]*zf), int(w[1]*zf), int((w[2]-w[0])*zf), int((w[3]-w[1])*zf)))
                else:
                    selected_words.append(w[4])
                    qrects.append(QRect(int(w[0]*zf), int(w[1]*zf), int((w[2]-w[0])*zf), int((w[3]-w[1])*zf)))

        text = " ".join(selected_words)
        return qrects, text

    # ── Annotations ──────────────────────────────────────────────────────────
    def add_annotation(self, role):
        if not self.current_selection_text:
            self.statusBar().showMessage(f"Cannot add {role.upper()} — select text first!", 3000)
            return

        text = self.current_selection_text
        custom_note = ""

        if role == "custom_note":
            note_text, ok = QInputDialog.getMultiLineText(self, "Add Custom Note", "Type your note here:", "")
            if not ok or not note_text.strip():
                return
            custom_note = note_text.strip()
            role = "note"

        if self.save_to_pdf_mode and self.doc is not None and not getattr(self.doc, 'is_closed', False):
            page = self.doc[self.current_page_idx]
            for r in self.current_selection_fitz_rects:
                annot = page.add_highlight_annot(r)
                if annot:
                    annot.update()
            self.save_pdf_highlights()
            self.show_page()

        node = {
            "text": text, "custom_note": custom_note, "role": role,
            "children": [], "page": self.current_page_idx + 1,
            "fitz_rects": [[r.x0, r.y0, r.x1, r.y1] for r in self.current_selection_fitz_rects]
        }

        if role == "h1":
            self.annotations.append(node)
            self.current_h1 = node
            self.current_h2 = self.current_h3 = self.current_h4 = None
        elif role == "h2":
            (self.current_h1["children"] if self.current_h1 else self.annotations).append(node)
            self.current_h2 = node
            self.current_h3 = self.current_h4 = None
        elif role == "h3":
            parent = self.current_h2 or self.current_h1
            (parent["children"] if parent else self.annotations).append(node)
            self.current_h3 = node
            self.current_h4 = None
        elif role == "h4":
            parent = self.current_h3 or self.current_h2 or self.current_h1
            (parent["children"] if parent else self.annotations).append(node)
            self.current_h4 = node
        else:
            parent = self.current_h4 or self.current_h3 or self.current_h2 or self.current_h1
            (parent["children"] if parent else self.annotations).append(node)

        self.update_context_label()
        self.render_tree()
        self.viewer.clear_selection()
        self.clear_accumulated_selection()
        self.statusBar().showMessage(f"Added [{role.upper()}]: {text[:40]}...", 3000)
        self.export_markdown()

    # ── Table of Contents ────────────────────────────────────────────────────
    def load_toc(self):
        self.outline_widget.clear()
        if self.doc is None or getattr(self.doc, 'is_closed', False): return
        toc = self.doc.get_toc()
        if not toc:
            item = QTreeWidgetItem(["No Table of Contents available."])
            self.outline_widget.addTopLevelItem(item)
            return
            
        items_by_level = {}
        for level, title, page in toc:
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.ItemDataRole.UserRole, page)
            
            if level == 1:
                self.outline_widget.addTopLevelItem(item)
            else:
                parent = items_by_level.get(level - 1)
                if parent:
                    parent.addChild(item)
                else:
                    self.outline_widget.addTopLevelItem(item)
            items_by_level[level] = item
            
    def on_outline_clicked(self, item, column):
        page = item.data(0, Qt.ItemDataRole.UserRole)
        if page is not None:
            # PyMuPDF TOC pages are 1-based usually
            self.current_page_idx = max(0, page - 1)
            self.show_page()
            self.save_bookmark()

    # ── Search ───────────────────────────────────────────────────────────────
    def show_search(self):
        if self.doc is None or getattr(self.doc, 'is_closed', False): return
        self.search_bar_widget.show()
        self.search_input.setFocus()
        self.search_input.selectAll()
        
    def hide_search(self):
        self.search_bar_widget.hide()
        self.viewer.search_rects = []
        self.viewer.update()
        
    def search_next(self):
        self._do_search(forward=True)
        
    def search_prev(self):
        self._do_search(forward=False)
        
    def _do_search(self, forward=True):
        if self.doc is None or getattr(self.doc, 'is_closed', False): return
        query = self.search_input.text().strip()
        if not query: return
        
        start_page = self.current_page_idx
        pages_to_check = []
        
        if forward:
            pages_to_check = list(range(start_page, len(self.doc))) + list(range(0, start_page))
        else:
            pages_to_check = list(range(start_page, -1, -1)) + list(range(len(self.doc)-1, start_page, -1))
            
        for p_idx in pages_to_check:
            page = self.doc[p_idx]
            rects = page.search_for(query)
            if rects:
                if p_idx != self.current_page_idx:
                    self.current_page_idx = p_idx
                    self.show_page()
                    rects = self.doc[self.current_page_idx].search_for(query)
                
                self.viewer.search_rects = []
                for r in rects:
                    self.viewer.search_rects.append(QRect(
                        int(r.x0 * self.zoom_factor),
                        int(r.y0 * self.zoom_factor),
                        int((r.x1 - r.x0) * self.zoom_factor),
                        int((r.y1 - r.y0) * self.zoom_factor)
                    ))
                self.viewer.update()
                
                first_match = rects[0] if forward else rects[-1]
                
                # Scroll to match
                scrollbar = self.scroll_area.verticalScrollBar()
                if scrollbar:
                    scrollbar.setValue(int(first_match.y0 * self.zoom_factor) - 50)
                
                self.statusBar().showMessage(f"Found '{query}' on page {p_idx + 1}", 3000)
                return
                
        self.statusBar().showMessage(f"'{query}' not found.", 3000)

    def update_context_label(self):
        ctx = "Root"
        if self.current_h4: ctx = f"H4: {self.current_h4['text'][:20]}..."
        elif self.current_h3: ctx = f"H3: {self.current_h3['text'][:20]}..."
        elif self.current_h2: ctx = f"H2: {self.current_h2['text'][:20]}..."
        elif self.current_h1: ctx = f"H1: {self.current_h1['text'][:20]}..."
        self.context_label.setText(f"Context: {ctx}")

    def render_tree(self):
        self.tree_widget.clear()
        self.tree_item_to_node = {}

        def add_nodes(parent_widget, nodes):
            for n in nodes:
                item = QTreeWidgetItem(parent_widget)
                self.tree_item_to_node[id(item)] = n

                role = n["role"]
                if role == "image":
                    display_text = f"📸 [IMAGE] p.{n['page']}"
                elif role == "note":
                    cn = n.get('custom_note', '')
                    display_text = f"[NOTE] {cn[:30]}... ({n['text'][:20]})" if cn else f"[NOTE] {n['text']}"
                elif role == "highlight":
                    display_text = f"[HIGHLIGHT] {n['text']}"
                else:
                    display_text = f"[{role.upper()}] {n['text']}"

                if len(display_text) > 50:
                    display_text = display_text[:50] + "..."

                item.setText(0, display_text)

                colors = {"h1": "#7aa2f7", "h2": "#bb9af7", "h3": "#9ece6a", "h4": "#ff9e64", "image": "#e0af68"}
                item.setForeground(0, QColor(colors.get(role, "#c0caf5")))

                add_nodes(item, n["children"])
                item.setExpanded(True)

        add_nodes(self.tree_widget, self.annotations)

    def show_tree_context_menu(self, pos):
        item = self.tree_widget.itemAt(pos)
        if not item: return
        menu = QMenu(self)
        delete_action = QAction("🗑 Delete", self)
        delete_action.triggered.connect(lambda: self.delete_annotation(item))
        menu.addAction(delete_action)
        menu.exec(self.tree_widget.mapToGlobal(pos))

    def on_tree_clicked(self, item, column):
        node = self.tree_item_to_node.get(id(item))
        if node and "page" in node:
            page_idx = max(0, node["page"] - 1)
            if self.doc is not None and not getattr(self.doc, 'is_closed', False) and 0 <= page_idx < len(self.doc):
                self.current_page_idx = page_idx
                self.show_page()
                self.save_bookmark()

    def delete_annotation(self, item):
        node_to_delete = self.tree_item_to_node.get(id(item))
        if not node_to_delete: return

        def remove_from_list(nodes, target):
            for i, n in enumerate(nodes):
                if n is target:
                    nodes.pop(i)
                    return True
                if remove_from_list(n["children"], target):
                    return True
            return False

        if remove_from_list(self.annotations, node_to_delete):
            def get_all_nodes(nodes):
                res = set()
                for n in nodes:
                    res.add(id(n))
                    res.update(get_all_nodes(n["children"]))
                return res
            
            active = get_all_nodes(self.annotations)
            if self.current_h1 and id(self.current_h1) not in active: self.current_h1 = None
            if self.current_h2 and id(self.current_h2) not in active: self.current_h2 = None
            if self.current_h3 and id(self.current_h3) not in active: self.current_h3 = None
            if self.current_h4 and id(self.current_h4) not in active: self.current_h4 = None
            
            if self.save_to_pdf_mode and self.doc is not None and not getattr(self.doc, 'is_closed', False):
                self.remove_pdf_highlights(node_to_delete)
            # Defer the save to prevent blocking the UI
            self.save_pdf_highlights()
            self.render_tree()
            self.show_page()
            self.export_markdown()

    def remove_pdf_highlights(self, node):
        """Remove PDF highlight annotations matching the given annotation node."""
        if self.doc is None or getattr(self.doc, 'is_closed', False):
            return

        def collect_nodes(n):
            yield n
            for child in n.get("children", []):
                yield from collect_nodes(child)

        for n in collect_nodes(node):
            page_idx = n.get("page", 1) - 1
            if page_idx < 0 or page_idx >= len(self.doc):
                continue

            stored_rects = n.get("fitz_rects", [])
            text = n.get("text", "")

            # Build list of fitz.Rect targets to match against
            target_rects = [fitz.Rect(sr) for sr in stored_rects if len(sr) == 4]
            if not target_rects and text and not text.startswith("![["):
                page = self.doc[page_idx]
                target_rects = page.search_for(text[:50])

            if not target_rects:
                continue

            # Simple loop: delete one matching annotation at a time, re-scan after each
            keep_going = True
            while keep_going:
                keep_going = False
                page = self.doc[page_idx]  # Fresh reference
                try:
                    for annot in page.annots():
                        if annot.type[0] != 8:
                            continue
                        ar = annot.rect
                        for tr in target_rects:
                            if ar.intersects(tr):
                                page.delete_annot(annot)
                                keep_going = True
                                break
                        if keep_going:
                            break  # Restart scan
                except Exception:
                    break

    # ── Export / Import ──────────────────────────────────────────────────────
    def get_markdown(self):
        def render_md(nodes):
            md = ""
            for n in nodes:
                if n["role"] == "image":
                    md += f"\n{n['text']}\n"
                elif n["role"] in ("h1", "h2", "h3", "h4"):
                    hashes = "#" * (int(n["role"][1]) + 1)
                    md += f"\n{hashes} {n['text'].strip()}\n"
                elif n["role"] == "note":
                    text = n['text'].strip().replace('\n', ' ')
                    md += f"\n> [!quote] p.{n['page']}\n> {text}\n"
                    cn = n.get('custom_note', '').strip().replace('\n', ' ')
                    if cn:
                        md += f"\n- 📝 **Note:** {cn}\n"
                else:
                    text = n['text'].strip().replace('\n', ' ')
                    md += f"\n> [!quote] p.{n['page']}\n> {text}\n"
                if n["children"]:
                    md += render_md(n["children"])
            return md

        now = datetime.now().strftime("%Y-%m-%d")
        markdown = f"---\ntitle: \"{self.source_title}\"\ndate_annotated: {now}\ntags: [annotations/pdf]\n---\n\n"
        markdown += f"# {self.source_title}\n\n"
        if self.annotations:
            markdown += render_md(self.annotations)
        return markdown

    def export_markdown(self):
        if not self.vault_path:
            return
        markdown = self.get_markdown()
        if not markdown: return

        safe_title = "".join([c for c in self.source_title if c.isalnum() or c in ' -_']).rstrip()
        filename = f"{safe_title} Annotations.md"
        filepath = os.path.join(self.vault_path, filename)

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(markdown)
            self.statusBar().showMessage(f"Auto-saved to {filename}", 3000)
            self.save_pdf_highlights()
        except Exception as e:
            self.statusBar().showMessage(f"Error saving: {e}", 5000)

    def export_pdf(self):
        markdown = self.get_markdown()
        if not markdown:
            self.statusBar().showMessage("No annotations to export.", 3000)
            return
        
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF", f"{self.source_title}_Notes.pdf", "PDF Files (*.pdf)")
        if not path: return
        
        try:
            doc = QTextDocument()
            doc.setMarkdown(markdown)
            writer = QPdfWriter(path)
            doc.print(writer)
            self.statusBar().showMessage(f"Exported notes to {os.path.basename(path)}", 3000)
        except Exception as e:
            self.statusBar().showMessage(f"Error exporting PDF: {e}", 5000)

    def save_pdf_highlights(self):
        """Schedule a debounced PDF save — doesn't block the UI."""
        if self.doc is None or getattr(self.doc, 'is_closed', False) or not self.save_to_pdf_mode:
            return
        # Restart the timer (debounce: saves 2s after last change)
        self._save_timer.start()

    def _do_save_pdf(self):
        """Actually perform the PDF save (called by timer or directly after deletion)."""
        if self.doc is None or getattr(self.doc, 'is_closed', False) or not self.save_to_pdf_mode:
            return
        try:
            self.doc.saveIncr()
        except Exception as e:
            print(f"saveIncr failed: {e}")
            # Don't close/reopen the doc — that loses in-memory changes.
            # Instead, try saving to a temp file and swapping.
            try:
                temp_path = self.pdf_path + ".tmp"
                # Use a fast save without expensive garbage collection or deflation
                self.doc.save(temp_path, incremental=False)
                self.doc.close()
                os.replace(temp_path, self.pdf_path)
                self.doc = fitz.open(self.pdf_path)
                print("Saved via full-save fallback.")
            except Exception as e2:
                print(f"Full save also failed: {e2}")
                # If doc got closed but reopen failed, try to recover
                if getattr(self.doc, 'is_closed', True):
                    try:
                        self.doc = fitz.open(self.pdf_path)
                    except Exception:
                        self.doc = None
                        self.statusBar().showMessage("⚠ PDF save failed. Reopen the PDF.", 10000)

    def load_markdown(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Markdown Session", self.vault_path, "Markdown Files (*.md)")
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            self.annotations = []
            self.current_h1 = self.current_h2 = self.current_h3 = self.current_h4 = None

            in_frontmatter = False
            frontmatter_count = 0
            current_page = 1

            for line in lines:
                line = line.strip()
                if line == "---":
                    frontmatter_count += 1
                    in_frontmatter = (frontmatter_count % 2 != 0)
                    continue
                if in_frontmatter or not line:
                    continue

                # Image embeds
                if line.startswith("![["):
                    node = {"text": line, "custom_note": "", "role": "image", "children": [], "page": current_page, "fitz_rects": []}
                    parent = self.current_h4 or self.current_h3 or self.current_h2 or self.current_h1
                    (parent["children"] if parent else self.annotations).append(node)
                    continue

                if line.startswith("##### "):
                    node = {"text": line[6:].strip(), "role": "h4", "children": [], "page": current_page, "fitz_rects": []}
                    parent = self.current_h3 or self.current_h2 or self.current_h1
                    (parent["children"] if parent else self.annotations).append(node)
                    self.current_h4 = node
                elif line.startswith("#### "):
                    node = {"text": line[5:].strip(), "role": "h3", "children": [], "page": current_page, "fitz_rects": []}
                    parent = self.current_h2 or self.current_h1
                    (parent["children"] if parent else self.annotations).append(node)
                    self.current_h3 = node
                    self.current_h4 = None
                elif line.startswith("### "):
                    node = {"text": line[4:].strip(), "role": "h2", "children": [], "page": current_page, "fitz_rects": []}
                    (self.current_h1["children"] if self.current_h1 else self.annotations).append(node)
                    self.current_h2 = node
                    self.current_h3 = self.current_h4 = None
                elif line.startswith("## "):
                    node = {"text": line[3:].strip(), "role": "h1", "children": [], "page": current_page, "fitz_rects": []}
                    self.annotations.append(node)
                    self.current_h1 = node
                    self.current_h2 = self.current_h3 = self.current_h4 = None
                elif line.startswith("# "):
                    pass  # Document title
                elif line.startswith("> [!quote] p."):
                    try: current_page = int(line[13:].strip())
                    except: current_page = 1
                elif line.startswith("> "):
                    text = line[2:].strip()
                    node = {"text": text, "role": "highlight", "children": [], "page": current_page, "fitz_rects": []}
                    parent = self.current_h4 or self.current_h3 or self.current_h2 or self.current_h1
                    (parent["children"] if parent else self.annotations).append(node)
                    if self.save_to_pdf_mode and self.doc is not None and not getattr(self.doc, 'is_closed', False) and 0 <= current_page - 1 < len(self.doc):
                        page = self.doc[current_page - 1]
                        rects = page.search_for(text)
                        for r in rects:
                            # Prevent stacking by checking if a highlight already exists here
                            exists = False
                            for annot in page.annots():
                                if annot.type[0] == 8 and annot.rect.intersects(r):
                                    exists = True
                                    break
                            if not exists:
                                annot = page.add_highlight_annot(r)
                                if annot:
                                    annot.update()
                elif line.startswith("**Note:**"):
                    parent = self.current_h4 or self.current_h3 or self.current_h2 or self.current_h1
                    container = parent["children"] if parent else self.annotations
                    if container and container[-1]["role"] == "highlight":
                        container[-1]["role"] = "note"
                        container[-1]["custom_note"] = line[9:].strip()

            self.update_context_label()
            self.render_tree()
            if self.doc is not None and not getattr(self.doc, 'is_closed', False):
                self.show_page()
            self.statusBar().showMessage(f"Loaded session from {os.path.basename(path)}", 3000)
            self.source_title = os.path.splitext(os.path.basename(path))[0].replace(" Annotations", "")

        except Exception as e:
            self.statusBar().showMessage(f"Error loading: {e}", 5000)

    def closeEvent(self, event):
        # Flush any pending debounced PDF save before closing
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._do_save_pdf()
        self.save_bookmark()
        self.save_settings()
        event.accept()


def global_exception_handler(exc_type, exc_value, exc_traceback):
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print("CRASH:", msg)
    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle("Application Crashed")
    box.setText("An unexpected error occurred:")
    box.setDetailedText(msg)
    box.exec()

if __name__ == "__main__":
    sys.excepthook = global_exception_handler
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_theme(app, "Dark Black")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
