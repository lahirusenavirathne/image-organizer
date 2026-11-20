"""Light, responsive Qt photo-library presentation.

These widgets are deliberately UI-only; indexing and file moves remain in their
existing reviewed workflows. A card uses the cached thumbnail only and never
changes its underlying photo.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QStyledItemDelegate, QStyle


STYLE = """
QMainWindow, QWidget { background: #F7F9FC; color: #182B3A; font-family: 'Segoe UI', Arial; font-size: 12px; }
QFrame#Sidebar { background: #FFFFFF; border-right: 1px solid #E6EBF1; }
QFrame#Workspace, QWidget#Workspace, QWidget#PhotoArea { background: #F7F9FC; }
QFrame#Toolbar, QFrame#FilterPanel, QWidget#Inspector { background: #FFFFFF; border: 1px solid #E4EBF0; border-radius: 12px; }
QLabel#Brand { color: #0C684F; font-weight: 800; font-size: 17px; }
QLabel#Headline { color: #182B3A; font-weight: 750; font-size: 23px; }
QLabel#SectionTitle { color: #142D3C; font-weight: 700; font-size: 14px; }
QLabel#Subtle { color: #6D7D89; }
QLabel#Tiny { color: #7D8B95; font-size: 11px; }
QLabel#Count { color: #47715F; background: #E7F6EB; border-radius: 10px; padding: 5px 10px; font-weight: 700; }
QLabel#Badge { color: #247453; background: #DDF4E7; border-radius: 8px; padding: 4px 9px; }
QPushButton { background: #FFFFFF; color: #253D4D; padding: 9px 13px; border: 1px solid #DAE3E9; border-radius: 8px; font-weight: 600; }
QPushButton:hover { background: #EFF6F3; border-color: #8DC3AE; }
QPushButton:disabled { background: #F1F4F5; color: #A6B0B7; }
QPushButton#Primary { color: #FFFFFF; background: #117A5C; border: 1px solid #117A5C; }
QPushButton#Primary:hover { background: #0A674D; }
QPushButton#NavButton { text-align: left; color: #5F7280; background: transparent; border: 0px; border-radius: 9px; padding: 11px 14px; font-size: 12px; font-weight: 600; }
QPushButton#NavButton:hover { background: #F0F5F3; color: #1C7354; }
QPushButton#NavButton[active="true"] { background: #E7F6ED; color: #0E704F; }
QPushButton#NavButton[active="true"]:hover { background: #DEF1E6; }
QToolButton { background: #FFFFFF; border: 1px solid #DEE5EA; border-radius: 8px; padding: 9px 12px; color: #253D4D; font-weight: 600; }
QToolButton:hover { background: #EDF6F1; border-color: #A5CEB9; }
QToolButton:checked { color: #116A4E; background: #E7F6ED; }
QLineEdit, QTextEdit, QComboBox, QSpinBox, QTableWidget { background: #FFFFFF; color: #193244; border: 1px solid #DBE4E9; border-radius: 8px; padding: 9px; selection-background-color: #117A5C; }
QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border: 1px solid #179473; }
QListWidget#PhotoGrid { background: transparent; border: 0px; padding: 5px; outline: 0; }
QListWidget#PhotoGrid::item { border: 0px; background: transparent; }
QListWidget#PhotoGrid::item:selected { background: transparent; }
QScrollArea { background: transparent; border: 0px; }
QScrollBar:vertical { background: #F3F6F7; width: 10px; border: none; }
QScrollBar::handle:vertical { background: #C9D5D6; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QTableWidget { gridline-color: #E8EDF1; }
QTableWidget::item:selected { background: #DDF2E7; color: #1D4538; }
QHeaderView::section { background: #EDF3F2; border: 0px; border-bottom: 1px solid #DCE7E7; color: #344B58; padding: 9px; font-weight: 600; }
QGroupBox { border: 1px solid #E2E8ED; border-radius: 9px; margin-top: 12px; padding: 12px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
QProgressBar { background: #E8F0EF; border: 0px; border-radius: 5px; height: 7px; }
QProgressBar::chunk { background: #168562; border-radius: 5px; }
QTabWidget::pane { border: 0; }
QMenu { background: white; color: #244153; border: 1px solid #D8E3E7; padding: 5px; }
QMenu::item { padding: 9px 24px; border-radius: 6px; }
QMenu::item:selected { background: #E4F3EB; color: #116C4E; }
QSplitter::handle { background: transparent; }
"""


class PhotoCardDelegate(QStyledItemDelegate):
    """Draw image-rich, rounded cards using the gallery's existing thumbnails."""
    CARD_WIDTH = 242
    CARD_HEIGHT = 226

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect.adjusted(5, 5, -5, -5))
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.setPen(QColor('#158763' if selected else '#E2EAF0'))
        painter.setBrush(QColor('#E9F7ED' if selected else '#FFFFFF'))
        painter.drawRoundedRect(rect, 12, 12)
        image_height = max(110, min(146, rect.height() - 72))
        image_rect = QRectF(rect.left() + 6, rect.top() + 6, rect.width() - 12, image_height)
        path = QPainterPath()
        path.addRoundedRect(image_rect, 9, 9)
        painter.setClipPath(path)
        painter.fillRect(image_rect, QColor('#E7EEF1'))
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if icon is not None:
            pixmap = icon.pixmap(QSize(int(image_rect.width()), int(image_rect.height())))
            if not pixmap.isNull():
                painter.drawPixmap(image_rect.toRect(), pixmap)
        painter.setClipping(False)
        fname = index.data(Qt.ItemDataRole.UserRole + 1) or ''
        subtitle = index.data(Qt.ItemDataRole.UserRole + 2) or 'Unclassified'
        badge = index.data(Qt.ItemDataRole.UserRole + 3) or ''
        painter.setFont(QFont('Segoe UI', 10, QFont.Weight.DemiBold))
        painter.setPen(QColor('#203744'))
        text_rect = QRectF(rect.left() + 10, image_rect.bottom() + 8, rect.width() - 20, 20)
        metrics = painter.fontMetrics()
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         metrics.elidedText(fname, Qt.TextElideMode.ElideMiddle, int(text_rect.width())))
        painter.setFont(QFont('Segoe UI', 9))
        painter.setPen(QColor('#6B7C86'))
        subrect = QRectF(rect.left() + 10, image_rect.bottom() + 30, rect.width() - 20, 17)
        painter.drawText(subrect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         painter.fontMetrics().elidedText(subtitle, Qt.TextElideMode.ElideRight, int(subrect.width())))
        if badge:
            painter.setPen(QColor('#127452'))
            painter.setFont(QFont('Segoe UI', 8, QFont.Weight.DemiBold))
            r = QRectF(rect.right() - 91, rect.top() + 14, 80, 22)
            painter.setBrush(QColor('#E1F6E8'))
            painter.drawRoundedRect(r, 9, 9)
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter,
                             painter.fontMetrics().elidedText(badge, Qt.TextElideMode.ElideRight, 70))
        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor('#11805C'))
            painter.drawEllipse(QRectF(rect.right() - 30, image_rect.bottom() - 28, 21, 21))
            painter.setPen(QColor('white'))
            painter.drawText(QRectF(rect.right() - 30, image_rect.bottom() - 28, 21, 20),
                             Qt.AlignmentFlag.AlignCenter, '✓')
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(self.CARD_WIDTH, self.CARD_HEIGHT)
