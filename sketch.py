"""Sketch Sticky drawing canvas: pen + pixel eraser, saved as a PNG."""
from PyQt6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QMenu, QComboBox)
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QColor, QPainter, QPen, QImage

from theme import PEN_COLORS, pen_qcolor

class SketchCanvasDialog(QDialog):
    """A resizable drawing surface: pen + pixel eraser. Returns a QImage on save."""
    def __init__(self, parent=None, existing_image=None, init_w=420, init_h=320,
                 pen_color=None, pen_width=3):
        super().__init__(parent)
        self.setWindowTitle("🖌 Sketch Sticky")
        self.setMinimumSize(220, 180)
        self.resize(init_w, init_h)

        self.pen_color = pen_color or QColor(20, 20, 20)
        self.pen_width = pen_width
        self.eraser_mode = False
        self.eraser_width = 18
        self._last = None
        self.result_image = None

        # The canvas image (transparent so the page shows through when stamped)
        self._canvas = QImage(init_w, init_h - 44, QImage.Format.Format_ARGB32)
        self._canvas.fill(Qt.GlobalColor.transparent)
        if existing_image is not None and not existing_image.isNull():
            p = QPainter(self._canvas)
            p.drawImage(0, 0, existing_image.scaled(
                self._canvas.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            p.end()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Toolbar row
        bar = QHBoxLayout()
        self.pen_btn = QPushButton("✏ Pen"); self.pen_btn.setCheckable(True); self.pen_btn.setChecked(True)
        self.eraser_btn = QPushButton("🧽 Eraser"); self.eraser_btn.setCheckable(True)
        self.pen_btn.clicked.connect(lambda: self._set_eraser(False))
        self.eraser_btn.clicked.connect(lambda: self._set_eraser(True))
        bar.addWidget(self.pen_btn); bar.addWidget(self.eraser_btn)

        color_btn = QPushButton("🎨")
        color_btn.setToolTip("Pen color")
        color_menu = QMenu(self)
        for cname in PEN_COLORS:
            act = color_menu.addAction(cname)
            act.triggered.connect(lambda checked, c=cname: self._set_color(c))
        color_btn.setMenu(color_menu)
        bar.addWidget(color_btn)

        self.width_combo = QComboBox()
        for wl, wv in [("1", 1), ("2", 2), ("3", 3), ("5", 5), ("8", 8)]:
            self.width_combo.addItem(wl, wv)
        self.width_combo.setCurrentText(str(pen_width))
        self.width_combo.setFixedWidth(52)
        self.width_combo.currentIndexChanged.connect(
            lambda: setattr(self, "pen_width", self.width_combo.currentData()))
        bar.addWidget(QLabel("W:")); bar.addWidget(self.width_combo)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear)
        bar.addWidget(clear_btn)
        bar.addStretch()
        layout.addLayout(bar)

        # Drawing area label (the canvas is painted in paintEvent of an inner widget)
        self.surface = _SketchSurface(self)
        layout.addWidget(self.surface, 1)

        # Save / Cancel
        btns = QHBoxLayout()
        btns.addStretch()
        save_btn = QPushButton("Save"); cancel_btn = QPushButton("Cancel")
        save_btn.clicked.connect(self._on_save); cancel_btn.clicked.connect(self.reject)
        btns.addWidget(save_btn); btns.addWidget(cancel_btn)
        layout.addLayout(btns)

    def _set_eraser(self, on):
        self.eraser_mode = on
        self.pen_btn.setChecked(not on); self.eraser_btn.setChecked(on)

    def _set_color(self, cname):
        self.pen_color = pen_qcolor(cname)
        self._set_eraser(False)

    def _clear(self):
        self._canvas.fill(Qt.GlobalColor.transparent)
        self.surface.update()

    def _ensure_canvas_size(self, w, h):
        if w <= self._canvas.width() and h <= self._canvas.height():
            return
        bigger = QImage(max(w, self._canvas.width()), max(h, self._canvas.height()),
                        QImage.Format.Format_ARGB32)
        bigger.fill(Qt.GlobalColor.transparent)
        p = QPainter(bigger); p.drawImage(0, 0, self._canvas); p.end()
        self._canvas = bigger

    def draw_to(self, pt):
        self._ensure_canvas_size(pt.x() + 2, pt.y() + 2)
        painter = QPainter(self._canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.eraser_mode:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            pen = QPen(Qt.GlobalColor.transparent, self.eraser_width)
        else:
            pen = QPen(self.pen_color, self.pen_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        if self._last is not None:
            painter.drawLine(self._last, pt)
        else:
            painter.drawPoint(pt)
        painter.end()
        self._last = pt
        self.surface.update()

    def end_stroke(self):
        self._last = None

    def _content_bounds(self):
        """Tight bounding box of non-transparent pixels; None if empty."""
        w, h = self._canvas.width(), self._canvas.height()
        minx, miny, maxx, maxy = w, h, 0, 0
        found = False
        for y in range(0, h, 2):
            for x in range(0, w, 2):
                if (self._canvas.pixel(x, y) >> 24) & 0xFF:
                    found = True
                    minx = min(minx, x); miny = min(miny, y)
                    maxx = max(maxx, x); maxy = max(maxy, y)
        if not found:
            return None
        pad = 6
        return QRect(max(0, minx - pad), max(0, miny - pad),
                     min(w, maxx + pad) - max(0, minx - pad),
                     min(h, maxy + pad) - max(0, miny - pad))

    def _on_save(self):
        bounds = self._content_bounds()
        if bounds is None:
            self.reject()
            return
        cropped = self._canvas.copy(bounds)
        # Composite over white: transparent PNGs render invisibly in some PDF
        # viewers and wash out in the expanded pin view.
        flat = QImage(cropped.size(), QImage.Format.Format_RGB32)
        flat.fill(QColor(255, 255, 255))
        p = QPainter(flat)
        p.drawImage(0, 0, cropped)
        p.end()
        self.result_image = flat
        self.accept()


class _SketchSurface(QWidget):
    """Inner widget that displays the dialog's canvas and forwards mouse strokes."""
    def __init__(self, dlg):
        super().__init__(dlg)
        self.dlg = dlg
        self.setStyleSheet("background: white; border: 1px solid #888;")
        self.setCursor(Qt.CursorShape.CrossCursor)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(255, 255, 255))
        p.drawImage(0, 0, self.dlg._canvas)
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.dlg.draw_to(e.pos())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            self.dlg.draw_to(e.pos())

    def mouseReleaseEvent(self, e):
        self.dlg.end_stroke()