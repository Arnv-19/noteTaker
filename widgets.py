"""Small reusable widgets."""
from PyQt6.QtWidgets import QCheckBox
from PyQt6.QtCore import Qt, QPoint, QRect, pyqtProperty, QPropertyAnimation
from PyQt6.QtGui import QColor, QPainter

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