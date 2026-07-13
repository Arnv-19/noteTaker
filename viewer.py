"""The PDF page viewer widget: selection, drawing strokes, sketch-sticky clicks."""
from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QColor, QPainter, QPen

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
        self._dbl_click_time = 0
        self.draw_mode = False
        self._current_stroke = []   # live points [(x,y),...] in viewer pixels
        self.pen_color = QColor(255, 0, 0)
        self.pen_width = 3

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.draw_mode:
            self._current_stroke = [(event.pos().x(), event.pos().y())]
            self.update()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            # Eraser mode: delete whatever annotation is under the cursor
            if self.main_window and getattr(self.main_window, "eraser_action", None) \
                    and self.main_window.eraser_action.isChecked():
                self.main_window.erase_at(event.pos())
                return
            # A click on a sketch sticky toggles it (open/collapse) instead of selecting
            if self.main_window and self.main_window.handle_sketch_click(event.pos()):
                return
            # Triple-click: a press arriving right after a double-click
            if self.main_window and self._dbl_click_time and \
               (event.timestamp() - self._dbl_click_time) < 450:
                self._dbl_click_time = 0
                self.main_window.select_block_at(event.pos())
                return
            if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                if self.main_window:
                    self.main_window.clear_accumulated_selection()
                self.selected_rects = []
            self.start_point = event.pos()
            self.end_point = event.pos()
            if self.main_window:
                self.main_window.begin_selection(event.pos())
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            if self.main_window:
                self.main_window.show_viewer_context_menu(event.pos())

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.main_window:
            self._dbl_click_time = event.timestamp()
            self.main_window.select_word_at(event.pos())

    def mouseMoveEvent(self, event):
        if self.draw_mode:
            if self._current_stroke:
                self._current_stroke.append((event.pos().x(), event.pos().y()))
                self.update()
            return
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
        if event.button() == Qt.MouseButton.LeftButton and self.draw_mode:
            if self._current_stroke and len(self._current_stroke) > 1 and self.main_window:
                self.main_window.commit_ink_stroke(self._current_stroke)
            self._current_stroke = []
            self.update()
            return
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
        self._current_stroke = []
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

        # Live ink stroke preview
        if self._current_stroke and len(self._current_stroke) > 1:
            pen = QPen(self.pen_color, self.pen_width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for i in range(1, len(self._current_stroke)):
                x0, y0 = self._current_stroke[i-1]
                x1, y1 = self._current_stroke[i]
                painter.drawLine(int(x0), int(y0), int(x1), int(y1))

        painter.end()