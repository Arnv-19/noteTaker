"""PDF Annotator — main window and application entry point.

Architecture:
    theme.py      themes, color palettes, global stylesheet
    widgets.py    small reusable widgets (ToggleSwitch)
    viewer.py     the PDF page viewer (selection, ink strokes, sketch clicks)
    sketch.py     the Sketch Sticky drawing canvas dialog
    nodes.py      annotation node schema, factories, tree helpers
    pdf_store.py  ALL PDF I/O: open/repair, saves, annot writes/removal/sync
    main.py       MainWindow: UI wiring, annotation tree, tabs, exports
"""
import sys
import os
import json
import csv
import fitz  # PyMuPDF
import traceback
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QTreeWidget, QTreeWidgetItem,
    QLabel, QScrollArea, QSplitter, QToolBar, QInputDialog,
    QMessageBox, QLineEdit, QMenu, QDialog, QGridLayout, QComboBox,
    QTabWidget, QCheckBox, QKeySequenceEdit, QWidgetAction, QSizePolicy,
    QAbstractItemView, QTabBar, QTextBrowser, QPlainTextEdit, QStackedWidget
)
import re
import shutil
from PyQt6.QtCore import Qt, QRect, QPoint, QSize, QTimer, QUrl, QEvent
from PyQt6.QtGui import (QPixmap, QImage, QAction, QKeySequence, QShortcut,
                         QColor, QPainter, QPen, QTextDocument, QPdfWriter, QIcon,
                         QFont)

from theme import (THEMES, apply_theme, HIGHLIGHT_COLORS, PEN_COLORS,
                   hl_qcolor, pen_qcolor)
from widgets import ToggleSwitch
from viewer import PDFViewer
from sketch import SketchCanvasDialog
from pdf_store import PdfStore, rects_match
import ppt_convert
import nodes as N

