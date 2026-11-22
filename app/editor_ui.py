"""Native PySide6 editor dialog; every preview is generated locally and non-destructively."""
from __future__ import annotations
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageOps
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QSpinBox, QFileDialog, QMessageBox, QWidget, QFormLayout,
    QScrollArea, QCheckBox)
from . import db, photo_editor


class PhotoEditorDialog(QDialog):
    def __init__(self, db_path: Path, photo_id: int, parent=None):
        super().__init__(parent)
        self.db_path, self.photo_id = db_path, photo_id
        with db.connect(db_path) as con:
            row = con.execute('SELECT path,display_name FROM photos WHERE id=? AND deleted_at IS NULL', (photo_id,)).fetchone()
            if not row:
                raise ValueError('Photo not found or is in Trash')
            self.source_path = Path(row['path'])
            self.recipe = photo_editor.load_recipe(con, photo_id)
        with Image.open(self.source_path) as original:
            self.preview_source = ImageOps.exif_transpose(original).convert('RGB')
        self.preview_source.thumbnail((1300, 1300), Image.Resampling.LANCZOS)
        self.setWindowTitle('Photo editor — '+(row['display_name'] or self.source_path.name))
        self.resize(1050, 720)
        layout = QVBoxLayout(self)
        heading = QLabel('Non-destructive adjustments · Originals stay unchanged · Export creates a new file')
        heading.setWordWrap(True)
        layout.addWidget(heading)
        content = QHBoxLayout(); layout.addLayout(content, 1)
        self.preview = QLabel('Preparing preview…')
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(480, 320)
        self.preview.setStyleSheet('background:#1c211e;color:#f5f7f4;border-radius:10px;')
        content.addWidget(self.preview, 2)
        control_scroll = QScrollArea(); control_scroll.setWidgetResizable(True)
        control_scroll.setMinimumWidth(300)
        control_root = QWidget(); form = QFormLayout(control_root)
        self.crop = QComboBox(); self.crop.addItems(list(photo_editor.CROPS.keys()));
        self.crop.setCurrentText(self.recipe['crop']); self.crop.currentTextChanged.connect(self.schedule_preview)
        form.addRow('Center crop', self.crop)
        self.rotation = QComboBox()
        for angle in (0, 90, 180, 270): self.rotation.addItem(f'{angle}° clockwise', angle)
        self.rotation.setCurrentIndex([0,90,180,270].index(self.recipe['rotate']))
        self.rotation.currentIndexChanged.connect(self.schedule_preview)
        form.addRow('Rotate', self.rotation)
        self.sliders = {}
        for field, (minimum, maximum) in photo_editor.RANGES.items():
            wrap = QWidget(); horizontal = QHBoxLayout(wrap);horizontal.setContentsMargins(0,0,0,0)
            slider = QSlider(Qt.Orientation.Horizontal);slider.setRange(minimum,maximum)
            slider.setValue(self.recipe[field]);slider.valueChanged.connect(self.schedule_preview)
            value = QLabel(str(self.recipe[field]));value.setMinimumWidth(32)
            slider.valueChanged.connect(lambda n,label=value:label.setText(str(n)))
            horizontal.addWidget(slider,1);horizontal.addWidget(value)
            form.addRow(field.replace('_',' ').capitalize(),wrap)
            self.sliders[field]=slider
        self.compare = QCheckBox('Show unedited original (before)')
        self.compare.toggled.connect(self.schedule_preview)
        form.addRow('',self.compare)
        self.width=QSpinBox();self.width.setRange(0,8000);self.width.setValue(0)
        self.height=QSpinBox();self.height.setRange(0,8000);self.height.setValue(0)
        self.format=QComboBox();self.format.addItems(['WEBP','JPEG','PNG'])
        self.quality=QSpinBox();self.quality.setRange(40,100);self.quality.setValue(86)
        for name,widget in [('Export width (0 = auto)',self.width),('Export height (0 = auto)',self.height),
                            ('Export format',self.format),('JPEG/WebP quality',self.quality)]:form.addRow(name,widget)
        note = QLabel('Crop is center-based in this release. For exact website sizes use both output dimensions, e.g. 272 × 300. Edits are recipes, not new originals.')
        note.setWordWrap(True);form.addRow('',note)
        control_scroll.setWidget(control_root);content.addWidget(control_scroll,1)
        footer=QHBoxLayout()
        self.save_btn=QPushButton('Save adjustments');self.save_btn.clicked.connect(self.save)
        self.export_btn=QPushButton('Export edited copy…');self.export_btn.clicked.connect(self.export)
        self.reset_btn=QPushButton('Reset');self.reset_btn.clicked.connect(self.reset)
        self.close_btn=QPushButton('Close');self.close_btn.clicked.connect(self.reject)
        for b in (self.save_btn,self.export_btn,self.reset_btn,self.close_btn):footer.addWidget(b)
        layout.addLayout(footer)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(180)
        self.timer.timeout.connect(self.refresh_preview)
        self.refresh_preview()

    def current_recipe(self):
        return photo_editor.normalize_recipe({'crop':self.crop.currentText(), 'rotate':self.rotation.currentData(),
            **{key:widget.value() for key,widget in self.sliders.items()}})

    def schedule_preview(self, *_):self.timer.start()

    def refresh_preview(self):
        try:
            recipe = None if self.compare.isChecked() else self.current_recipe()
            image = photo_editor.apply_recipe(self.preview_source, recipe, preview_max=850)
            buffer=BytesIO();image.save(buffer,'JPEG',quality=83)
            pix=QPixmap();pix.loadFromData(buffer.getvalue(),'JPEG')
            self.preview.setPixmap(pix.scaled(self.preview.size(),Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation))
        except Exception as exc:
            self.preview.setText('Preview could not be rendered: '+str(exc))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'timer'):self.timer.start()

    def save(self):
        try:
            with db.connect(self.db_path) as con:
                photo_editor.save_recipe(con,self.photo_id,self.current_recipe())
            QMessageBox.information(self,'Adjustments saved','The edit recipe was saved locally. The original image was not modified.')
        except Exception as exc:QMessageBox.warning(self,'Save failed',str(exc))

    def reset(self):
        self.crop.setCurrentText('original');self.rotation.setCurrentIndex(0)
        for slider in self.sliders.values():slider.setValue(0)
        self.compare.setChecked(False);self.schedule_preview()

    def export(self):
        suffix={'WEBP':'.webp','JPEG':'.jpg','PNG':'.png'}[self.format.currentText()]
        suggested=str(self.source_path.with_name(self.source_path.stem+'-edited'+suffix))
        name,_=QFileDialog.getSaveFileName(self,'Export edited photograph',suggested,
                                          'Images (*.webp *.jpg *.jpeg *.png)')
        if not name:return
        dest=Path(name)
        if dest.suffix.lower() not in ('.webp','.jpg','.jpeg','.png'):
            dest=dest.with_suffix(suffix)
        if dest.exists():
            QMessageBox.warning(self,'File already exists','Choose a new file name. Editing never overwrites an existing file.')
            return
        try:
            dimensions=photo_editor.export_copy(self.source_path,dest,self.current_recipe(),
                        width=self.width.value(),height=self.height.value(),quality=self.quality.value())
            QMessageBox.information(self,'Export complete',f'Edited copy saved ({dimensions[0]} × {dimensions[1]}) to:\n{dest}\n\nOriginal unchanged.')
        except Exception as exc:QMessageBox.warning(self,'Export failed',str(exc))