class MainWindow(QMainWindow):
    # self.doc and self.save_to_pdf_mode proxy the PdfStore so every existing
    # read/write site keeps working while I/O stays centralized in one class.
    @property
    def doc(self):
        return self.pdf.doc

    @doc.setter
    def doc(self, value):
        self.pdf.doc = value

    @property
    def save_to_pdf_mode(self):
        return self.pdf.save_enabled

    @save_to_pdf_mode.setter
    def save_to_pdf_mode(self, value):
        self.pdf.save_enabled = bool(value)

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
        self.pdf = PdfStore(self, on_error=lambda m: self.statusBar().showMessage(m, 10000))
        self.setWindowTitle("PDF Annotator for Obsidian")
        self.resize(1200, 800)

        # State
        self.pdf_path = ""
        self.current_page_idx = 0
        self.zoom_factor = 2.0
        self.annotations = []
        self.current_selection_text = ""
        self.current_selection_fitz_rects = []
        self.accumulated_qrects = []
        self.source_title = "Untitled_PDF"
        self.vault_path = ""
        self.notes_root = ""  # sidebar folder — any folder, vault optional
        self.night_mode = False
        self.save_to_pdf_mode = True
        self.theme_name = "AMOLED"
        self.recent_files = []
        self.bookmarks = {}  # {pdf_path: page_idx}
        self.screenshot_counter = 0

        # New feature state
        self.continuous_mode = False          # continuous scroll (3-page window)
        self.markup_style = "Highlight"       # Highlight / Underline / Strikeout / Squiggly
        self.auto_color = False               # color-code by annotation type
        self.role_colors = {"highlight": "Yellow", "note": "Green", "sticky": "Orange",
                            "h1": "Blue", "h2": "Blue", "h3": "Blue", "h4": "Blue"}
        self.screenshot_box = True            # draw a box annot in PDF for area captures
        self.page_offsets = []                # [(page_idx, y_offset_px, height_px)] of rendered window
        self.sel_page_idx = 0                 # page a selection started on
        self.sel_offset = 0                   # y-offset of that page in the viewer
        self._suppress_scroll = False
        self.sessions = {}
        self.draw_mode = False
        self.pen_color_name = "Red"
        self.pen_width = 3
        self.sketch_default_collapsed = True                    # open tabs: path -> saved state


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
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # ── File menu (Open / Recent / Load MD / Vault / Save / Export) ──
        file_btn = QPushButton("☰ File")
        file_btn.setFlat(True)
        file_menu = QMenu(self)
        file_menu.addAction("📂 Open PDF…", self.open_pdf)
        self.recent_menu_action = file_menu.addAction("📋 Recent Files", self.show_recent_files)
        file_menu.addAction("📄 Load Markdown Session…", self.load_markdown)
        file_menu.addAction("📖 Open Markdown File…", self.open_markdown_view)
        file_menu.addAction("📝 New Markdown Note…", self.new_markdown_note)
        file_menu.addAction("✏ Edit Markdown Note…", self.edit_markdown_note)
        file_menu.addSeparator()
        file_menu.addAction("⚙ Set Vault Folder…", self.set_vault)
        file_menu.addSeparator()
        file_menu.addAction("💾 Save Annotations", self.export_markdown)
        file_menu.addAction("🖨 Export Notes as PDF…", self.export_pdf)
        file_menu.addAction("🃏 Export Anki Flashcards…", self.export_anki)
        file_btn.setMenu(file_menu)
        toolbar.addWidget(file_btn)
        # Keep attribute so show_recent_files can anchor its popup
        self.recent_btn = file_btn

        # Vault notes sidebar toggle
        self.vault_toggle_action = QAction("🗂", self)
        self.vault_toggle_action.setToolTip("Toggle vault notes sidebar")
        self.vault_toggle_action.setCheckable(True)
        self.vault_toggle_action.toggled.connect(self.toggle_vault_panel)
        toolbar.addAction(self.vault_toggle_action)

        toolbar.addSeparator()

        # ── Page navigation ──
        prev_action = QAction("‹", self)
        prev_action.setToolTip("Previous page")
        prev_action.triggered.connect(self.prev_page)
        toolbar.addAction(prev_action)

        self.page_input = QLineEdit("0")
        self.page_input.setFixedWidth(44)
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_input.returnPressed.connect(self.go_to_page)
        toolbar.addWidget(self.page_input)

        self.page_label = QLabel(" / 0 ")
        toolbar.addWidget(self.page_label)

        next_action = QAction("›", self)
        next_action.setToolTip("Next page")
        next_action.triggered.connect(self.next_page)
        toolbar.addAction(next_action)

        bookmark_action = QAction("🔖", self)
        bookmark_action.setToolTip("Jump to bookmark (last read page)")
        bookmark_action.triggered.connect(self.goto_bookmark)
        toolbar.addAction(bookmark_action)

        toolbar.addSeparator()

        # ── Zoom ──
        zoom_out_action = QAction("−", self)
        zoom_out_action.setToolTip("Zoom out")
        zoom_out_action.triggered.connect(self.zoom_out)
        toolbar.addAction(zoom_out_action)

        zoom_in_action = QAction("＋", self)
        zoom_in_action.setToolTip("Zoom in")
        zoom_in_action.triggered.connect(self.zoom_in)
        toolbar.addAction(zoom_in_action)

        toolbar.addSeparator()

        # ── Highlight color picker ──
        self.highlight_color_name = "Yellow"
        self.color_btn = QPushButton()
        self.color_btn.setFlat(True)
        self.color_btn.setFixedSize(30, 26)
        self.color_btn.setToolTip("Highlight color")
        color_menu = QMenu(self)
        for cname in HIGHLIGHT_COLORS:
            act = color_menu.addAction(self._color_icon(cname), cname)
            act.triggered.connect(lambda checked, c=cname: self.set_highlight_color(c))
        self.color_btn.setMenu(color_menu)
        toolbar.addWidget(self.color_btn)
        self._refresh_color_btn()

        # ── Markup style selector ──
        self.style_combo = QComboBox()
        self.style_combo.addItems(["Highlight", "Underline", "Strikeout", "Squiggly"])
        self.style_combo.setFixedWidth(100)
        self.style_combo.setToolTip("Markup style for new annotations")
        self.style_combo.currentTextChanged.connect(self.set_markup_style)
        toolbar.addWidget(self.style_combo)

        # ── Pen / draw tool ──
        self.pen_action = QAction("✏", self)
        self.pen_action.setCheckable(True)
        self.pen_action.setToolTip("Freehand pen — draw on the page (saved as PDF ink)")
        self.pen_action.triggered.connect(self.toggle_draw_mode)
        toolbar.addAction(self.pen_action)

        self.pen_opts_btn = QPushButton("▾")
        self.pen_opts_btn.setFlat(True)
        self.pen_opts_btn.setFixedWidth(22)
        self.pen_opts_btn.setToolTip("Pen color & thickness")
        pen_menu = QMenu(self)
        color_sub = pen_menu.addMenu("Color")
        for cname in PEN_COLORS:
            act = color_sub.addAction(self._pen_icon(cname), cname)
            act.triggered.connect(lambda checked, c=cname: self.set_pen_color(c))
        width_sub = pen_menu.addMenu("Thickness")
        for wlabel, wval in [("Fine (1)", 1), ("Thin (2)", 2), ("Medium (3)", 3), ("Thick (5)", 5), ("Marker (8)", 8)]:
            act = width_sub.addAction(wlabel)
            act.triggered.connect(lambda checked, wv=wval: self.set_pen_width(wv))
        pen_menu.addSeparator()
        pen_menu.addAction("🧽 Erase Last Stroke", self.erase_last_ink)
        self.pen_opts_btn.setMenu(pen_menu)
        toolbar.addWidget(self.pen_opts_btn)

        # ── Eraser tool ──
        self.eraser_action = QAction("🧽", self)
        self.eraser_action.setCheckable(True)
        self.eraser_action.setToolTip("Eraser — click any pen stroke, sticky, sketch, or capture box to delete it")
        self.eraser_action.triggered.connect(self.toggle_eraser_mode)
        toolbar.addAction(self.eraser_action)


        # ── Save-to-PDF toggle ──
        toggle_widget = QWidget()
        toggle_layout = QHBoxLayout(toggle_widget)
        toggle_layout.setContentsMargins(8, 0, 8, 0)
        toggle_layout.setSpacing(6)
        toggle_label = QLabel("PDF")
        toggle_label.setToolTip("Save highlights into the PDF file")
        self.save_pdf_switch = ToggleSwitch()
        self.save_pdf_switch.setToolTip("Save highlights into the PDF file")
        self.save_pdf_switch.toggled.connect(self.toggle_save_pdf_mode)
        toggle_layout.addWidget(toggle_label)
        toggle_layout.addWidget(self.save_pdf_switch)
        toolbar.addWidget(toggle_widget)

        # ── Pomodoro Timer ──
        toolbar.addSeparator()
        pomo_widget = QWidget()
        pomo_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        pomo_widget.customContextMenuRequested.connect(self._pomo_context_menu)
        pomo_layout = QHBoxLayout(pomo_widget)
        pomo_layout.setContentsMargins(4, 0, 4, 0)
        pomo_layout.setSpacing(4)

        self.pomo_label = QLabel("25:00")
        self.pomo_label.setToolTip("Timer  |  Right-click for options")
        self.pomo_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        pomo_layout.addWidget(self.pomo_label)

        self.pomo_start_btn = QPushButton("▶")
        self.pomo_start_btn.setFixedSize(26, 26)
        self.pomo_start_btn.setToolTip("Start / Pause")
        self.pomo_start_btn.clicked.connect(self.pomo_toggle)
        pomo_layout.addWidget(self.pomo_start_btn)

        self.pomo_reset_btn = QPushButton("⟲")
        self.pomo_reset_btn.setFixedSize(26, 26)
        self.pomo_reset_btn.setToolTip("Reset timer")
        self.pomo_reset_btn.clicked.connect(self.pomo_reset)
        pomo_layout.addWidget(self.pomo_reset_btn)

        toolbar.addWidget(pomo_widget)

        # Timer state
        self._pomo_mode = "pomodoro"      # pomodoro / stopwatch
        self._pomo_focus_min = 25
        self._pomo_break_min = 5
        self._pomo_long_break_min = 15
        self._pomo_seconds = self._pomo_focus_min * 60
        self._pomo_running = False
        self._pomo_phase = "focus"       # focus / break / long_break
        self._pomo_count = 0             # completed pomodoros
        self._pomo_timer = QTimer(self)
        self._pomo_timer.setInterval(1000)
        self._pomo_timer.timeout.connect(self._pomo_tick)

        # Spacer pushes view controls to the right edge
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # ── View / tools (right-aligned) ──
        self.continuous_action = QAction("📜", self)
        self.continuous_action.setToolTip("Continuous scroll mode")
        self.continuous_action.setCheckable(True)
        self.continuous_action.triggered.connect(self.toggle_continuous_mode)
        toolbar.addAction(self.continuous_action)

        self.night_action = QAction("🌙", self)
        self.night_action.setToolTip("Night mode (invert page colors)")
        self.night_action.setCheckable(True)
        self.night_action.triggered.connect(self.toggle_night_mode)
        toolbar.addAction(self.night_action)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(THEMES.keys())
        self.theme_combo.currentTextChanged.connect(self.change_theme)
        self.theme_combo.setFixedWidth(110)
        self.theme_combo.setToolTip("Theme")
        toolbar.addWidget(self.theme_combo)

        # Overflow menu: less-used tools
        more_btn = QPushButton("⋯")
        more_btn.setFlat(True)
        more_btn.setToolTip("More tools")
        more_menu = QMenu(self)
        more_menu.addAction("📸 Screenshot Region", self.start_screenshot_mode)
        more_menu.addSeparator()
        more_menu.addAction("🧹 Clear Annotations on This Page", self.clear_page_annotations)
        more_menu.addAction("🗑 Clear ALL Annotations…", self.clear_all_annotations)
        more_menu.addSeparator()
        more_menu.addAction("⚙ Settings…", self.show_settings_dialog)
        more_btn.setMenu(more_menu)
        toolbar.addWidget(more_btn)

        # Central Widget -> Tab bar + Splitter
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        self.doc_tabs = QTabBar()
        self.doc_tabs.setTabsClosable(True)
        self.doc_tabs.setMovable(True)
        self.doc_tabs.setExpanding(False)
        self.doc_tabs.currentChanged.connect(self.on_tab_changed)
        self.doc_tabs.tabCloseRequested.connect(self.on_tab_close)
        self.doc_tabs.tabBarClicked.connect(lambda _i: self.show_pdf_center())
        self.doc_tabs.hide()  # shown once a PDF is open
        central_layout.addWidget(self.doc_tabs)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        central_layout.addWidget(splitter)
        self.setCentralWidget(central)

        # Vault Notes sidebar (leftmost) — lists every .md note in the vault
        self.vault_panel = QWidget()
        vault_layout = QVBoxLayout(self.vault_panel)
        vault_layout.setContentsMargins(4, 4, 4, 4)
        vault_layout.setSpacing(4)
        vhead = QHBoxLayout()
        vhead.setContentsMargins(4, 2, 2, 2)
        self.vault_panel_label = QLabel("🗂 Notes")
        vhead.addWidget(self.vault_panel_label)
        vhead.addStretch()
        vfolder_btn = QPushButton("📂")
        vfolder_btn.setFlat(True)
        vfolder_btn.setFixedWidth(26)
        vfolder_btn.setToolTip("Browse any folder (vault not required)")
        vfolder_btn.clicked.connect(self.choose_notes_folder)
        vhead.addWidget(vfolder_btn)
        vnew_btn = QPushButton("＋")
        vnew_btn.setFlat(True)
        vnew_btn.setFixedWidth(26)
        vnew_btn.setToolTip("New note")
        vnew_btn.clicked.connect(self.new_markdown_note)
        vrefresh_btn = QPushButton("⟳")
        vrefresh_btn.setFlat(True)
        vrefresh_btn.setFixedWidth(26)
        vrefresh_btn.setToolTip("Refresh vault")
        vrefresh_btn.clicked.connect(self.refresh_vault_tree)
        vhead.addWidget(vnew_btn)
        vhead.addWidget(vrefresh_btn)
        vault_layout.addLayout(vhead)
        self.vault_tree = QTreeWidget()
        self.vault_tree.setHeaderHidden(True)
        self.vault_tree.itemClicked.connect(self.on_vault_item_clicked)
        self.vault_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.vault_tree.customContextMenuRequested.connect(self.show_vault_tree_menu)
        vault_layout.addWidget(self.vault_tree)
        splitter.addWidget(self.vault_panel)
        self.vault_panel.hide()  # shown via toggle / when a vault is set

        # Left side: Search Bar + PDF Viewer
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # Search Bar UI (hidden by default)
        self.search_bar_widget = QWidget()
        self.search_bar_widget.setStyleSheet("border-bottom: 1px solid rgba(255,255,255,15);")
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
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.on_viewer_scrolled)

        # Center stack: page 0 = the PDF view, page 1 = note tabs.
        # Notes open here in the middle (like PDFs do), not in extra windows.
        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self.scroll_area)
        self.notes_tabs = QTabWidget()
        self.notes_tabs.setTabsClosable(True)
        self.notes_tabs.setDocumentMode(True)
        self.notes_tabs.setMovable(True)
        self.notes_tabs.tabCloseRequested.connect(self.on_note_tab_close)
        self.notes_tabs.currentChanged.connect(lambda _i: self.refresh_outline())
        self.center_stack.addWidget(self.notes_tabs)
        left_layout.addWidget(self.center_stack)

        splitter.addWidget(left_panel)

        # Right side: Tabbed Panel for Annotations and Outline
        right_panel = QTabWidget()
        
        # Annotations Tab
        annot_tab = QWidget()
        annot_layout = QVBoxLayout(annot_tab)
        annot_layout.setContentsMargins(5, 5, 5, 5)
        
        self.context_label = QLabel("Context: Root")
        self.context_label.setStyleSheet("font-weight: bold;")
        annot_layout.addWidget(self.context_label)

        # Annotation filter/search box
        self.tree_filter_input = QLineEdit()
        self.tree_filter_input.setPlaceholderText("🔍 Filter annotations…")
        self.tree_filter_input.setClearButtonEnabled(True)
        self.tree_filter_input.textChanged.connect(self.filter_tree)
        annot_layout.addWidget(self.tree_filter_input)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Annotations"])
        self.tree_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_tree_context_menu)
        self.tree_widget.itemClicked.connect(self.on_tree_clicked)
        # Drag-to-reorder
        self.tree_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tree_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.tree_widget.model().rowsMoved.connect(self.on_tree_reordered)
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

        # Review Tab: flat list of every highlight/note, filterable by color
        review_tab = QWidget()
        review_layout = QVBoxLayout(review_tab)
        review_layout.setContentsMargins(5, 5, 5, 5)

        review_filter_row = QHBoxLayout()
        self.review_color_filter = QComboBox()
        self.review_color_filter.addItem("All colors")
        self.review_color_filter.addItems(HIGHLIGHT_COLORS.keys())
        self.review_color_filter.currentTextChanged.connect(lambda _t: self.refresh_review())
        review_filter_row.addWidget(QLabel("Filter:"))
        review_filter_row.addWidget(self.review_color_filter, 1)
        review_layout.addLayout(review_filter_row)

        self.review_list = QTreeWidget()
        self.review_list.setHeaderLabels(["Highlight", "Page"])
        self.review_list.setRootIsDecorated(False)
        self.review_list.setColumnWidth(0, 260)
        self.review_list.itemClicked.connect(self.on_review_clicked)
        review_layout.addWidget(self.review_list)

        right_panel.addTab(review_tab, "Review")

        splitter.addWidget(right_panel)
        splitter.setSizes([230, 800, 400])

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
                self.notes_root = data.get("notes_root", "")
                self.recent_files = data.get("recent_files", [])
                self.bookmarks = data.get("bookmarks", {})
                self.theme_name = data.get("theme", "AMOLED")
                self.night_mode = data.get("night_mode", False)
                self.save_to_pdf_mode = data.get("save_to_pdf_mode", True)
                self.highlight_color_name = data.get("highlight_color", "Yellow")
                if self.highlight_color_name not in HIGHLIGHT_COLORS:
                    self.highlight_color_name = "Yellow"
                self._refresh_color_btn()
                self.continuous_mode = data.get("continuous_mode", False)
                self.markup_style = data.get("markup_style", "Highlight")
                self.auto_color = data.get("auto_color", False)
                saved_rc = data.get("role_colors", {})
                for k, v in saved_rc.items():
                    if v in HIGHLIGHT_COLORS:
                        self.role_colors[k] = v
                self.screenshot_box = data.get("screenshot_box", True)
                self.pen_color_name = data.get("pen_color", "Red")
                if self.pen_color_name not in PEN_COLORS:
                    self.pen_color_name = "Red"
                self.pen_width = data.get("pen_width", 3)
                self.sketch_default_collapsed = data.get("sketch_default_collapsed", True)
                self.continuous_action.setChecked(self.continuous_mode)
                if self.markup_style in ("Highlight", "Underline", "Strikeout", "Squiggly"):
                    self.style_combo.setCurrentText(self.markup_style)
                self.shortcuts.update(data.get("shortcuts", {}))
                self.night_action.setChecked(self.night_mode)
                self.save_pdf_switch.setChecked(self.save_to_pdf_mode)
                self.theme_combo.setCurrentText(self.theme_name)
                apply_theme(QApplication.instance(), self.theme_name)
                # Show the notes sidebar if it was open last time
                has_root = bool(self.vault_path or self.notes_root)
                show_sidebar = data.get("vault_sidebar", has_root)
                self.vault_toggle_action.setChecked(has_root and show_sidebar)
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
            "highlight_color": getattr(self, "highlight_color_name", "Yellow"),
            "continuous_mode": self.continuous_mode,
            "markup_style": self.markup_style,
            "auto_color": self.auto_color,
            "role_colors": self.role_colors,
            "screenshot_box": self.screenshot_box,
            "pen_color": self.pen_color_name,
            "pen_width": self.pen_width,
            "sketch_default_collapsed": self.sketch_default_collapsed,
            "shortcuts": self.shortcuts,
            "vault_sidebar": self.vault_panel.isVisible() if hasattr(self, "vault_panel") else False,
            "notes_root": self.notes_root,
        }
        with open(self.SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def set_vault(self):
        path = QFileDialog.getExistingDirectory(self, "Select Obsidian Vault Directory", self.vault_path)
        if path:
            self.vault_path = path
            self.save_settings()
            self.refresh_vault_tree()
            self.vault_toggle_action.setChecked(True)
            QMessageBox.information(self, "Vault Set", f"Obsidian vault set to:\n{self.vault_path}")

    # ── Theme ────────────────────────────────────────────────────────────────
    def change_theme(self, name):
        self.theme_name = name
        apply_theme(QApplication.instance(), name)
        self.save_settings()

    # ── Timer (Pomodoro + Stopwatch) ────────────────────────────────────────
    def pomo_toggle(self):
        if self._pomo_running:
            self._pomo_timer.stop()
            self._pomo_running = False
            self.pomo_start_btn.setText("▶")
        else:
            self._pomo_timer.start()
            self._pomo_running = True
            self.pomo_start_btn.setText("⏸")

    def pomo_reset(self):
        self._pomo_timer.stop()
        self._pomo_running = False
        self.pomo_start_btn.setText("▶")
        self.pomo_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        if self._pomo_mode == "stopwatch":
            self._pomo_seconds = 0
            self.pomo_label.setText("00:00")
        else:
            self._pomo_phase = "focus"
            self._pomo_seconds = self._pomo_focus_min * 60
            self._pomo_count = 0
            self.pomo_label.setText(f"{self._pomo_focus_min:02d}:00")

    def _pomo_tick(self):
        if self._pomo_mode == "stopwatch":
            self._pomo_seconds += 1
            hrs, rem = divmod(self._pomo_seconds, 3600)
            mins, secs = divmod(rem, 60)
            if hrs > 0:
                self.pomo_label.setText(f"{hrs}:{mins:02d}:{secs:02d}")
            else:
                self.pomo_label.setText(f"{mins:02d}:{secs:02d}")
            return

        # Pomodoro countdown
        self._pomo_seconds -= 1
        mins, secs = divmod(self._pomo_seconds, 60)
        self.pomo_label.setText(f"{mins:02d}:{secs:02d}")

        if self._pomo_seconds <= 0:
            self._pomo_timer.stop()
            self._pomo_running = False
            self.pomo_start_btn.setText("▶")
            if self._pomo_phase == "focus":
                self._pomo_count += 1
                if self._pomo_count % 4 == 0:
                    self._pomo_phase = "long_break"
                    self._pomo_seconds = self._pomo_long_break_min * 60
                    self.pomo_label.setText(f"{self._pomo_long_break_min:02d}:00")
                    self.pomo_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #e0af68;")
                    QMessageBox.information(self, "Pomodoro", f"{self._pomo_count} pomodoros done!\nLong break ({self._pomo_long_break_min} min).")
                else:
                    self._pomo_phase = "break"
                    self._pomo_seconds = self._pomo_break_min * 60
                    self.pomo_label.setText(f"{self._pomo_break_min:02d}:00")
                    self.pomo_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #9ece6a;")
                    QMessageBox.information(self, "Pomodoro", f"Focus done! Break ({self._pomo_break_min} min).")
            else:
                self._pomo_phase = "focus"
                self._pomo_seconds = self._pomo_focus_min * 60
                self.pomo_label.setText(f"{self._pomo_focus_min:02d}:00")
                self.pomo_label.setStyleSheet("font-weight: bold; font-size: 13px;")
                QMessageBox.information(self, "Pomodoro", "Break over! Ready to focus.")

    def _pomo_context_menu(self, pos):
        menu = QMenu(self)
        # Mode switch
        if self._pomo_mode == "pomodoro":
            menu.addAction("Mode: Pomodoro").setEnabled(False)
            menu.addAction("Switch to Stopwatch", self._pomo_switch_stopwatch)
        else:
            menu.addAction("Mode: Stopwatch").setEnabled(False)
            menu.addAction("Switch to Pomodoro", self._pomo_switch_pomodoro)
        menu.addSeparator()
        if self._pomo_mode == "pomodoro":
            menu.addAction(f"Focus: {self._pomo_focus_min} min").setEnabled(False)
            menu.addAction(f"Break: {self._pomo_break_min} min").setEnabled(False)
            menu.addAction(f"Long break: {self._pomo_long_break_min} min").setEnabled(False)
            menu.addSeparator()
            menu.addAction("Set Focus Time...", self._pomo_set_focus)
            menu.addAction("Set Break Time...", self._pomo_set_break)
            menu.addAction("Set Long Break Time...", self._pomo_set_long_break)
        menu.exec(self.pomo_label.mapToGlobal(pos))

    def _pomo_switch_stopwatch(self):
        self._pomo_mode = "stopwatch"
        self.pomo_reset()

    def _pomo_switch_pomodoro(self):
        self._pomo_mode = "pomodoro"
        self.pomo_reset()

    def _pomo_set_focus(self):
        val, ok = QInputDialog.getInt(self, "Focus Time", "Focus duration (minutes):", self._pomo_focus_min, 1, 120)
        if ok:
            self._pomo_focus_min = val
            self.pomo_reset()

    def _pomo_set_break(self):
        val, ok = QInputDialog.getInt(self, "Break Time", "Break duration (minutes):", self._pomo_break_min, 1, 60)
        if ok:
            self._pomo_break_min = val
            if self._pomo_phase == "break":
                self.pomo_reset()

    def _pomo_set_long_break(self):
        val, ok = QInputDialog.getInt(self, "Long Break Time", "Long break duration (minutes):", self._pomo_long_break_min, 1, 60)
        if ok:
            self._pomo_long_break_min = val
            if self._pomo_phase == "long_break":
                self.pomo_reset()

    # ── Night Mode & PDF Save ────────────────────────────────────────────────
    def toggle_night_mode(self, checked):
        self.night_mode = checked
        self.save_settings()
        if self.doc is not None and not getattr(self.doc, 'is_closed', False):
            self.show_page()

    # ── Highlight Color ──────────────────────────────────────────────────────
    def _color_icon(self, cname, size=16):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(hl_qcolor(cname, 255))
        p.drawEllipse(1, 1, size - 2, size - 2)
        p.end()
        return QIcon(pm)

    def _refresh_color_btn(self):
        self.color_btn.setIcon(self._color_icon(self.highlight_color_name, 18))
        self.color_btn.setIconSize(QSize(18, 18))

    def set_highlight_color(self, cname):
        self.highlight_color_name = cname
        self._refresh_color_btn()
        self.save_settings()
        self.statusBar().showMessage(f"Highlight color: {cname}", 2000)

    # ── Clear Annotations ────────────────────────────────────────────────────
    def clear_page_annotations(self):
        if self.doc is None or getattr(self.doc, 'is_closed', False):
            return
        page_num = self.current_page_idx + 1

        def prune(nodes):
            removed = []
            kept = []
            for n in nodes:
                n["children"], child_removed = prune(n["children"])
                removed.extend(child_removed)
                # Only remove leaf-style annotations on this page; keep headers with surviving children
                if n.get("page") == page_num and n["role"] in ("highlight", "note", "image") :
                    removed.append(n)
                else:
                    kept.append(n)
            return kept, removed

        self.annotations, removed = prune(self.annotations)
        if not removed:
            self.statusBar().showMessage("No annotations on this page.", 2000)
            return
        for n in removed:
            self.remove_pdf_highlights(n)
        self._do_save_pdf(force=True)
        self.render_tree()
        self.show_page()
        self.export_markdown()
        self.statusBar().showMessage(f"Cleared {len(removed)} annotation(s) on page {page_num}.", 3000)

    def clear_all_annotations(self):
        if not self.annotations:
            self.statusBar().showMessage("No annotations to clear.", 2000)
            return
        reply = QMessageBox.question(
            self, "Clear ALL Annotations",
            "This will delete every annotation in this session and remove the matching highlights from the PDF.\n\nAre you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        for n in list(self.annotations):
            self.remove_pdf_highlights(n)
        self.annotations = []
        self.current_h1 = self.current_h2 = self.current_h3 = self.current_h4 = None
        self._do_save_pdf(force=True)
        self.update_context_label()
        self.render_tree()
        if self.doc is not None and not getattr(self.doc, 'is_closed', False):
            self.show_page()
        self.export_markdown()
        self.statusBar().showMessage("All annotations cleared.", 3000)

    # ── Edit Annotation ──────────────────────────────────────────────────────
    def edit_annotation(self, item):
        node = self.tree_item_to_node.get(id(item))
        if not node:
            return
        new_text, ok = QInputDialog.getMultiLineText(
            self, "Edit Annotation", "Text:", node.get("text", ""))
        if ok and new_text.strip():
            node["text"] = new_text.strip()
        if node.get("role") == "note" or node.get("custom_note"):
            new_note, ok2 = QInputDialog.getMultiLineText(
                self, "Edit Note", "Note:", node.get("custom_note", ""))
            if ok2:
                node["custom_note"] = new_note.strip()
        self.render_tree()
        self.export_markdown()
        self.statusBar().showMessage("Annotation updated.", 2000)

    def change_annotation_color(self, item, cname):
        """Recolor a node's highlight, in the tree data and in the PDF."""
        node = self.tree_item_to_node.get(id(item))
        if not node:
            return
        node["color"] = cname
        self.pdf.recolor_matching(node, cname)
        self.render_tree()
        self.show_page()
        self.export_markdown()

    def toggle_save_pdf_mode(self, checked):
        self.save_to_pdf_mode = checked
        self.save_settings()
        if checked and self.doc is not None and not getattr(self.doc, 'is_closed', False):
            # Backfill: write any highlights made while the toggle was OFF into the PDF
            self.sync_highlights_to_pdf()

    def sync_highlights_to_pdf(self):
        if self.pdf.sync_from_tree(self.annotations):
            self.show_page(scroll_to_current=False)

    @staticmethod
    def _rects_match(a, b, threshold=0.5):
        return rects_match(a, b, threshold)

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

        # Which page was captured (continuous mode aware)
        cap_page_idx, cap_off = self.locate_page(rect.top())
        zf = self.zoom_factor
        area_rect = fitz.Rect(rect.left()/zf, (rect.top()-cap_off)/zf,
                              rect.right()/zf, (rect.bottom()-cap_off)/zf)

        # Optionally draw a box annotation in the PDF marking the captured area
        if self.screenshot_box:
            self.pdf.add_box(cap_page_idx, area_rect,
                             self._pick_color_for_role("highlight"))

        img_dir = os.path.join(self.vault_path, "attachments")
        os.makedirs(img_dir, exist_ok=True)
        self.screenshot_counter += 1
        safe_title = "".join([c for c in self.source_title if c.isalnum() or c in ' -_']).rstrip()
        filename = f"{safe_title}_p{cap_page_idx + 1}_{self.screenshot_counter}.png"
        filepath = os.path.join(img_dir, filename)
        cropped.save(filepath, "PNG")

        # Add as annotation node (stores the area rect so it draws as a box outline)
        node = N.image_node(filename, cap_page_idx + 1, area_rect,
                            self._pick_color_for_role("highlight"))
        node["show_box"] = self.screenshot_box
        parent = self.current_h4 or self.current_h3 or self.current_h2 or self.current_h1
        if parent:
            parent["children"].append(node)
        else:
            self.annotations.append(node)

        self.render_tree()
        self.viewer.clear_selection()
        self.show_page(scroll_to_current=False)
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
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Document", "",
            "Documents (*.pdf *.pptx *.ppt *.ppsx *.pps);;PDF Files (*.pdf);;PowerPoint (*.pptx *.ppt *.ppsx *.pps)")
        if path:
            self.open_pdf_path(path)

    def open_pdf_path(self, path):
        if not os.path.exists(path):
            self.statusBar().showMessage(f"File not found: {path}", 3000)
            return

        display_title = os.path.splitext(os.path.basename(path))[0]
        if ppt_convert.is_ppt(path):
            self.statusBar().showMessage("Converting slides to PDF…", 0)
            QApplication.processEvents()
            converted = ppt_convert.convert_ppt_to_pdf(path)
            self.statusBar().clearMessage()
            if converted is None:
                QMessageBox.warning(
                    self, "Slide Conversion Failed",
                    "Couldn't convert the PowerPoint file to PDF.\n\n"
                    "This feature needs either Microsoft PowerPoint or LibreOffice "
                    "installed. Notes and highlights are made on the converted PDF "
                    "copy (<name>.slides.pdf); the original deck is never modified.")
                return
            path = converted

        abs_path = os.path.abspath(path)
        # Already open in a tab? Just switch to it.
        if abs_path in self.sessions or abs_path == self.pdf_path:
            idx = self._tab_index_for(abs_path)
            if idx >= 0:
                self.doc_tabs.setCurrentIndex(idx)
            self.show_pdf_center()
            return

        # Save bookmark + session for the current PDF before switching
        self.save_bookmark()
        self._save_current_session()

        new_doc = self.pdf.open(path)
        if new_doc is None:
            self.statusBar().showMessage(f"Failed to open or repair corrupted PDF: {path}", 5000)
            return
        self.pdf_path = abs_path
        self.source_title = display_title
        self.add_to_recent(path)
        self._register_tab(abs_path)

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
        self.show_pdf_center()

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

    def show_page(self, scroll_to_current=True):
        if self.doc is None or getattr(self.doc, 'is_closed', False):
            return

        self.page_input.setText(str(self.current_page_idx + 1))
        self.page_label.setText(f" / {len(self.doc)} ")
        self.viewer.clear_selection()
        self.clear_accumulated_selection()

        zf = self.zoom_factor
        mat = fitz.Matrix(zf, zf)

        # Which pages to render: 3-page window in continuous mode, single otherwise
        if self.continuous_mode:
            window = [p for p in range(self.current_page_idx - 1, self.current_page_idx + 2)
                      if 0 <= p < len(self.doc)]
        else:
            window = [self.current_page_idx]

        # One-time migration: blank any legacy embedded sketch images and
        # clear their img_xref so they become overlay-only (like text stickies)
        visible_set = set(window)
        for n in N.walk(self.annotations):
            if n.get("role") == "sketch_sticky" and n.get("img_xref") \
                    and (n.get("page", 1) - 1) in visible_set:
                self.pdf.blank_image(n.get("page", 1) - 1, n["img_xref"])
                n.pop("img_xref", None)

        # Render pixmaps (annots=False to avoid PyMuPDF crashes on malformed annots)
        pixes = []
        for p_idx in window:
            pixes.append(self.doc[p_idx].get_pixmap(matrix=mat, annots=False))

        GAP = 14 if len(window) > 1 else 0
        total_w = max(p.width for p in pixes)
        total_h = sum(p.height for p in pixes) + GAP * (len(pixes) - 1)

        img = QImage(total_w, total_h, QImage.Format.Format_RGB888)
        img.fill(QColor(18, 18, 18))

        self.page_offsets = []
        painter = QPainter(img)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            y_cursor = 0
            for p_idx, pix in zip(window, pixes):
                fmt = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
                page_img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
                painter.drawImage(0, y_cursor, page_img)
                self.page_offsets.append((p_idx, y_cursor, pix.height))
                y_cursor += pix.height + GAP

            painter.setPen(Qt.PenStyle.NoPen)

            for p_idx, off, _h in self.page_offsets:
                page = self.doc[p_idx]

                # 1) PDF-native markup annots (highlight/underline/squiggly/strikeout)
                try:
                    annot_list = list(page.annots())
                except Exception:
                    annot_list = []
                type_style = {8: "Highlight", 9: "Underline", 10: "Squiggly", 11: "Strikeout"}
                for annot in annot_list:
                    try:
                        atype = annot.type[0]
                        if atype in type_style:
                            color = annot.colors.get("stroke") if annot.colors else None
                            if color and len(color) == 3:
                                qc = QColor(int(color[0]*255), int(color[1]*255), int(color[2]*255), 100)
                            else:
                                qc = QColor(255, 255, 0, 100)
                            r = annot.rect
                            self._draw_markup(painter, r.x0*zf, off + r.y0*zf, r.x1*zf, off + r.y1*zf,
                                              type_style[atype], qc)
                    except Exception as e:
                        print(f"Skipping malformed annotation: {e}")
                        continue

            # 2) App-tree annotations (guaranteed rendering even with Save-to-PDF off)
            offset_map = {p: off for p, off, _h in self.page_offsets}

            def draw_app_nodes(nodes):
                for n in nodes:
                    n_off = offset_map.get(n.get("page", 0) - 1)
                    if n_off is not None:
                        if n.get("role") == "sketch_sticky":
                            rc = (n.get("fitz_rects") or [[0,0,0,0]])[0]
                            if len(rc) == 4:
                                x, y = rc[0]*zf, n_off + rc[1]*zf
                                w_px = int((rc[2]-rc[0])*zf)
                                h_px = int((rc[3]-rc[1])*zf)
                                if n.get("collapsed", True):
                                    # Collapsed: just draw the small icon (the PDF
                                    # image is blanked when collapsing so nothing
                                    # bleeds through — no white cover rect needed)
                                    painter.setBrush(QColor(255, 214, 120, 240))
                                    painter.setPen(QPen(QColor(150, 110, 0), 1))
                                    painter.drawRoundedRect(int(x), int(y), 20, 20, 4, 4)
                                    painter.setPen(QPen(QColor(90, 60, 0), 2))
                                    painter.drawLine(int(x+5), int(y+14), int(x+13), int(y+6))
                                    painter.drawEllipse(int(x+11), int(y+3), 5, 5)
                                    painter.setPen(Qt.PenStyle.NoPen)
                                else:
                                    x, y = int(x), int(y)
                                    locked = n.get("locked", False)
                                    # Draw border
                                    painter.setBrush(Qt.BrushStyle.NoBrush)
                                    painter.setPen(QPen(QColor(220, 60, 60) if locked else QColor(150, 110, 0),
                                                        2 if locked else 1))
                                    painter.drawRoundedRect(x-3, y-3, w_px+6, h_px+6, 5, 5)
                                    painter.setPen(Qt.PenStyle.NoPen)
                                    # Always draw from cache (the PDF Do command
                                    # is removed when collapsed and may not exist)
                                    cached = self._sketch_pixmap(n.get("img_path"))
                                    if cached and not cached.isNull():
                                        scaled = cached.scaled(max(1,w_px), max(1,h_px),
                                                               Qt.AspectRatioMode.KeepAspectRatio,
                                                               Qt.TransformationMode.SmoothTransformation)
                                        painter.drawPixmap(x, y, scaled)
                        elif n.get("sticky"):
                            for rc in n.get("fitz_rects", []):
                                if len(rc) != 4:
                                    continue
                                x, y = rc[0]*zf, n_off + rc[1]*zf
                                if n.get("collapsed", True):
                                    # Collapsed: small pin
                                    painter.setBrush(QColor(255, 200, 60, 230))
                                    painter.setPen(QPen(QColor(120, 90, 0), 1))
                                    painter.drawRoundedRect(int(x), int(y), 16, 16, 3, 3)
                                    painter.setPen(QPen(QColor(120, 90, 0), 2))
                                    painter.drawLine(int(x+4), int(y+6), int(x+12), int(y+6))
                                    painter.drawLine(int(x+4), int(y+10), int(x+12), int(y+10))
                                    painter.setPen(Qt.PenStyle.NoPen)
                                else:
                                    # Expanded: note box with wrapped text
                                    bw, bh = self.STICKY_NOTE_W, self.STICKY_NOTE_H
                                    painter.setBrush(QColor(255, 249, 196, 245))
                                    painter.setPen(QPen(QColor(150, 110, 0), 1))
                                    painter.drawRoundedRect(int(x), int(y), bw, bh, 5, 5)
                                    painter.setPen(QPen(QColor(60, 45, 0), 1))
                                    painter.drawText(QRect(int(x)+8, int(y)+6, bw-16, bh-12),
                                                     Qt.TextFlag.TextWordWrap,
                                                     n.get("custom_note", "")[:400])
                                    painter.setPen(Qt.PenStyle.NoPen)
                        elif n.get("role") == "ink" and n.get("ink_points"):
                            pts = n["ink_points"]
                            pen = QPen(pen_qcolor(n.get("pen_color", "Red")),
                                       n.get("pen_width", 3))
                            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                            painter.setPen(pen)
                            painter.setBrush(Qt.BrushStyle.NoBrush)
                            for i in range(1, len(pts)):
                                x0, y0 = pts[i-1]; x1, y1 = pts[i]
                                painter.drawLine(int(x0*zf), int(n_off + y0*zf),
                                                 int(x1*zf), int(n_off + y1*zf))
                            painter.setPen(Qt.PenStyle.NoPen)
                        elif n.get("role") == "image" and n.get("fitz_rects") and n.get("show_box", True):
                            # Area-capture box outline
                            for rc in n.get("fitz_rects", []):
                                if len(rc) == 4:
                                    painter.setBrush(Qt.BrushStyle.NoBrush)
                                    painter.setPen(QPen(hl_qcolor(n.get("color", "Blue"), 220), 2))
                                    painter.drawRect(int(rc[0]*zf), int(n_off + rc[1]*zf),
                                                     int((rc[2]-rc[0])*zf), int((rc[3]-rc[1])*zf))
                                    painter.setPen(Qt.PenStyle.NoPen)
                        else:
                            qc = hl_qcolor(n.get("color", "Yellow"), 100)
                            style = n.get("style", "Highlight")
                            for rc in n.get("fitz_rects", []):
                                if len(rc) == 4:
                                    self._draw_markup(painter, rc[0]*zf, n_off + rc[1]*zf,
                                                      rc[2]*zf, n_off + rc[3]*zf, style, qc)
                    draw_app_nodes(n.get("children", []))

            draw_app_nodes(self.annotations)
        finally:
            # CRITICAL: always end the painter, otherwise the QImage stays locked
            painter.end()

        if self.night_mode:
            img.invertPixels()

        self.viewer.setPixmap(QPixmap.fromImage(img))
        self.viewer.resize(total_w, total_h)

        # Jump viewport to the current page's top in continuous mode
        if self.continuous_mode and scroll_to_current:
            off = self.offset_of(self.current_page_idx)
            if off is not None:
                self._suppress_scroll = True
                self.scroll_area.verticalScrollBar().setValue(off)
                self._suppress_scroll = False

    @staticmethod
    def _draw_markup(painter, x0, y0, x1, y1, style, qcolor):
        """Draw one markup rect in the given style."""
        w, h = int(x1 - x0), int(y1 - y0)
        solid = QColor(qcolor.red(), qcolor.green(), qcolor.blue(), 220)
        if style == "Underline":
            painter.fillRect(int(x0), int(y1) - 3, w, 3, solid)
        elif style == "Strikeout":
            painter.fillRect(int(x0), int((y0 + y1) / 2) - 1, w, 3, solid)
        elif style == "Squiggly":
            pen = QPen(solid, 2, Qt.PenStyle.DotLine)
            painter.setPen(pen)
            painter.drawLine(int(x0), int(y1) - 2, int(x1), int(y1) - 2)
            painter.setPen(Qt.PenStyle.NoPen)
        else:  # Highlight
            painter.setBrush(qcolor)
            painter.drawRect(int(x0), int(y0), w, h)

    # ── Continuous-scroll helpers ────────────────────────────────────────────
    def offset_of(self, page_idx):
        for p, off, _h in self.page_offsets:
            if p == page_idx:
                return off
        return None

    def locate_page(self, y):
        """Return (page_idx, y_offset) of the rendered page under viewer-y."""
        for p, off, h in self.page_offsets:
            if off <= y <= off + h:
                return p, off
        if self.page_offsets:
            p, off, _h = self.page_offsets[-1] if y > self.page_offsets[-1][1] else self.page_offsets[0]
            return p, off
        return self.current_page_idx, 0

    def toggle_continuous_mode(self, checked):
        self.continuous_mode = checked
        self.save_settings()
        if self.doc is not None and not getattr(self.doc, 'is_closed', False):
            self.show_page()

    def on_viewer_scrolled(self, value):
        """Track which page is under the viewport center; slide the render window."""
        if self._suppress_scroll or not self.continuous_mode or not self.page_offsets:
            return
        if self.doc is None or getattr(self.doc, 'is_closed', False):
            return
        center_y = value + self.scroll_area.viewport().height() / 2
        page, _off = self.locate_page(center_y)
        if page == self.current_page_idx:
            return
        old_off = self.offset_of(page)
        self.current_page_idx = page
        self.page_input.setText(str(page + 1))
        self.save_bookmark()
        # If we've reached the edge of the window and more pages exist, re-center
        first, last = self.page_offsets[0][0], self.page_offsets[-1][0]
        if (page == first and page > 0) or (page == last and page < len(self.doc) - 1):
            self._suppress_scroll = True
            self.show_page(scroll_to_current=False)
            new_off = self.offset_of(page)
            if old_off is not None and new_off is not None:
                self.scroll_area.verticalScrollBar().setValue(value + (new_off - old_off))
            self._suppress_scroll = False

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
            y0 = (r.top() - self.sel_offset) / self.zoom_factor
            x1 = r.right() / self.zoom_factor
            y1 = (r.bottom() - self.sel_offset) / self.zoom_factor
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

    def begin_selection(self, pos):
        """Anchor a selection: resolve which rendered page the press landed on."""
        page, off = self.locate_page(pos.y())
        self.sel_page_idx = page
        self.sel_offset = off
        # Make the pressed page current so annotations land on the right page
        if page != self.current_page_idx:
            self.current_page_idx = page
            self.page_input.setText(str(page + 1))

    def select_word_at(self, pos):
        """Double-click: select the word under the cursor."""
        if self.doc is None or getattr(self.doc, 'is_closed', False):
            return
        page_idx, off = self.locate_page(pos.y())
        self.sel_page_idx, self.sel_offset = page_idx, off
        self.current_page_idx = page_idx
        zf = self.zoom_factor
        px, py = pos.x() / zf, (pos.y() - off) / zf
        for w in self.doc[page_idx].get_text("words"):
            if w[0] <= px <= w[2] and w[1] <= py <= w[3]:
                qr = QRect(int(w[0]*zf), int(off + w[1]*zf), int((w[2]-w[0])*zf), int((w[3]-w[1])*zf))
                self.current_selection_text = w[4]
                self.current_selection_fitz_rects = [fitz.Rect(w[0], w[1], w[2], w[3])]
                self.accumulated_qrects = [qr]
                self.viewer.selected_rects = [qr]
                self.viewer.update()
                self.statusBar().showMessage(f"Selected word: {w[4]}", 2000)
                return

    def select_block_at(self, pos):
        """Triple-click: select the whole text block (paragraph) under the cursor."""
        if self.doc is None or getattr(self.doc, 'is_closed', False):
            return
        page_idx, off = self.locate_page(pos.y())
        self.sel_page_idx, self.sel_offset = page_idx, off
        self.current_page_idx = page_idx
        zf = self.zoom_factor
        px, py = pos.x() / zf, (pos.y() - off) / zf
        page = self.doc[page_idx]
        for b in page.get_text("blocks"):
            if b[6] != 0:  # text blocks only
                continue
            if b[0] <= px <= b[2] and b[1] <= py <= b[3]:
                block_rect = fitz.Rect(b[0], b[1], b[2], b[3])
                qrects, frects, words_txt = [], [], []
                for w in page.get_text("words"):
                    wr = fitz.Rect(w[0], w[1], w[2], w[3])
                    if block_rect.intersects(wr):
                        words_txt.append(w[4])
                        frects.append(wr)
                        qrects.append(QRect(int(w[0]*zf), int(off + w[1]*zf),
                                            int((w[2]-w[0])*zf), int((w[3]-w[1])*zf)))
                if words_txt:
                    self.current_selection_text = " ".join(words_txt)
                    self.current_selection_fitz_rects = frects
                    self.accumulated_qrects = qrects
                    self.viewer.selected_rects = qrects
                    self.viewer.update()
                    self.statusBar().showMessage(f"Selected paragraph ({len(words_txt)} words)", 2000)
                return

    def show_viewer_context_menu(self, pos):
        """Right-click on the PDF page."""
        if self.doc is None or getattr(self.doc, 'is_closed', False):
            return
        menu = QMenu(self)
        menu.addAction("📌 Add Sticky Note Here", lambda checked=False, p=pos: self.add_sticky_note(p))
        menu.addAction("🖌 Add Sketch Sticky Here", lambda checked=False, p=pos: self.add_sketch_sticky(p))
        if self.current_selection_text:
            menu.addSeparator()
            menu.addAction("✨ Highlight Selection", lambda checked=False: self.add_annotation("highlight"))
            menu.addAction("📝 Note from Selection", lambda checked=False: self.add_annotation("custom_note"))
        menu.exec(self.viewer.mapToGlobal(pos))

    def add_sticky_note(self, pos):
        """Drop a sticky note pinned to a location on the page."""
        page_idx, off = self.locate_page(pos.y())
        text, ok = QInputDialog.getMultiLineText(self, "📌 Sticky Note", "Note:", "")
        if not ok or not text.strip():
            return
        text = text.strip()
        zf = self.zoom_factor
        fx, fy = pos.x() / zf, (pos.y() - off) / zf

        cname = self.role_colors.get("sticky", "Orange") if self.auto_color else self.highlight_color_name

        self.pdf.add_sticky(page_idx, fx, fy, text)
        node = N.sticky_node(text, page_idx + 1, fx, fy, cname)
        parent = self.current_h4 or self.current_h3 or self.current_h2 or self.current_h1
        (parent["children"] if parent else self.annotations).append(node)
        self.render_tree()
        self.show_page(scroll_to_current=False)
        self.export_markdown()
        self.statusBar().showMessage("📌 Sticky note added.", 2500)

    def _sketch_pixmap(self, path):
        """Cache loaded sketch PNGs so repeated renders don't re-read disk."""
        if not path:
            return None
        if not hasattr(self, "_sketch_cache"):
            self._sketch_cache = {}
        pm = self._sketch_cache.get(path)
        if pm is None:
            try:
                pm = QPixmap(path)
            except Exception:
                pm = QPixmap()
            self._sketch_cache[path] = pm
        return pm

    def add_sketch_sticky(self, pos):
        """Open a drawing canvas; save the sketch as a collapsible pinned image."""
        if not self.vault_path:
            self.statusBar().showMessage("Set Obsidian Vault first to save sketches.", 3000)
            return
        page_idx, off = self.locate_page(pos.y())
        zf = self.zoom_factor
        fx, fy = pos.x() / zf, (pos.y() - off) / zf

        dlg = SketchCanvasDialog(self, pen_color=pen_qcolor(self.pen_color_name),
                                 pen_width=self.pen_width)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.result_image is None:
            return
        img = dlg.result_image

        img_dir = os.path.join(self.vault_path, "attachments")
        os.makedirs(img_dir, exist_ok=True)
        self.screenshot_counter += 1
        safe_title = "".join([c for c in self.source_title if c.isalnum() or c in ' -_']).rstrip()
        filename = f"{safe_title}_sketch_p{page_idx + 1}_{self.screenshot_counter}.png"
        filepath = os.path.join(img_dir, filename)
        img.save(filepath, "PNG")

        # Place the sketch on the page at roughly its drawn size (capped)
        pw = min(img.width(), 260) / zf
        ph = min(img.height(), 260) / zf
        area_rect = fitz.Rect(fx, fy, fx + pw, fy + ph)

        # Sketch stickies are overlay-only (like text stickies) — no PDF embedding.
        # The image file on disk is drawn by the overlay when expanded.
        node = N.sketch_node(filename, filepath, page_idx + 1, area_rect,
                             self.sketch_default_collapsed)
        parent = self.current_h4 or self.current_h3 or self.current_h2 or self.current_h1
        (parent["children"] if parent else self.annotations).append(node)
        self.render_tree()
        self.show_page(scroll_to_current=False)
        self.export_markdown()
        self.statusBar().showMessage(f"🖌 Sketch sticky saved: {filename}", 3000)

    STICKY_NOTE_W = 210   # expanded text-sticky box size in screen px
    STICKY_NOTE_H = 100

    def _find_pin_at(self, page_idx, sx, sy):
        """Return the topmost sketch/text-sticky node whose drawn icon/box contains
        (sx, sy) — screen pixels relative to the page's top-left, matching exactly
        what show_page paints."""
        zf = self.zoom_factor
        hit = None
        for n in N.walk(self.annotations):
            if n.get("page") != page_idx + 1:
                continue
            rects = n.get("fitz_rects", [])
            if not rects or len(rects[0]) != 4:
                continue
            rc = rects[0]
            ax, ay = rc[0] * zf, rc[1] * zf  # anchor in screen px
            if n.get("role") == "sketch_sticky":
                if n.get("collapsed", True):
                    if ax <= sx <= ax + 20 and ay <= sy <= ay + 20:
                        hit = n
                else:
                    if rc[0] * zf <= sx <= rc[2] * zf and rc[1] * zf <= sy <= rc[3] * zf:
                        hit = n
            elif n.get("sticky"):
                if n.get("collapsed", True):
                    if ax <= sx <= ax + 16 and ay <= sy <= ay + 16:
                        hit = n
                else:
                    if ax <= sx <= ax + self.STICKY_NOTE_W and ay <= sy <= ay + self.STICKY_NOTE_H:
                        hit = n
        return hit

    def handle_sketch_click(self, viewer_pos):
        """Left-click on a pin (sketch or text sticky) toggles it open/collapsed.
        Returns True if the click was handled."""
        if self.doc is None or getattr(self.doc, 'is_closed', False):
            return False
        page_idx, off = self.locate_page(viewer_pos.y())
        sx, sy = viewer_pos.x(), viewer_pos.y() - off
        node = self._find_pin_at(page_idx, sx, sy)
        if not node:
            return False
        if self.eraser_action.isChecked():
            self.delete_node(node)
            self.statusBar().showMessage("🧽 Erased.", 1500)
            return True
        node["collapsed"] = not node.get("collapsed", True)
        self.render_tree()
        self.show_page(scroll_to_current=False)
        return True

    def erase_at(self, viewer_pos):
        """Eraser tool: delete the ink stroke or pin under the cursor."""
        if self.doc is None or getattr(self.doc, 'is_closed', False):
            return False
        page_idx, off = self.locate_page(viewer_pos.y())
        zf = self.zoom_factor
        sx, sy = viewer_pos.x(), viewer_pos.y() - off

        # 1. Pins (sketch / text sticky) — exact icon/box hit
        node = self._find_pin_at(page_idx, sx, sy)
        # 2. Ink strokes — within a small radius of any stroke point
        if node is None:
            RADIUS = 8  # screen px
            for n in N.walk(self.annotations):
                if n.get("role") == "ink" and n.get("page") == page_idx + 1:
                    for px, py in n.get("ink_points", []):
                        if abs(px * zf - sx) <= RADIUS and abs(py * zf - sy) <= RADIUS:
                            node = n
                            break
                if node:
                    break
        # 3. Area-capture boxes
        if node is None:
            for n in N.walk(self.annotations):
                if n.get("role") == "image" and n.get("page") == page_idx + 1:
                    for rc in n.get("fitz_rects", []):
                        if len(rc) == 4 and rc[0]*zf <= sx <= rc[2]*zf and rc[1]*zf <= sy <= rc[3]*zf:
                            node = n
                            break
                if node:
                    break
        if node is None:
            return False
        self.delete_node(node)
        self.statusBar().showMessage("🧽 Erased.", 1500)
        return True

    def toggle_sketch_lock(self, node):
        node["locked"] = not node.get("locked", False)
        self.export_markdown()
        state = "locked" if node["locked"] else "unlocked"
        self.statusBar().showMessage(f"Sketch sticky {state}.", 2000)

    def _tree_toggle_sketch(self, node):
        node["collapsed"] = not node.get("collapsed", True)
        self.render_tree()
        self.show_page(scroll_to_current=False)
        self.export_markdown()

    def _tree_toggle_lock(self, node):
        self.toggle_sketch_lock(node)
        self.render_tree()
        self.show_page(scroll_to_current=False)

    def redraw_sketch(self, node):
        """Reopen the canvas pre-loaded with the existing drawing to edit it."""
        if not self.vault_path:
            return
        existing = QImage(node.get("img_path", "")) if node.get("img_path") else None
        dlg = SketchCanvasDialog(self, existing_image=existing,
                                 pen_color=pen_qcolor(self.pen_color_name),
                                 pen_width=self.pen_width)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.result_image is None:
            return
        path = node.get("img_path")
        try:
            dlg.result_image.save(path, "PNG")
            if hasattr(self, "_sketch_cache"):
                self._sketch_cache.pop(path, None)
        except Exception as e:
            print(f"Re-draw save failed: {e}")
            return
        # Replace the embedded image in the PDF using the stored xref
        page_idx = node.get("page", 1) - 1
        img_xref = node.get("img_xref")
        if img_xref and self.pdf.valid and 0 <= page_idx < len(self.doc):
            self.pdf.update_image(page_idx, img_xref, path)
        self.render_tree()
        self.show_page(scroll_to_current=False)
        self.export_markdown()
        self.statusBar().showMessage("Sketch updated.", 2000)

    def _get_inline_selection(self, p1, p2):
        if self.doc is None or getattr(self.doc, 'is_closed', False):
            return [], ""

        page = self.doc[self.sel_page_idx]
        zf = self.zoom_factor
        off = self.sel_offset

        sx, sy = p1.x() / zf, (p1.y() - off) / zf
        ex, ey = p2.x() / zf, (p2.y() - off) / zf

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
                        qrects.append(QRect(int(w[0]*zf), int(off + w[1]*zf), int((w[2]-w[0])*zf), int((w[3]-w[1])*zf)))
                elif is_first_line:
                    if wcx >= sx:
                        selected_words.append(w[4])
                        qrects.append(QRect(int(w[0]*zf), int(off + w[1]*zf), int((w[2]-w[0])*zf), int((w[3]-w[1])*zf)))
                elif is_last_line:
                    if wcx <= ex:
                        selected_words.append(w[4])
                        qrects.append(QRect(int(w[0]*zf), int(off + w[1]*zf), int((w[2]-w[0])*zf), int((w[3]-w[1])*zf)))
                else:
                    selected_words.append(w[4])
                    qrects.append(QRect(int(w[0]*zf), int(off + w[1]*zf), int((w[2]-w[0])*zf), int((w[3]-w[1])*zf)))

        text = " ".join(selected_words)
        return qrects, text

    # ── Annotations ──────────────────────────────────────────────────────────
    def add_annotation(self, role):
        if not self.current_selection_text:
            self.statusBar().showMessage(f"Cannot add {role.upper()} — select text first!", 3000)
            return

        text = self.current_selection_text
        custom_note = ""
        # Capture rects NOW — show_page() below clears the selection state
        sel_rects = list(self.current_selection_fitz_rects)

        if role == "custom_note":
            note_text, ok = QInputDialog.getMultiLineText(self, "Add Custom Note", "Type your note here:", "")
            if not ok or not note_text.strip():
                return
            custom_note = note_text.strip()
            role = "note"

        cname = self._pick_color_for_role(role)
        target_page_idx = self.sel_page_idx if self.continuous_mode else self.current_page_idx

        if self.pdf.add_markup(target_page_idx, sel_rects, self.markup_style, cname):
            self.show_page(scroll_to_current=False)

        node = N.markup_node(text, role, target_page_idx + 1,
                             [[r.x0, r.y0, r.x1, r.y1] for r in sel_rects],
                             cname, self.markup_style, custom_note)

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
        if self.center_stack.currentWidget() is self.notes_tabs:
            block = item.data(0, Qt.ItemDataRole.UserRole)
            w = self.notes_tabs.currentWidget()
            if block is not None and w is not None:
                w.goto_block(block)
            return
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
                
                page_off = self.offset_of(self.current_page_idx) or 0
                self.viewer.search_rects = []
                for r in rects:
                    self.viewer.search_rects.append(QRect(
                        int(r.x0 * self.zoom_factor),
                        int(page_off + r.y0 * self.zoom_factor),
                        int((r.x1 - r.x0) * self.zoom_factor),
                        int((r.y1 - r.y0) * self.zoom_factor)
                    ))
                self.viewer.update()

                first_match = rects[0] if forward else rects[-1]

                # Scroll to match
                scrollbar = self.scroll_area.verticalScrollBar()
                if scrollbar:
                    self._suppress_scroll = True
                    scrollbar.setValue(int(page_off + first_match.y0 * self.zoom_factor) - 50)
                    self._suppress_scroll = False
                
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
                elif role == "sketch_sticky":
                    state = "collapsed" if n.get("collapsed", True) else "open"
                    lk = " 🔒" if n.get("locked") else ""
                    display_text = f"🖌 [SKETCH] p.{n['page']} ({state}){lk}"
                elif role == "ink":
                    display_text = f"✏ [DRAWING] p.{n['page']} ({n.get('pen_color','Red')})"
                elif role == "note":
                    cn = n.get('custom_note', '')
                    tag = "📌 STICKY" if n.get("sticky") else "NOTE"
                    display_text = f"[{tag}] {cn[:30]}... ({n['text'][:20]})" if cn else f"[{tag}] {n['text']}"
                elif role == "highlight":
                    style = n.get("style", "Highlight")
                    tag = "HIGHLIGHT" if style == "Highlight" else style.upper()
                    display_text = f"[{tag}] {n['text']}"
                else:
                    display_text = f"[{role.upper()}] {n['text']}"

                if len(display_text) > 50:
                    display_text = display_text[:50] + "..."

                # Count badge for headers with children
                if n["children"]:
                    display_text += f"  ({N.count_descendants(n)})"

                item.setText(0, display_text)

                colors = {"h1": "#7aa2f7", "h2": "#bb9af7", "h3": "#9ece6a", "h4": "#ff9e64", "image": "#e0af68"}
                if role in ("highlight", "note"):
                    item.setForeground(0, hl_qcolor(n.get("color", "Yellow"), 255).lighter(115))
                elif role == "ink":
                    cname = n.get("pen_color", "Red")
                    qc = pen_qcolor(cname)
                    if cname == "Black" or qc.lightness() < 60:
                        qc = QColor(170, 170, 170)
                    item.setForeground(0, qc)
                else:
                    item.setForeground(0, QColor(colors.get(role, "#c0caf5")))

                add_nodes(item, n["children"])
                item.setExpanded(True)

        add_nodes(self.tree_widget, self.annotations)
        # Re-apply active filter after rebuild
        if hasattr(self, "tree_filter_input") and self.tree_filter_input.text().strip():
            self.filter_tree(self.tree_filter_input.text())
        self.refresh_review()

    # ── Tree Filter ──────────────────────────────────────────────────────────
    def filter_tree(self, query):
        query = query.strip().lower()

        def visit(item):
            """Returns True if item or any descendant matches."""
            self_match = not query or query in item.text(0).lower()
            child_match = False
            for i in range(item.childCount()):
                if visit(item.child(i)):
                    child_match = True
            visible = self_match or child_match
            item.setHidden(not visible)
            return visible

        for i in range(self.tree_widget.topLevelItemCount()):
            visit(self.tree_widget.topLevelItem(i))

    # ── Tree Reorder (drag & drop) ───────────────────────────────────────────
    def on_tree_reordered(self, *args):
        """Rebuild self.annotations from the widget tree after a drag-drop move."""
        def collect(item):
            node = self.tree_item_to_node.get(id(item))
            if node is None:
                return None
            node["children"] = []
            for i in range(item.childCount()):
                child_node = collect(item.child(i))
                if child_node is not None:
                    node["children"].append(child_node)
            return node

        new_annotations = []
        for i in range(self.tree_widget.topLevelItemCount()):
            n = collect(self.tree_widget.topLevelItem(i))
            if n is not None:
                new_annotations.append(n)
        self.annotations = new_annotations
        self.export_markdown()
        self.statusBar().showMessage("Annotations reordered.", 2000)

    def show_tree_context_menu(self, pos):
        item = self.tree_widget.itemAt(pos)
        if not item: return
        node = self.tree_item_to_node.get(id(item))
        menu = QMenu(self)

        edit_action = QAction("✏ Edit", self)
        edit_action.triggered.connect(lambda checked=False, it=item: self.edit_annotation(it))
        menu.addAction(edit_action)

        # Color submenu for highlight/note nodes
        if node and node.get("role") in ("highlight", "note"):
            color_menu = menu.addMenu("🎨 Color")
            for cname in HIGHLIGHT_COLORS:
                act = color_menu.addAction(self._color_icon(cname), cname)
                act.triggered.connect(lambda checked=False, c=cname, it=item: self.change_annotation_color(it, c))

        # Sketch sticky actions
        if node and node.get("role") == "sketch_sticky":
            collapse_lbl = "🔽 Expand" if node.get("collapsed", True) else "🔼 Collapse"
            a1 = menu.addAction(collapse_lbl)
            a1.triggered.connect(lambda checked=False, n=node: self._tree_toggle_sketch(n))
            lock_lbl = "🔓 Unlock Position" if node.get("locked") else "🔒 Lock Position"
            a2 = menu.addAction(lock_lbl)
            a2.triggered.connect(lambda checked=False, n=node: self._tree_toggle_lock(n))
            a3 = menu.addAction("✏ Re-draw")
            a3.triggered.connect(lambda checked=False, n=node: self.redraw_sketch(n))

        menu.addSeparator()
        delete_action = QAction("🗑 Delete", self)
        delete_action.triggered.connect(lambda checked=False, it=item: self.delete_annotation(it))
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
                self.scroll_to_node(node)

    def scroll_to_node(self, node):
        """Center the viewport on the node's first highlight rect."""
        rects = node.get("fitz_rects", [])
        if not rects or len(rects[0]) != 4:
            return
        x0, y0, x1, y1 = rects[0]
        page_off = self.offset_of(node.get("page", 1) - 1) or 0
        cx = int(((x0 + x1) / 2) * self.zoom_factor)
        cy = int(page_off + ((y0 + y1) / 2) * self.zoom_factor)
        vp = self.scroll_area.viewport()
        self._suppress_scroll = True
        self.scroll_area.ensureVisible(cx, cy, vp.width() // 2, vp.height() // 2)
        self._suppress_scroll = False

    def delete_annotation(self, item):
        node_to_delete = self.tree_item_to_node.get(id(item))
        if not node_to_delete: return
        self.delete_node(node_to_delete)

    def delete_node(self, node_to_delete):
        """Remove a node from the tree and clean its traces from the PDF."""
        if N.remove_node(self.annotations, node_to_delete):
            active = N.all_ids(self.annotations)
            if self.current_h1 and id(self.current_h1) not in active: self.current_h1 = None
            if self.current_h2 and id(self.current_h2) not in active: self.current_h2 = None
            if self.current_h3 and id(self.current_h3) not in active: self.current_h3 = None
            if self.current_h4 and id(self.current_h4) not in active: self.current_h4 = None

            if self.doc is not None and not getattr(self.doc, 'is_closed', False):
                # Always clean up matching PDF annots (no-op if none were ever saved),
                # and persist immediately so the deletion sticks even with toggle OFF
                self.remove_pdf_highlights(node_to_delete)
                self._do_save_pdf(force=True)
            self.render_tree()
            self.show_page()
            self.export_markdown()

    def remove_pdf_highlights(self, node):
        self.pdf.remove_matching(node)

    # ── Export / Import ──────────────────────────────────────────────────────
    def get_markdown(self):
        def render_md(nodes):
            md = ""
            for n in nodes:
                if n["role"] == "image":
                    md += f"\n{n['text']}\n"
                elif n["role"] == "sketch_sticky":
                    md += f"\n- 🖌 *Sketch on p.{n['page']}:*\n\n{n.get('text','')}\n"
                elif n["role"] == "ink":
                    md += f"\n- ✏ *Drawing on p.{n['page']} ({n.get('pen_color','Red')} pen)*\n"
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

    # ── Pen / Ink Drawing ────────────────────────────────────────────────────
    def _pen_icon(self, cname, size=16):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pen_qcolor(cname))
        p.drawEllipse(1, 1, size - 2, size - 2)
        p.end()
        return QIcon(pm)

    def toggle_draw_mode(self, checked):
        self.draw_mode = checked
        self.viewer.draw_mode = checked
        self.viewer.pen_color = pen_qcolor(self.pen_color_name)
        self.viewer.pen_width = self.pen_width
        if checked:
            # Pen and eraser are mutually exclusive
            if self.eraser_action.isChecked():
                self.eraser_action.setChecked(False)
            self.viewer.setCursor(Qt.CursorShape.CrossCursor)
            self.statusBar().showMessage(f"✏ Pen on — {self.pen_color_name}, width {self.pen_width}. Draw on the page.", 4000)
        else:
            self.viewer.setCursor(Qt.CursorShape.ArrowCursor)
            self.viewer.clear_selection()

    def toggle_eraser_mode(self, checked):
        if checked:
            if self.pen_action.isChecked():
                self.pen_action.setChecked(False)
                self.toggle_draw_mode(False)
            self.viewer.setCursor(Qt.CursorShape.PointingHandCursor)
            self.statusBar().showMessage("🧽 Eraser on — click a stroke, sticky, sketch, or capture box to delete it.", 4000)
        else:
            self.viewer.setCursor(Qt.CursorShape.ArrowCursor)

    def set_pen_color(self, cname):
        self.pen_color_name = cname
        self.viewer.pen_color = pen_qcolor(cname)
        self.save_settings()
        if not self.pen_action.isChecked():
            self.pen_action.setChecked(True)
            self.toggle_draw_mode(True)
        self.statusBar().showMessage(f"Pen color: {cname}", 2000)

    def set_pen_width(self, w):
        self.pen_width = w
        self.viewer.pen_width = w
        self.save_settings()
        self.statusBar().showMessage(f"Pen width: {w}", 2000)

    def commit_ink_stroke(self, points_px):
        """Turn a drawn stroke (viewer pixels) into a PDF ink annotation + tree node."""
        if self.doc is None or getattr(self.doc, 'is_closed', False) or len(points_px) < 2:
            return
        # Which rendered page did the stroke land on? Use its first point.
        first_y = points_px[0][1]
        page_idx, off = self.locate_page(first_y)
        zf = self.zoom_factor
        # Convert to PDF coordinates (relative to that page's top)
        pdf_pts = [(x / zf, (y - off) / zf) for x, y in points_px]

        xs = [p[0] for p in pdf_pts]; ys = [p[1] for p in pdf_pts]
        bbox = [min(xs), min(ys), max(xs), max(ys)]

        self.pdf.add_ink(page_idx, pdf_pts, self.pen_color_name, self.pen_width)

        node = N.ink_node(page_idx + 1, pdf_pts, bbox,
                          self.pen_color_name, self.pen_width)
        parent = self.current_h4 or self.current_h3 or self.current_h2 or self.current_h1
        (parent["children"] if parent else self.annotations).append(node)
        self.render_tree()
        self.show_page(scroll_to_current=False)
        self.export_markdown()

    def erase_last_ink(self):
        """Remove the most recently added ink stroke (tree + PDF)."""
        def find_last_ink(nodes, path=None):
            path = path or []
            found = None
            for i, n in enumerate(nodes):
                if n.get("role") == "ink":
                    found = (nodes, i, n)
                sub = find_last_ink(n.get("children", []), path + [n])
                if sub:
                    found = sub
            return found

        result = find_last_ink(self.annotations)
        if not result:
            self.statusBar().showMessage("No ink strokes to erase.", 2000)
            return
        nodes, idx, node = result
        self.remove_pdf_highlights(node)
        nodes.pop(idx)
        self._do_save_pdf(force=True)
        self.render_tree()
        self.show_page(scroll_to_current=False)
        self.export_markdown()
        self.statusBar().showMessage("Erased last stroke.", 2000)

    # ── Markup Style ─────────────────────────────────────────────────────────
    def set_markup_style(self, style):
        self.markup_style = style
        self.save_settings()

    def _pick_color_for_role(self, role):
        """Auto color-by-type if enabled in settings, else the toolbar color."""
        if self.auto_color:
            return self.role_colors.get(role, self.highlight_color_name)
        return self.highlight_color_name

    # ── Review Tab ───────────────────────────────────────────────────────────
    def refresh_review(self):
        if not hasattr(self, "review_list"):
            return
        self.review_list.clear()
        self.review_item_to_node = {}
        want_color = self.review_color_filter.currentText()

        for n in N.walk(self.annotations):
            if n["role"] in ("highlight", "note"):
                if want_color == "All colors" or n.get("color", "Yellow") == want_color:
                    label = n.get("custom_note") or n.get("text", "")
                    prefix = "📌 " if n.get("sticky") else ""
                    item = QTreeWidgetItem([f"{prefix}{label[:70]}", str(n.get("page", "?"))])
                    item.setForeground(0, hl_qcolor(n.get("color", "Yellow"), 255).lighter(115))
                    self.review_list.addTopLevelItem(item)
                    self.review_item_to_node[id(item)] = n

    def on_review_clicked(self, item, column):
        node = self.review_item_to_node.get(id(item))
        if node and "page" in node and self.doc is not None and not getattr(self.doc, 'is_closed', False):
            page_idx = max(0, node["page"] - 1)
            if 0 <= page_idx < len(self.doc):
                self.current_page_idx = page_idx
                self.show_page()
                self.save_bookmark()
                self.scroll_to_node(node)

    # ── Anki Export ──────────────────────────────────────────────────────────
    def export_anki(self):
        rows = []

        def walk(nodes, header_path):
            for n in nodes:
                role = n["role"]
                if role in ("h1", "h2", "h3", "h4"):
                    walk(n["children"], header_path + [n["text"]])
                else:
                    if role in ("highlight", "note"):
                        front = n.get("text", "").strip()
                        back = n.get("custom_note", "").strip()
                        if not back:
                            back = " > ".join(header_path) if header_path else f"{self.source_title} p.{n.get('page','?')}"
                        if front:
                            rows.append((front, back, f"p.{n.get('page','?')}"))
                    walk(n.get("children", []), header_path)

        walk(self.annotations, [])
        if not rows:
            self.statusBar().showMessage("No highlights/notes to export.", 3000)
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Anki Flashcards", f"{self.source_title}_flashcards.csv", "CSV Files (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                for front, back, page in rows:
                    writer.writerow([front, back, page])
            self.statusBar().showMessage(f"🃏 Exported {len(rows)} flashcards. In Anki: File → Import.", 5000)
        except Exception as e:
            self.statusBar().showMessage(f"Anki export failed: {e}", 5000)

    # ── Settings Dialog ──────────────────────────────────────────────────────
    def show_settings_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("⚙ Settings")
        layout = QGridLayout(dlg)
        row = 0

        auto_cb = QCheckBox("Color-code annotations by type automatically")
        auto_cb.setChecked(self.auto_color)
        auto_cb.setToolTip("When on, each annotation type gets its assigned color below,\ninstead of the toolbar color.")
        layout.addWidget(auto_cb, row, 0, 1, 2); row += 1

        role_labels = {"highlight": "Highlights", "note": "Notes", "sticky": "Sticky notes",
                       "h1": "H1 headers", "h2": "H2 headers", "h3": "H3 headers", "h4": "H4 headers"}
        combos = {}
        for role, label in role_labels.items():
            lab = QLabel(f"    {label}:")
            combo = QComboBox()
            for cname in HIGHLIGHT_COLORS:
                combo.addItem(self._color_icon(cname), cname)
            combo.setCurrentText(self.role_colors.get(role, "Yellow"))
            combo.setEnabled(auto_cb.isChecked())
            combos[role] = combo
            layout.addWidget(lab, row, 0)
            layout.addWidget(combo, row, 1); row += 1
        auto_cb.toggled.connect(lambda on: [c.setEnabled(on) for c in combos.values()])

        box_cb = QCheckBox("Area captures also draw a box annotation in the PDF")
        box_cb.setChecked(self.screenshot_box)
        layout.addWidget(box_cb, row, 0, 1, 2); row += 1

        cont_cb = QCheckBox("Continuous scroll mode")
        cont_cb.setChecked(self.continuous_mode)
        layout.addWidget(cont_cb, row, 0, 1, 2); row += 1

        sketch_cb = QCheckBox("New sketch stickies start collapsed (as an icon)")
        sketch_cb.setChecked(self.sketch_default_collapsed)
        layout.addWidget(sketch_cb, row, 0, 1, 2); row += 1

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        btn_row.addStretch(); btn_row.addWidget(ok_btn); btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row, row, 0, 1, 2)

        ok_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.auto_color = auto_cb.isChecked()
            for role, combo in combos.items():
                self.role_colors[role] = combo.currentText()
            self.screenshot_box = box_cb.isChecked()
            self.sketch_default_collapsed = sketch_cb.isChecked()
            if cont_cb.isChecked() != self.continuous_mode:
                self.continuous_action.setChecked(cont_cb.isChecked())
                self.toggle_continuous_mode(cont_cb.isChecked())
            self.save_settings()
            self.statusBar().showMessage("Settings saved.", 2000)

    # ── Document Tabs ────────────────────────────────────────────────────────
    def _save_current_session(self):
        if not self.pdf_path:
            return
        self.sessions[self.pdf_path] = {
            "doc": self.doc, "title": self.source_title,
            "page": self.current_page_idx, "zoom": self.zoom_factor,
            "annotations": self.annotations,
            "h": (self.current_h1, self.current_h2, self.current_h3, self.current_h4),
            "counter": self.screenshot_counter,
        }

    def _load_session(self, path):
        s = self.sessions.get(path)
        if not s:
            return
        # Flush any pending save of the outgoing doc
        self.pdf.flush()
        self.pdf.adopt(s["doc"], path)
        self.pdf_path = path
        self.source_title = s["title"]
        self.current_page_idx = s["page"]
        self.zoom_factor = s["zoom"]
        self.annotations = s["annotations"]
        self.current_h1, self.current_h2, self.current_h3, self.current_h4 = s["h"]
        self.screenshot_counter = s["counter"]
        self.setWindowTitle(f"{self.source_title} — PDF Annotator")
        self.update_context_label()
        self.render_tree()
        self.load_toc()
        self.show_page()

    def _tab_index_for(self, path):
        for i in range(self.doc_tabs.count()):
            if self.doc_tabs.tabData(i) == path:
                return i
        return -1

    def _register_tab(self, path):
        self.doc_tabs.blockSignals(True)
        idx = self._tab_index_for(path)
        if idx < 0:
            idx = self.doc_tabs.addTab(os.path.basename(path))
            self.doc_tabs.setTabData(idx, path)
            self.doc_tabs.setTabToolTip(idx, path)
        self.doc_tabs.setCurrentIndex(idx)
        self.doc_tabs.blockSignals(False)
        self.doc_tabs.show()

    def on_tab_changed(self, index):
        if index < 0:
            return
        path = self.doc_tabs.tabData(index)
        if not path or path == self.pdf_path:
            return
        self._save_current_session()
        self._load_session(path)
        self.save_settings()

    def on_tab_close(self, index):
        path = self.doc_tabs.tabData(index)
        if not path:
            return
        closing_current = (path == self.pdf_path)
        session = self.sessions.pop(path, None)
        doc = self.doc if closing_current else (session["doc"] if session else None)
        # Flush & close the document
        try:
            if doc is not None and not getattr(doc, 'is_closed', False):
                if closing_current:
                    self.pdf.flush()
                doc.close()
        except Exception:
            pass
        self.doc_tabs.blockSignals(True)
        self.doc_tabs.removeTab(index)
        self.doc_tabs.blockSignals(False)

        if closing_current:
            self.save_bookmark()
            if self.doc_tabs.count() > 0:
                new_idx = min(index, self.doc_tabs.count() - 1)
                self.doc_tabs.setCurrentIndex(new_idx)
                self._load_session(self.doc_tabs.tabData(new_idx))
            else:
                # No documents left
                self.doc = None
                self.pdf_path = ""
                self.annotations = []
                self.current_h1 = self.current_h2 = self.current_h3 = self.current_h4 = None
                self.viewer.clear()
                self.tree_widget.clear()
                self.outline_widget.clear()
                if hasattr(self, "review_list"):
                    self.review_list.clear()
                self.page_input.setText("0")
                self.page_label.setText(" / 0 ")
                self.doc_tabs.hide()

    def save_pdf_highlights(self):
        self.pdf.schedule_save()

    def _do_save_pdf(self, force=False):
        self.pdf.save_now(force=force)

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

    def _md_for_display(self, raw):
        """Convert app/Obsidian-flavored markdown into Qt-renderable markdown:
        drop YAML frontmatter, turn ![[embeds]] into standard images, and
        flatten `> [!type] title` callout headers into a bold quote line."""
        text = raw

        # Strip a leading YAML frontmatter block (--- ... ---)
        if text.lstrip().startswith("---"):
            lines = text.split("\n")
            start = next(i for i, l in enumerate(lines) if l.strip() == "---")
            end = None
            for i in range(start + 1, len(lines)):
                if lines[i].strip() == "---":
                    end = i
                    break
            if end is not None:
                text = "\n".join(lines[end + 1:]).lstrip("\n")

        # Obsidian embeds: ![[path|size]] -> ![](path)
        def _embed(m):
            inner = m.group(1).split("|")[0].strip()
            return f"![]({inner})"
        text = re.sub(r"!\[\[([^\]]+)\]\]", _embed, text)

        # Callout headers: `> [!quote] p.5` -> `> **p.5**`
        out = []
        for line in text.split("\n"):
            m = re.match(r"^(\s*>+\s*)\[!(\w+)\]\s*(.*)$", line)
            if m:
                prefix, ctype, title = m.group(1), m.group(2), m.group(3).strip()
                out.append(f"{prefix}**{title or ctype.capitalize()}**")
            else:
                out.append(line)
        return "\n".join(out)

    def open_markdown_view(self):
        start_dir = self.vault_path or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Markdown File", start_dir,
            "Markdown Files (*.md *.markdown);;All Files (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception as e:
            self.statusBar().showMessage(f"Error opening: {e}", 5000)
            return

        base_dir = os.path.dirname(os.path.abspath(path))
        dlg = QDialog(self)
        dlg.setWindowTitle(f"📖 {os.path.basename(path)}")
        dlg.resize(820, 900)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)

        browser = QTextBrowser(dlg)
        browser.setOpenExternalLinks(True)
        # Resolve relative image paths (e.g. attachments/x.png) against the file
        browser.setSearchPaths([base_dir, os.path.join(base_dir, "attachments")])
        browser.setMarkdown(self._md_for_display(raw))
        layout.addWidget(browser)

        bar = QHBoxLayout()
        bar.setContentsMargins(8, 6, 8, 8)
        bar.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        bar.addWidget(close_btn)
        layout.addLayout(bar)

        self.statusBar().showMessage(f"Viewing {os.path.basename(path)}", 3000)
        dlg.exec()

    def show_pdf_center(self):
        self.center_stack.setCurrentWidget(self.scroll_area)
        self.refresh_outline()

    def show_notes_center(self):
        self.center_stack.setCurrentWidget(self.notes_tabs)
        self.refresh_outline()

    def refresh_outline(self):
        """Outline tab shows the PDF's TOC, or the active note's headings."""
        if self.center_stack.currentWidget() is self.notes_tabs:
            w = self.notes_tabs.currentWidget()
            if w is not None:
                self.build_note_outline(w)
            else:
                self.outline_widget.clear()
        else:
            self.load_toc()

    def build_note_outline(self, widget):
        self.outline_widget.clear()
        items_by_level = {}
        found = False
        for i, line in enumerate(widget.editor.toPlainText().split("\n")):
            mm = re.match(r"^(#{1,6})\s+(.*)$", line)
            if not mm:
                continue
            found = True
            level = len(mm.group(1))
            item = QTreeWidgetItem([mm.group(2).strip() or "(untitled)"])
            item.setData(0, Qt.ItemDataRole.UserRole, i)  # editor line/block number
            parent = next((items_by_level[lv] for lv in range(level - 1, 0, -1)
                           if lv in items_by_level), None)
            (parent.addChild if parent else self.outline_widget.addTopLevelItem)(item)
            items_by_level[level] = item
            for lv in [lv for lv in items_by_level if lv > level]:
                del items_by_level[lv]
        if not found:
            self.outline_widget.addTopLevelItem(QTreeWidgetItem(["(no headings yet)"]))
        self.outline_widget.expandAll()

    def _open_md_editor(self, path=None, mode="Split"):
        """Open a note as a tab in the middle area (like PDFs). If the file
        is already open in a tab, switch to that tab instead of duplicating."""
        if path:
            ap = os.path.abspath(path)
            for i in range(self.notes_tabs.count()):
                w = self.notes_tabs.widget(i)
                if w.path and os.path.abspath(w.path) == ap:
                    self.notes_tabs.setCurrentIndex(i)
                    self.show_notes_center()
                    self.vault_toggle_action.setChecked(False)
                    return
        try:
            page = MarkdownEditorWidget(self, path, start_mode=mode)
        except Exception as e:
            QMessageBox.critical(self, "Editor unavailable",
                                 f"Could not open the Markdown editor:\n{e}")
            return
        name = os.path.splitext(os.path.basename(path))[0] if path else "Untitled"
        idx = self.notes_tabs.addTab(page, f"📝 {name}")
        self.notes_tabs.setCurrentIndex(idx)
        self.show_notes_center()
        # Collapse the sidebar so the note gets the full width; 🗂 re-opens it
        self.vault_toggle_action.setChecked(False)

    def _update_note_tab(self, widget, text):
        idx = self.notes_tabs.indexOf(widget)
        if idx >= 0:
            self.notes_tabs.setTabText(idx, f"📝 {text}")

    def on_note_tab_close(self, idx):
        w = self.notes_tabs.widget(idx)
        if w is not None and not w.maybe_close():
            return  # user cancelled the unsaved-changes prompt
        self.notes_tabs.removeTab(idx)
        if w is not None:
            w.deleteLater()
        if self.notes_tabs.count() == 0:
            self.show_pdf_center()

    def new_markdown_note(self):
        self._open_md_editor(None, mode="Split")

    def edit_markdown_note(self):
        start = self.vault_path or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Edit Markdown File", start,
            "Markdown Files (*.md *.markdown);;All Files (*)")
        if path:
            self._open_md_editor(path)

    # ── Notes sidebar (any folder — vault optional) ──────────────────────────
    def toggle_vault_panel(self, checked):
        self.vault_panel.setVisible(checked)
        if checked:
            self.refresh_vault_tree()

    def choose_notes_folder(self):
        start = self.notes_root or self.vault_path or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, "Browse Folder (notes / lectures / vault)", start)
        if path:
            self.notes_root = path
            self.save_settings()
            self.vault_toggle_action.setChecked(True)
            self.refresh_vault_tree()

    @staticmethod
    def _is_note(name):
        return name.lower().endswith((".md", ".markdown"))

    @staticmethod
    def _media_icon(name):
        ext = os.path.splitext(name)[1].lower()
        if ext in VIDEO_EXTS:
            return "🎬"
        if ext in AUDIO_EXTS:
            return "🎵"
        if ext in IMAGE_EXTS:
            return "🖼"
        return None

    @classmethod
    def _dir_has_content(cls, path):
        for _root, _dirs, files in os.walk(path):
            for f in files:
                if cls._is_note(f) or cls._media_icon(f):
                    return True
        return False

    def refresh_vault_tree(self):
        if not hasattr(self, "vault_tree"):
            return
        self.vault_tree.clear()
        root = self.notes_root or self.vault_path
        self.vault_panel_label.setText(
            f"🗂 {os.path.basename(root)}" if root else "🗂 Notes")
        if not root or not os.path.isdir(root):
            self.vault_tree.addTopLevelItem(QTreeWidgetItem(
                ["(click 📂 to browse any folder,"]))
            self.vault_tree.addTopLevelItem(QTreeWidgetItem(
                [" or set a vault in ☰ File)"]))
            return
        show_attachments = bool(self.notes_root)  # inside a vault keep them hidden

        def add_dir(parent, dirpath):
            try:
                entries = sorted(os.listdir(dirpath), key=str.lower)
            except OSError:
                return
            for e in entries:
                full = os.path.join(dirpath, e)
                if os.path.isdir(full):
                    if e.startswith(".") or not self._dir_has_content(full):
                        continue
                    if e == "attachments" and not show_attachments:
                        continue
                    node = QTreeWidgetItem([f"📁 {e}"])
                    (parent.addChild if parent else self.vault_tree.addTopLevelItem)(node)
                    add_dir(node, full)
            for e in entries:
                full = os.path.join(dirpath, e)
                if not os.path.isfile(full):
                    continue
                if self._is_note(e):
                    node = QTreeWidgetItem([f"📄 {os.path.splitext(e)[0]}"])
                elif self._media_icon(e):
                    node = QTreeWidgetItem([f"{self._media_icon(e)} {e}"])
                else:
                    continue
                node.setData(0, Qt.ItemDataRole.UserRole, full)
                (parent.addChild if parent else self.vault_tree.addTopLevelItem)(node)

        add_dir(None, root)
        self.vault_tree.expandToDepth(0)
        if self.vault_tree.topLevelItemCount() == 0:
            self.vault_tree.addTopLevelItem(
                QTreeWidgetItem(["(no notes or media here yet)"]))

    def on_vault_item_clicked(self, item, _col=0):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not path or not os.path.isfile(path):
            return
        if self._is_note(path):
            # Obsidian-style: single click opens read view; double-click the
            # preview (or Ctrl+E) to switch into editing.
            self._open_md_editor(path, mode="Preview")
        else:
            self._open_media_player(path)

    def show_vault_tree_menu(self, pos):
        item = self.vault_tree.itemAt(pos)
        if item is None:
            return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not path:
            return  # folder rows: no actions yet
        menu = QMenu(self)
        menu.addAction("🗑 Delete", lambda: self.delete_vault_file(path))
        menu.exec(self.vault_tree.viewport().mapToGlobal(pos))

    def delete_vault_file(self, path):
        name = os.path.basename(path)
        r = QMessageBox.question(
            self, "Delete file",
            f"Permanently delete “{name}”?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        ap = os.path.abspath(path)
        # Close its tab first (without an unsaved-changes prompt — it's going away)
        for i in range(self.notes_tabs.count()):
            w = self.notes_tabs.widget(i)
            if w.path and os.path.abspath(w.path) == ap:
                w._dirty = False
                self.notes_tabs.removeTab(i)
                w.deleteLater()
                break
        try:
            os.remove(path)
            self.statusBar().showMessage(f"Deleted {name}", 3000)
        except Exception as e:
            QMessageBox.warning(self, "Delete failed", str(e))
        if self.notes_tabs.count() == 0:
            self.show_pdf_center()
        self.refresh_vault_tree()

    def _open_media_player(self, path):
        """Play a video/audio file (or show an image) in a themed window —
        e.g. downloaded lectures, straight from the sidebar."""
        try:
            dlg = MediaPlayerDialog(self, path)
        except Exception as e:
            QMessageBox.critical(self, "Player unavailable",
                                 f"Could not open the media player:\n{e}")
            return
        if not hasattr(self, "_media_players"):
            self._media_players = []
        self._media_players = [d for d in self._media_players if d.isVisible()]
        self._media_players.append(dlg)
        dlg.show()
        dlg.raise_()

    def closeEvent(self, event):
        # Give open notes a chance to save (or the user a chance to cancel)
        for i in range(self.notes_tabs.count()):
            if not self.notes_tabs.widget(i).maybe_close():
                event.ignore()
                return
        self.pdf.flush()
        self.save_bookmark()
        self.save_settings()
        # Close documents held by background tabs
        for s in self.sessions.values():
            try:
                d = s.get("doc")
                if d is not None and not getattr(d, 'is_closed', False) and d is not self.doc:
                    d.close()
            except Exception:
                pass
        event.accept()


# ── Obsidian-style Markdown → HTML (for the WebEngine note preview) ───────────
VIDEO_EXTS = {".mp4", ".webm", ".ogv", ".mov", ".mkv", ".m4v"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".oga", ".ogg"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".avif"}


def _strip_frontmatter(text):
    if text.lstrip().startswith("---"):
        lines = text.split("\n")
        start = next(i for i, l in enumerate(lines) if l.strip() == "---")
        for i in range(start + 1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1:]).lstrip("\n")
    return text


def _file_url(path):
    """Absolute, percent-encoded file:// URL. Encoding matters: markdown and
    HTML both choke on raw spaces in paths like 'Textbooks notes/IMG 1.JPG'."""
    return QUrl.fromLocalFile(os.path.abspath(path)).toString(
        QUrl.ComponentFormattingOption.FullyEncoded)


def _resolve_media_url(name, base_dir, vault_path):
    """Resolve a vault-relative media reference to an absolute file:// URL."""
    name = name.split("|")[0].strip()
    if name.startswith(("http://", "https://", "file:", "data:")):
        return name
    roots = [base_dir, os.path.join(base_dir, "attachments")]
    if vault_path:
        roots += [vault_path, os.path.join(vault_path, "attachments")]
    for root in roots:
        cand = os.path.join(root, name)
        if os.path.isfile(cand):
            return _file_url(cand)
    # Not found — still hand back a file URL relative to the note's folder
    return _file_url(os.path.join(base_dir, name))


def note_md_to_html(raw, base_dir, vault_path, theme_name):
    """Render app/Obsidian-flavored markdown to a full themed HTML document.
    Images embed inline; video/audio become real playable HTML5 players."""
    text = _strip_frontmatter(raw)
    media = []  # collected <video>/<audio> tags, referenced by token

    def wiki(m):
        name = m.group(1).split("|")[0].strip()
        ext = os.path.splitext(name)[1].lower()
        url = _resolve_media_url(name, base_dir, vault_path)
        if ext in VIDEO_EXTS:
            media.append(f'<video controls preload="metadata" src="{url}"></video>')
            return f"\n\nMEDIATOKEN{len(media) - 1}ENDTOKEN\n\n"
        if ext in AUDIO_EXTS:
            media.append(f'<audio controls preload="metadata" src="{url}"></audio>')
            return f"\n\nMEDIATOKEN{len(media) - 1}ENDTOKEN\n\n"
        # Qt's markdown parser drops images with empty alt text — always supply one
        return f"![{os.path.basename(name)}]({url})"
    text = re.sub(r"!\[\[([^\]]+)\]\]", wiki, text)

    # Standard markdown images with local paths -> resolved file URLs
    def img(m):
        alt = m.group(1).strip() or os.path.basename(m.group(2).strip())
        return f"![{alt}]({_resolve_media_url(m.group(2).strip(), base_dir, vault_path)})"
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", img, text)

    # Flatten Obsidian callout headers: `> [!quote] p.5` -> `> **p.5**`
    out = []
    for line in text.split("\n"):
        cm = re.match(r"^(\s*>+\s*)\[!(\w+)\]\s*(.*)$", line)
        out.append(f"{cm.group(1)}**{cm.group(3).strip() or cm.group(2).capitalize()}**"
                   if cm else line)
    text = "\n".join(out)

    # Reuse Qt's robust markdown parser for the text/image body
    doc = QTextDocument()
    doc.setMarkdown(text, QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
    body_html = doc.toHtml()
    bm = re.search(r"<body[^>]*>(.*)</body>", body_html, re.S)
    inner = bm.group(1) if bm else body_html
    for i, tag in enumerate(media):
        inner = inner.replace(f"MEDIATOKEN{i}ENDTOKEN", tag)

    t = THEMES.get(theme_name, THEMES["AMOLED"])
    bg = "rgb(%d,%d,%d)" % t["window"]
    fg = "rgb(%d,%d,%d)" % t["text"]
    accent = "rgb(%d,%d,%d)" % t["bright"]
    border = "rgba(%d,%d,%d,0.25)" % t["text"]
    soft = "rgba(127,127,127,0.12)"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  html,body {{ margin:0; padding:26px 30px; background:{bg}; color:{fg};
    font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
    font-size:16px; line-height:1.65; }}
  img,video,audio {{ max-width:100%; border-radius:8px; }}
  video,audio {{ width:100%; margin:10px 0; display:block; }}
  a {{ color:{accent}; text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
  h1,h2,h3,h4 {{ line-height:1.3; margin:1.1em 0 0.5em; }}
  blockquote {{ border-left:3px solid {accent}; margin:10px 0; padding:6px 16px;
    background:{soft}; border-radius:4px; }}
  pre {{ background:{soft}; padding:12px 14px; border-radius:8px; overflow:auto; }}
  code {{ background:{soft}; padding:2px 6px; border-radius:4px;
    font-family:Consolas,'Courier New',monospace; }}
  pre code {{ padding:0; background:none; }}
  table {{ border-collapse:collapse; margin:10px 0; }}
  th,td {{ border:1px solid {border}; padding:6px 12px; }}
  hr {{ border:none; border-top:1px solid {border}; margin:18px 0; }}
</style></head><body>{inner}</body></html>"""


class MediaPlayerDialog(QDialog):
    """Plays a video/audio file (or shows an image) in a themed Chromium view.
    Lets lecture recordings etc. open straight from the Notes sidebar."""

    def __init__(self, owner, path):
        super().__init__(owner)
        self.setWindowTitle(os.path.basename(path))
        self.resize(960, 620)
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebEngineCore import QWebEngineSettings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.web = QWebEngineView()
        ws = self.web.settings()
        ws.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        ws.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        layout.addWidget(self.web)

        url = _file_url(path)
        ext = os.path.splitext(path)[1].lower()
        if ext in VIDEO_EXTS:
            tag = f'<video controls autoplay src="{url}"></video>'
        elif ext in AUDIO_EXTS:
            tag = f'<audio controls autoplay src="{url}"></audio>'
        else:
            tag = f'<img src="{url}">'
        t = THEMES.get(owner.theme_name, THEMES["AMOLED"])
        bg = "rgb(%d,%d,%d)" % t["window"]
        self.web.setHtml(
            f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
            html,body {{ margin:0; height:100%; background:{bg};
              display:flex; align-items:center; justify-content:center; }}
            video,img {{ max-width:100%; max-height:100vh; }}
            audio {{ width:90%; }}
            </style></head><body>{tag}</body></html>""",
            QUrl.fromLocalFile(os.path.dirname(os.path.abspath(path)) + os.sep))

    def closeEvent(self, e):
        self.web.setHtml("")  # stop playback
        e.accept()


class MarkdownEditorWidget(QWidget):
    """A create/edit Markdown note page with a live Obsidian-style preview
    (images + playable video) powered by QtWebEngine. Lives as a tab in the
    main window's center area. start_mode="Preview" gives Obsidian's reading
    view; double-clicking the preview (or Ctrl+E) switches to editing."""

    def __init__(self, owner, path=None, start_mode="Split"):
        super().__init__()
        self.owner = owner
        self.path = path
        self._dirty = False
        self._web_proxy = None

        # Lazy import keeps Chromium out of app startup and the PDF workflow
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebEngineCore import QWebEngineSettings

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        bar = QToolBar()
        bar.addAction("💾 Save", self.save)
        bar.addAction("Save As…", self.save_as)
        bar.addSeparator()
        # Formatting: headings reuse the app's own configurable h1-h4 keys
        ks = owner.shortcuts
        for lvl in range(1, 5):
            a = bar.addAction(f"H{lvl}", lambda _=False, n=lvl: self.toggle_heading(n))
            a.setToolTip(f"Heading {lvl} on current/selected lines "
                         f"({ks.get(f'h{lvl}', '')})")
        b = bar.addAction("𝐁", lambda: self.wrap_selection("**"))
        b.setToolTip("Bold (Ctrl+B)")
        i = bar.addAction("𝘐", lambda: self.wrap_selection("*"))
        i.setToolTip("Italic (Ctrl+I)")
        q = bar.addAction("❝", lambda: self.toggle_line_prefix("> "))
        q.setToolTip("Quote (Ctrl+Shift+Q)")
        li = bar.addAction("•", lambda: self.toggle_line_prefix("- "))
        li.setToolTip("Bullet list (Ctrl+Shift+L)")
        bar.addSeparator()
        bar.addAction("🖼 Image", lambda: self.insert_media("image"))
        bar.addAction("🎬 Video", lambda: self.insert_media("video"))
        bar.addSeparator()
        bar.addWidget(QLabel(" View "))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Split", "Editor", "Preview"])
        self.mode_combo.setToolTip("Ctrl+E toggles Editor/Preview, like Obsidian")
        self.mode_combo.currentTextChanged.connect(self.set_mode)
        bar.addWidget(self.mode_combo)
        root.addWidget(bar)

        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("# Write your note in Markdown…\n\n"
                                       "Use 🖼 / 🎬 to embed images and video.")
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(11)
        self.editor.setFont(mono)
        # Route formatting keys (Alt+1…4, Ctrl+B/I, …) to the editor itself,
        # before the main window's application-wide shortcuts can steal them.
        self.editor.installEventFilter(self)

        self.web = QWebEngineView()
        ws = self.web.settings()
        ws.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        ws.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        ws.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        # Double-clicking the preview switches to editing (Obsidian behavior).
        # Chromium routes input to an internal focus-proxy child, so hook that.
        self.web.loadFinished.connect(self._arm_preview_dblclick)

        # Ctrl+E works from the preview too, not just inside the text editor
        e_sc = QShortcut(QKeySequence("Ctrl+E"), self)
        e_sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        e_sc.activated.connect(self.toggle_edit_preview)

        self.split.addWidget(self.editor)
        self.split.addWidget(self.web)
        self.split.setSizes([500, 660])
        root.addWidget(self.split, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self.refresh_preview)
        self.editor.textChanged.connect(self._on_changed)

        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    self.editor.setPlainText(fh.read())
            except Exception as e:
                QMessageBox.warning(self, "Open failed", str(e))
            self._dirty = False
        if start_mode != "Split":
            self.mode_combo.setCurrentText(start_mode)  # triggers set_mode
        self._update_title()
        self.refresh_preview()

    def _arm_preview_dblclick(self, _ok=True):
        fp = self.web.focusProxy()
        if fp is not None and fp is not self._web_proxy:
            fp.installEventFilter(self)
            self._web_proxy = fp

    def _update_title(self):
        name = (os.path.splitext(os.path.basename(self.path))[0]
                if self.path else "Untitled")
        self.owner._update_note_tab(self, f"{name}{' •' if self._dirty else ''}")

    def _base_dir(self):
        if self.path:
            return os.path.dirname(os.path.abspath(self.path))
        return (self.owner.vault_path or self.owner.notes_root
                or os.path.expanduser("~"))

    def _on_changed(self):
        self._dirty = True
        self._update_title()
        self._timer.start()

    def refresh_preview(self):
        html = note_md_to_html(self.editor.toPlainText(), self._base_dir(),
                               self.owner.vault_path, self.owner.theme_name)
        self.web.setHtml(html, QUrl.fromLocalFile(self._base_dir() + os.sep))
        # Keep the Outline panel in sync with this note's headings
        if getattr(self.owner, "notes_tabs", None) is not None \
                and self.owner.notes_tabs.currentWidget() is self:
            self.owner.refresh_outline()

    def goto_block(self, block_no):
        """Scroll the editor to a heading line (from the Outline panel)."""
        if not self.editor.isVisible():
            self.mode_combo.setCurrentText("Split")
        block = self.editor.document().findBlockByNumber(block_no)
        if not block.isValid():
            return
        c = self.editor.textCursor()
        c.setPosition(block.position())
        self.editor.setTextCursor(c)
        self.editor.centerCursor()
        self.editor.setFocus()

    def set_mode(self, mode):
        self.editor.setVisible(mode in ("Split", "Editor"))
        self.web.setVisible(mode in ("Split", "Preview"))
        if mode in ("Split", "Preview"):
            self.refresh_preview()

    # ── Obsidian-style formatting ────────────────────────────────────────────
    def _format_actions(self):
        """Key sequence -> action. Headings reuse the app's configured keys."""
        acts = {}
        for lvl in range(1, 5):
            keys = self.owner.shortcuts.get(f"h{lvl}")
            if keys:
                acts[keys] = lambda n=lvl: self.toggle_heading(n)
        acts["Ctrl+B"] = lambda: self.wrap_selection("**")
        acts["Ctrl+I"] = lambda: self.wrap_selection("*")
        acts["Ctrl+Shift+Q"] = lambda: self.toggle_line_prefix("> ")
        acts["Ctrl+Shift+L"] = lambda: self.toggle_line_prefix("- ")
        acts["Ctrl+E"] = self.toggle_edit_preview
        return acts

    def eventFilter(self, obj, event):
        if obj is self._web_proxy and \
                event.type() == QEvent.Type.MouseButtonDblClick:
            if self.mode_combo.currentText() == "Preview":
                self.mode_combo.setCurrentText("Split")
                return True
            return False
        if obj is self.editor and event.type() in (
                QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
            if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Shift,
                               Qt.Key.Key_Alt, Qt.Key.Key_Meta):
                return super().eventFilter(obj, event)
            pressed = QKeySequence(event.keyCombination())
            for keys, action in self._format_actions().items():
                if QKeySequence(keys).matches(pressed) == \
                        QKeySequence.SequenceMatch.ExactMatch:
                    if event.type() == QEvent.Type.ShortcutOverride:
                        event.accept()  # claim the key from global shortcuts
                    else:
                        action()
                    return True
        return super().eventFilter(obj, event)

    def toggle_edit_preview(self):
        self.mode_combo.setCurrentText(
            "Preview" if self.mode_combo.currentText() != "Preview" else "Editor")

    def toggle_heading(self, level):
        """Set (or toggle off) `level` heading on every selected line."""
        cur = self.editor.textCursor()
        doc = self.editor.document()
        start_block = doc.findBlock(cur.selectionStart())
        end_block = doc.findBlock(cur.selectionEnd())
        blocks = []
        b = start_block
        while True:
            blocks.append(b)
            if b == end_block:
                break
            b = b.next()
        prefix = "#" * level + " "
        all_at_level = all(
            re.match(r"^#{%d} " % level, bl.text()) for bl in blocks)
        cur.beginEditBlock()
        for bl in blocks:
            c = self.editor.textCursor()
            c.setPosition(bl.position())
            c.movePosition(c.MoveOperation.EndOfBlock, c.MoveMode.KeepAnchor)
            stripped = re.sub(r"^#{1,6} ", "", bl.text())
            c.insertText(stripped if all_at_level else prefix + stripped)
        cur.endEditBlock()

    def toggle_line_prefix(self, prefix):
        cur = self.editor.textCursor()
        doc = self.editor.document()
        start_block = doc.findBlock(cur.selectionStart())
        end_block = doc.findBlock(cur.selectionEnd())
        blocks = []
        b = start_block
        while True:
            blocks.append(b)
            if b == end_block:
                break
            b = b.next()
        all_prefixed = all(bl.text().startswith(prefix) for bl in blocks)
        cur.beginEditBlock()
        for bl in blocks:
            c = self.editor.textCursor()
            c.setPosition(bl.position())
            c.movePosition(c.MoveOperation.EndOfBlock, c.MoveMode.KeepAnchor)
            t = bl.text()
            c.insertText(t[len(prefix):] if all_prefixed and t.startswith(prefix)
                         else prefix + t)
        cur.endEditBlock()

    def wrap_selection(self, marker):
        """Wrap the selection in `marker` (bold/italic), or unwrap if already
        wrapped. With no selection, insert the markers and park the cursor
        between them."""
        cur = self.editor.textCursor()
        if not cur.hasSelection():
            cur.insertText(marker + marker)
            cur.movePosition(cur.MoveOperation.Left,
                             cur.MoveMode.MoveAnchor, len(marker))
            self.editor.setTextCursor(cur)
            return
        text = cur.selectedText()
        if text.startswith(marker) and text.endswith(marker) \
                and len(text) >= 2 * len(marker):
            cur.insertText(text[len(marker):-len(marker)])
        else:
            cur.insertText(f"{marker}{text}{marker}")

    def insert_media(self, kind):
        base = (os.path.dirname(os.path.abspath(self.path)) if self.path
                else self.owner.vault_path or self.owner.notes_root)
        if not base:
            QMessageBox.information(
                self, "No home for media",
                "Save this note first (or set a vault / browse a folder), so "
                "embedded media has a folder to live in.")
            return
        if kind == "image":
            flt = "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.svg)"
        else:
            flt = "Videos (*.mp4 *.webm *.mov *.mkv *.m4v *.ogv)"
        src, _ = QFileDialog.getOpenFileName(self, f"Insert {kind}", base, flt)
        if not src:
            return
        # Already inside the note's folder tree? Reference it in place —
        # no copy into attachments/ needed.
        rel = os.path.relpath(os.path.abspath(src), os.path.abspath(base))
        if not rel.startswith(".."):
            self.editor.insertPlainText(f"\n![[{rel.replace(os.sep, '/')}]]\n")
            return
        att = os.path.join(base, "attachments")
        try:
            os.makedirs(att, exist_ok=True)
            dest = os.path.join(att, os.path.basename(src))
            if os.path.abspath(src) != os.path.abspath(dest):
                shutil.copy2(src, dest)
        except Exception as e:
            QMessageBox.warning(self, "Copy failed", str(e))
            return
        self.editor.insertPlainText(f"\n![[attachments/{os.path.basename(src)}]]\n")

    def save(self):
        if not self.path:
            return self.save_as()
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                fh.write(self.editor.toPlainText())
            self._dirty = False
            self._update_title()
            self.owner.statusBar().showMessage(
                f"Saved {os.path.basename(self.path)}", 3000)
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))

    def save_as(self):
        start = self.path or self.owner.vault_path or os.path.expanduser("~")
        path, _ = QFileDialog.getSaveFileName(self, "Save Markdown Note", start,
                                              "Markdown (*.md)")
        if not path:
            return
        if not path.lower().endswith((".md", ".markdown")):
            path += ".md"
        self.path = path
        self.save()
        self.refresh_preview()

    def maybe_close(self):
        """Ask about unsaved changes. Returns False if the user cancels."""
        if self._dirty:
            r = QMessageBox.question(
                self, "Unsaved changes", "Save changes before closing?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Save:
                self.save()
                return not self._dirty  # save may have been cancelled (Save As)
            if r == QMessageBox.StandardButton.Cancel:
                return False
        self.web.setHtml("")  # stop any playing video
        return True


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
    # Required so the lazily-loaded QtWebEngine note preview shares a GL context
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_theme(app, "AMOLED")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())