"""Windows-oriented Qt desktop UI. All long-running operations use worker threads."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Callable
from PySide6.QtCore import Qt, QThread, Signal, QSize, QTimer
from PySide6.QtGui import QIcon, QPixmap, QImage, QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QLineEdit, QTextEdit,
    QFileDialog, QMessageBox, QListWidget, QListWidgetItem, QListView, QComboBox,
    QVBoxLayout, QHBoxLayout, QFormLayout, QSplitter, QScrollArea, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QSpinBox, QDialog, QDialogButtonBox,
    QProgressBar, QGroupBox, QInputDialog, QAbstractItemView, QCheckBox
)
from PIL import Image, ImageOps
from . import db
from .catalog import ACTIVITIES
from .operations import preview_moves, execute_moves, undo_last_batch, export_photos
from .faces import download_models, group_faces
from .recognition import run_local, run_cloud, local_ai_missing, test_local_model
from .library_tools import analyze_library, exact_duplicates, similar_pairs, set_rights
from .ai_cache import review_pending, review as review_ai

PAGE_SIZE=120

STYLE="""
QMainWindow, QWidget { background:#111827; color:#E5E7EB; font-family:'Segoe UI',Arial; font-size:12px; }
QWidget#MainPanel { background:#172033; }
QLabel#Title { color:white; font-size:22px; font-weight:700; }
QLabel#Subtle { color:#A3B2C8; }
QLineEdit, QTextEdit, QComboBox, QSpinBox, QTableWidget, QListWidget {
 background:#1F2937; color:#F3F4F6; border:1px solid #384659; padding:7px; border-radius:7px;
 selection-background-color:#16735D; selection-color:white; }
QListWidget { padding:8px; }
QListWidget::item { padding:5px; border-radius:8px; }
QListWidget::item:selected { background:#176C58; border:1px solid #36B492; }
QPushButton { background:#26394B; color:white; padding:9px 13px; border:1px solid #3A5368; border-radius:7px; font-weight:600; }
QPushButton:hover { background:#37556A; }
QPushButton:disabled { color:#6B7280; background:#202938; }
QPushButton#Primary { background:#14846C; border:1px solid #189B7C; }
QPushButton#Primary:hover { background:#189A7E; }
QTabWidget::pane { border:1px solid #344155; }
QTabBar::tab { color:#A3B2C8; background:#1F2937; padding:10px 22px; }
QTabBar::tab:selected { color:white; background:#16735D; }
QHeaderView::section { background:#28384B; color:white; padding:8px; }
QGroupBox { border:1px solid #344155; border-radius:8px; margin-top:12px; padding:12px; font-weight:600; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 5px; }
QProgressBar { background:#28384B; border:0; border-radius:5px; height:7px; }
QProgressBar::chunk { background:#18A77F; border-radius:5px; }
QScrollArea { border:0; }
"""

class Task(QThread):
    progress=Signal(str)
    succeeded=Signal(object)
    failed=Signal(str)
    def __init__(self, fn:Callable):
        super().__init__(); self.fn=fn
    def run(self):
        try: self.succeeded.emit(self.fn(self.progress.emit))
        except Exception as e: self.failed.emit(str(e))

class ExportDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle('Export photos - size and format')
        self.resize(420,310)
        layout=QVBoxLayout(self)
        form=QFormLayout()
        self.preset=QComboBox()
        self.preset.addItems(['Custom','Blog thumbnail 272 x 300','Website 1200 x 800','Social square 1080 x 1080','Social portrait 1080 x 1350','Full HD 1920 x 1080','Portrait gallery 1200 x 1600'])
        self.preset.currentIndexChanged.connect(self.use_preset)
        self.width=QSpinBox(); self.width.setRange(0,16000); self.width.setValue(1200)
        self.height=QSpinBox(); self.height.setRange(0,16000); self.height.setValue(800)
        self.format=QComboBox(); self.format.addItems(['WEBP','JPEG','PNG','TIFF'])
        self.mode=QComboBox(); self.mode.addItems(['Crop to fill','Pad to fit'])
        self.quality=QSpinBox(); self.quality.setRange(1,100); self.quality.setValue(85)
        for title,control in [('Size preset',self.preset),('Width (px)',self.width),('Height (px)',self.height),
                              ('Output format',self.format),('Fit mode',self.mode),('JPEG/WebP quality',self.quality)]:
            form.addRow(title,control)
        layout.addLayout(form)
        self.seo_names=QCheckBox('SEO-friendly filenames and bilingual alt text (ES/EN) in CSV')
        self.seo_names.setChecked(True)
        layout.addWidget(self.seo_names)
        info=QLabel('0 in one dimension preserves aspect ratio. Exports are new files; a CSV manifest records copyright and provenance.')
        info.setWordWrap(True); info.setObjectName('Subtle');layout.addWidget(info)
        controls=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(self.accept);controls.rejected.connect(self.reject);layout.addWidget(controls)
    def use_preset(self,index):
        vals={1:(272,300),2:(1200,800),3:(1080,1080),4:(1080,1350),5:(1920,1080),6:(1200,1600)}
        if index in vals: self.width.setValue(vals[index][0]);self.height.setValue(vals[index][1])

class ReviewDialog(QDialog):
    def __init__(self, plan,parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'Review {len(plan)} proposed moves - no files moved yet')
        self.resize(1000,540)
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('Review all destinations. Files will move only after you click Approve moves. Collisions are renamed, never overwritten.'))
        table=QTableWidget(len(plan),2)
        table.setHorizontalHeaderLabels(['Current file','Proposed destination'])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for i,p in enumerate(plan):
            table.setItem(i,0,QTableWidgetItem(p['source']))
            table.setItem(i,1,QTableWidgetItem(p['destination']))
        layout.addWidget(table)
        buttons=QDialogButtonBox()
        okay=buttons.addButton('Approve moves',QDialogButtonBox.ButtonRole.AcceptRole)
        okay.setObjectName('Primary')
        buttons.addButton('Cancel',QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

class Window(QMainWindow):
    def __init__(self,app_dir:Path):
        super().__init__()
        self.app_dir=app_dir
        self.db_path=app_dir/'photos.db'
        self.model_dir=app_dir/'models'
        self.thumb_dir=app_dir/'thumbnails'
        self.thumb_dir.mkdir(parents=True,exist_ok=True)
        db.init(self.db_path)
        self.offset=0
        self.total=0
        self.group_filter=None
        self.visible_rows={}
        self.current_id=None
        self.task=None
        self.action_buttons=[]
        self.setWindowTitle('Guia Lanka Photo Manager  •  Local-first photo intelligence')
        self.resize(1440,850)
        self.setMinimumSize(990,650)
        self.setStyleSheet(STYLE)
        self.build_ui()
        self.load_page()
        self.refresh_groups()

    def refresh_ai_notice(self):
        missing = local_ai_missing()
        if missing:
            self.ai_notice.setText('Local visual AI is not installed: ' + ', '.join(missing)
                + '. Close the app and run INSTALL_AI_WINDOWS.bat; then restart it. '
                'Photo import and exports can still work without this component.')
        else:
            self.ai_notice.setText('Local visual AI is installed. Click Test local AI to verify the model; '
                'first use may download model weights. Classification results are suggestions for review.')

    def test_local_ai(self):
        self.refresh_ai_notice()
        missing = local_ai_missing()
        if missing:
            QMessageBox.warning(self, 'Local AI not installed',
                'Missing: ' + ', '.join(missing) + '\n\n'
                'Close the application, run INSTALL_AI_WINDOWS.bat in the application folder, '
                'and restart the application.\n\n'
                'If installation fails, run DIAGNOSE_AI_WINDOWS.bat and copy the error.')
            return
        if QMessageBox.question(self, 'Test local visual AI',
                'Test whether OpenCLIP can load and recognize images? '
                'A model download may be needed the first time.') != QMessageBox.StandardButton.Yes:
            return
        self.task_start(lambda p:test_local_model(p),
            lambda result:QMessageBox.information(self,'Local AI test passed',result))

    def add_action(self,layout,label,handler,primary=False):
        b=QPushButton(label)
        if primary: b.setObjectName('Primary')
        b.clicked.connect(handler);layout.addWidget(b)
        self.action_buttons.append(b)
        return b

    def build_ui(self):
        root=QWidget(); self.setCentralWidget(root)
        main=QVBoxLayout(root); main.setContentsMargins(16,14,16,10);main.setSpacing(12)
        title_row=QHBoxLayout()
        brand=QVBoxLayout()
        t=QLabel('GUIA LANKA  /  PHOTO MANAGER');t.setObjectName('Title')
        brand.addWidget(t)
        subtitle=QLabel('Offline library  ·  AI attraction tags  ·  local faces  ·  review-first moves  ·  export presets')
        subtitle.setObjectName('Subtle');brand.addWidget(subtitle)
        title_row.addLayout(brand);title_row.addStretch()
        self.total_label=QLabel('0 photos indexed')
        title_row.addWidget(self.total_label);main.addLayout(title_row)

        controls=QHBoxLayout();controls.setSpacing(7)
        self.add_action(controls,'+ Add folder',self.import_folder,True)
        self.add_action(controls,'AI tag selected',self.tag_selected)
        self.add_action(controls,'Test local AI',self.test_local_ai)
        self.add_action(controls,'Scan quality',self.analyze_quality)
        self.add_action(controls,'Duplicates',self.show_duplicates)
        self.add_action(controls,'AI review queue',self.show_ai_reviews)
        self.add_action(controls,'Group faces',self.scan_faces)
        self.add_action(controls,'Get face models',self.get_models)
        self.add_action(controls,'Cloud AI selected',self.cloud_selected)
        self.add_action(controls,'Review moves',self.move_selected)
        self.add_action(controls,'Undo last moves',self.undo_moves)
        self.add_action(controls,'Export selected',self.export_selected,True)
        controls.addStretch();main.addLayout(controls)
        self.ai_notice=QLabel()
        self.ai_notice.setWordWrap(True)
        self.ai_notice.setStyleSheet('color: #F6CA70; font-size:12px;')
        main.addWidget(self.ai_notice)
        self.refresh_ai_notice()

        self.tabs=QTabWidget();main.addWidget(self.tabs,1)
        photos=QWidget();self.tabs.addTab(photos,'Photo Library')
        photo_layout=QVBoxLayout(photos)
        filters=QHBoxLayout()
        self.search=QLineEdit();self.search.setPlaceholderText('Search filename, attraction, tags, source, copyright…')
        self.search.returnPressed.connect(self.reset_page)
        filters.addWidget(self.search,4)
        self.locations=QComboBox();self.locations.setMinimumWidth(150)
        self.locations.addItem('All locations','');self.locations.currentIndexChanged.connect(self.reset_page)
        filters.addWidget(self.locations,1)
        self.activities=QComboBox();self.activities.addItem('All activities','')
        for name in ACTIVITIES: self.activities.addItem(name,name)
        self.activities.currentIndexChanged.connect(self.reset_page)
        filters.addWidget(self.activities,1)
        self.add_action(filters,'Search / refresh',self.reset_page)
        self.add_action(filters,'Clear filters',self.clear_filters)
        photo_layout.addLayout(filters)

        splitter=QSplitter(Qt.Orientation.Horizontal)
        self.list=QListWidget()
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setFlow(QListView.Flow.LeftToRight)
        self.list.setWrapping(True)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setIconSize(QSize(144,114))
        self.list.setGridSize(QSize(184,164))
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.itemSelectionChanged.connect(self.select_photo)
        splitter.addWidget(self.list)
        right=QScrollArea();right.setWidgetResizable(True)
        panel=QWidget();panel.setObjectName('MainPanel')
        v=QVBoxLayout(panel);v.setContentsMargins(15,12,15,12);v.setSpacing(10)
        self.photo_title=QLabel('Select an image');self.photo_title.setWordWrap(True)
        v.addWidget(self.photo_title)
        self.preview=QLabel('Photo preview')
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(235)
        self.preview.setStyleSheet('background:#0B1220; border:1px solid #32455C; border-radius:8px;')
        v.addWidget(self.preview)
        self.technical=QLabel('');self.technical.setObjectName('Subtle');self.technical.setWordWrap(True);v.addWidget(self.technical)
        form=QFormLayout(); form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.edits={}
        for field,label in [('location','Location'),('activity','Activities (comma separated)'),('attraction','Attraction'),
                            ('source_url','Source website URL'),('artist','Photographer'),('copyright','Copyright'),('license','License / usage rights')]:
            edit=QLineEdit();edit.setPlaceholderText(label)
            self.edits[field]=edit;form.addRow(label,edit)
        v.addLayout(form)
        self.rights_status=QComboBox();self.rights_status.addItems(['Unknown','Verified','Permission required'])
        form.addRow('Usage rights status',self.rights_status)
        self.add_action(v,'Save reviewed metadata',self.save_details,True)
        self.source_label=QLabel('Original source folder:');self.source_label.setObjectName('Subtle')
        self.source_label.setWordWrap(True);v.addWidget(self.source_label)
        v.addStretch()
        right.setWidget(panel)
        splitter.addWidget(right)
        splitter.setSizes([910,470]);splitter.setStretchFactor(0,2)
        photo_layout.addWidget(splitter,1)
        page=QHBoxLayout();self.prev=QPushButton('Previous page');self.next=QPushButton('Next page')
        self.prev.clicked.connect(self.previous_page);self.next.clicked.connect(self.next_page)
        self.page_label=QLabel('Page 1');page.addWidget(self.prev);page.addWidget(self.next)
        page.addWidget(self.page_label);page.addStretch()
        selinfo=QLabel('Tip: Ctrl+A selects all images on this page')
        selinfo.setObjectName('Subtle');page.addWidget(selinfo)
        photo_layout.addLayout(page)

        people=QWidget();self.tabs.addTab(people,'People / Face Groups')
        people_v=QVBoxLayout(people)
        intro=QLabel('Local face embeddings are stored only in the application database. Groups are suggestions, not verified identities. Double-click a group to browse its photos.')
        intro.setWordWrap(True);people_v.addWidget(intro)
        pplbuttons=QHBoxLayout()
        self.add_action(pplbuttons,'Refresh face groups',self.refresh_groups)
        self.add_action(pplbuttons,'Rename selected group',self.rename_group)
        self.add_action(pplbuttons,'Show all library photos',self.clear_filters)
        pplbuttons.addStretch();people_v.addLayout(pplbuttons)
        self.groups_table=QTableWidget(0,4)
        self.groups_table.setHorizontalHeaderLabels(['Group ID','Name / label','Number of photos','Faces'])
        self.groups_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.groups_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.groups_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.groups_table.doubleClicked.connect(self.open_group)
        people_v.addWidget(self.groups_table,1)

        bottom=QHBoxLayout()
        self.status=QLabel('Ready. Add a local folder to start indexing photos.');self.status.setObjectName('Subtle')
        bottom.addWidget(self.status,1)
        self.busybar=QProgressBar();self.busybar.setMaximumWidth(190);self.busybar.hide()
        bottom.addWidget(self.busybar);main.addLayout(bottom)

    def task_start(self,fn,done=None):
        if self.task and self.task.isRunning():
            QMessageBox.information(self,'Task in progress','Please finish the current operation before starting another.')
            return
        for button in self.action_buttons: button.setEnabled(False)
        self.busybar.setRange(0,0);self.busybar.show()
        task=Task(fn);self.task=task
        task.progress.connect(self.status.setText)
        def success(value):
            if done: done(value)
            else: self.status.setText(str(value))
        task.succeeded.connect(success)
        task.failed.connect(lambda e: (self.status.setText('Error: '+e),QMessageBox.critical(self,'Operation failed',e)))
        def finish():
            for button in self.action_buttons: button.setEnabled(True)
            self.busybar.hide();self.task=None
        task.finished.connect(finish)
        task.start()

    def import_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'Select local photo folder')
        if not folder: return
        source,okay=QInputDialog.getText(self,'Import provenance (optional)',
            'Original website/source URL for this folder (leave blank if unknown):')
        if not okay: return
        self.task_start(lambda progress:db.scan_folder(self.db_path,Path(folder),source,progress),self.finish_import)

    def finish_import(self,result):
        self.reset_page()
        self.status.setText(f"Scan complete: {result['indexed']} indexed, {result['unchanged']} unchanged, {result['failed']} errors")
        if result['failed']:
            QMessageBox.warning(self,'Import warnings','\n'.join(result['examples']))

    def refresh_location_choices(self):
        previous=self.locations.currentData()
        with db.connect(self.db_path) as con:
            values=[r[0] for r in con.execute("SELECT DISTINCT location FROM photos WHERE location!='' ORDER BY location")]
        self.locations.blockSignals(True)
        self.locations.clear();self.locations.addItem('All locations','')
        for value in values: self.locations.addItem(value,value)
        idx=self.locations.findData(previous)
        self.locations.setCurrentIndex(max(0,idx));self.locations.blockSignals(False)

    def load_page(self):
        self.refresh_location_choices()
        with db.connect(self.db_path) as con:
            rows,total=db.query_photos(con,self.search.text().strip(),self.locations.currentData() or '',
                self.activities.currentData() or '',self.group_filter,self.offset,PAGE_SIZE)
        if self.offset and not rows and total:
            self.offset=max(0,((total-1)//PAGE_SIZE)*PAGE_SIZE)
            return self.load_page()
        self.total=total
        self.visible_rows={r['id']:dict(r) for r in rows}
        self.list.clear()
        for row in rows:
            path=Path(row['path'])
            try:
                tag_list = json.loads(row['activities'] or '[]')
            except (ValueError, TypeError):
                tag_list = []
            item_label = path.name[:23] + '\n' + (tag_list[0][:25] if tag_list else 'No activity tag')
            it=QListWidgetItem(item_label)
            it.setData(Qt.ItemDataRole.UserRole,row['id'])
            it.setToolTip('\n'.join([str(path),'Location: '+(row['location'] or 'Unknown'),
                'Activities: '+(', '.join(tag_list) if tag_list else 'Not identified'),
                'Attraction: '+(row['attraction'] or 'Unknown'),
                'AI status: '+(row['ai_source'] or 'Not tagged'),'Faces: '+str(row['face_count'])]))
            self.list.addItem(it)
        self.current_id=None
        self.photo_title.setText('Select an image')
        self.preview.clear();self.preview.setText('Photo preview')
        self.total_label.setText(f'{total:,} matching photos')
        self.page_label.setText(f"{self.offset+1 if total else 0}-{min(self.offset+PAGE_SIZE,total)} of {total:,}")
        self.prev.setEnabled(self.offset>0);self.next.setEnabled(self.offset+PAGE_SIZE<total)
        QTimer.singleShot(20,lambda:self.render_thumbs(0))

    def render_thumbs(self,index):
        # Throttle thumbnail generation so the UI has a chance to handle events.
        for n in range(index,min(index+5,self.list.count())):
            item=self.list.item(n)
            pid=item.data(Qt.ItemDataRole.UserRole)
            row=self.visible_rows.get(pid)
            if not row: continue
            try: item.setIcon(QIcon(str(self.thumbnail(row))))
            except Exception: pass
        if index+5<self.list.count():
            QTimer.singleShot(10,lambda:self.render_thumbs(index+5))

    def thumbnail(self,row):
        source=Path(row['path'])
        key=hashlib.sha1(f"{source}|{row['mtime']}".encode('utf-8')).hexdigest()
        thumb=self.thumb_dir/(key+'.jpg')
        if thumb.exists(): return thumb
        with Image.open(source) as im:
            img=ImageOps.exif_transpose(im).convert('RGB')
            img.thumbnail((180,140),Image.Resampling.LANCZOS)
            background=Image.new('RGB',(180,140),'#202A38')
            background.paste(img,((180-img.width)//2,(140-img.height)//2))
            background.save(thumb,'JPEG',quality=75)
        return thumb

    def select_photo(self):
        chosen=self.list.selectedItems()
        if not chosen: return
        pid=chosen[-1].data(Qt.ItemDataRole.UserRole)
        row=self.visible_rows.get(pid)
        if not row:return
        self.current_id=pid
        self.photo_title.setText(Path(row['path']).name)
        try:
            pix=QPixmap(row['path'])
            if pix.isNull():
                with Image.open(row['path']) as im:
                    img=ImageOps.exif_transpose(im).convert('RGB');img.thumbnail((900,650))
                    raw=img.tobytes('raw','RGB')
                    qimg=QImage(raw,img.width,img.height,img.width*3,QImage.Format.Format_RGB888)
                    pix=QPixmap.fromImage(qimg.copy())
            self.preview.setPixmap(pix.scaled(450,300,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        except Exception: self.preview.setText('Preview unavailable')
        gps=(f"{row['gps_lat']:.5f}, {row['gps_lon']:.5f}" if row['gps_lat'] is not None and row['gps_lon'] is not None else 'none')
        self.technical.setText(f"{row['width']} × {row['height']} px   |   Camera: {row['camera'] or 'unknown'}\n"
              f"GPS: {gps}   |   Location evidence: {row['location_source'] or 'none'}\n"
              f"Recognition: {row['ai_source'] or 'not tagged'}   |   Faces: {row['face_count']}")
        try: acts=', '.join(json.loads(row['activities']))
        except (TypeError,ValueError): acts=''
        for field,val in [('location',row['location']),('activity',acts),('attraction',row['attraction']),
                          ('source_url',row['source_url']),('artist',row['artist']),
                          ('copyright',row['copyright']),('license',row['license'])]:
            self.edits[field].setText(val or '')
        self.rights_status.setCurrentText(row['rights_status'] or 'Unknown')
        self.source_label.setText('Original source folder:\n'+row['source_folder']+'\nOriginal file path:\n'+row['original_path'])

    def save_details(self):
        if self.current_id is None: return
        values={k:e.text() for k,e in self.edits.items()}
        with db.connect(self.db_path) as con:
            db.update_metadata(con,self.current_id,location=values['location'],activity_text=values['activity'],
                attraction=values['attraction'],source_url=values['source_url'],artist=values['artist'],
                copyright=values['copyright'],license=values['license'])
        self.status.setText('Reviewed metadata saved. Manual tags are protected from future AI changes.')
        self.load_page()

    def selected_ids(self):
        ids=[it.data(Qt.ItemDataRole.UserRole) for it in self.list.selectedItems()]
        if not ids: QMessageBox.information(self,'Select photos','Select one or more photos in the Photo Library. Ctrl+A selects the visible page.')
        return ids

    def analyze_quality(self):
        if QMessageBox.question(self,'Analyze entire library',
            'Compute checksums and quality estimates for the indexed library? This reads files but does not move or delete anything.') != QMessageBox.StandardButton.Yes:return
        self.task_start(lambda p:analyze_library(self.db_path,progress=p),self.finish_quality)

    def finish_quality(self,result):
        self.reset_page()
        QMessageBox.information(self,'Analysis complete',
            f"Analyzed: {result['analyzed']} | Already indexed: {result['cached']} | Errors: {len(result['errors'])}")

    def show_duplicates(self):
        with db.connect(self.db_path) as con:
            dup=exact_duplicates(con)
            near=similar_pairs(con,limit=40)
        lines=[f"Exact duplicate sets: {len(dup)}; visually similar pairs (review manually): {len(near)}"]
        for group in dup[:10]:
            lines.append('EXACT: '+ ' | '.join(Path(x['path']).name for x in group))
        for item in near[:20]:
            lines.append(f"SIMILAR d={item['distance']}: {Path(item['photo_1']).name} ↔ {Path(item['photo_2']).name}")
        if not dup and not near:lines.append('No matches indexed. Run Scan quality first.')
        self.show_report('Duplicate review (no deletion)', '\n'.join(lines))

    def show_ai_reviews(self):
        with db.connect(self.db_path) as con:
            pending=review_pending(con)
        if not pending:
            QMessageBox.information(self,'AI review queue','No unreviewed AI suggestions.');return
        text='\n'.join(f"{Path(x['path']).name}: {x['activities']} | {x['attraction']}" for x in pending[:100])
        self.show_report(f'Unreviewed AI suggestions ({len(pending)})',text)

    def show_report(self,title,text):
        dialog=QDialog(self);dialog.setWindowTitle(title);dialog.resize(800,520)
        layout=QVBoxLayout(dialog);area=QTextEdit();area.setReadOnly(True)
        area.setPlainText(text);layout.addWidget(area)
        controls=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        controls.rejected.connect(dialog.accept);layout.addWidget(controls)
        dialog.exec()

    def tag_selected(self):
        ids=self.selected_ids()
        if not ids:return
        missing=local_ai_missing()
        if missing:
            self.refresh_ai_notice()
            QMessageBox.warning(self,'AI tagging needs installation',
                'AI tagging cannot run yet. Missing: '+', '.join(missing)+'\n\n'
                'Run INSTALL_AI_WINDOWS.bat, then restart the app.\n'
                'Use Test local AI to confirm the model works before tagging large batches.')
            return
        okay=QMessageBox.question(self,'Local visual AI',
            f'Classify {len(ids)} selected photos on this computer? '
            'The model weights download during the first use. '
            'Activities and exact landmarks are only suggestions, and uncertain photos may remain unclassified.')
        if okay!=QMessageBox.StandardButton.Yes:return
        self.task_start(lambda p:run_local(self.db_path,ids,p),self.finished_tags)

    def finished_tags(self,result):
        self.reset_page()
        if result.get('processed_ids'):
            first=result['processed_ids'][0]
            for n in range(self.list.count()):
                item=self.list.item(n)
                if item.data(Qt.ItemDataRole.UserRole)==first:
                    item.setSelected(True)
                    self.list.scrollToItem(item)
                    break
        summary=(f"Processed {result['tagged']} photos. "
                 f"Activities found: {result.get('with_activity',0)}; "
                 f"exact landmarks suggested: {result.get('with_attraction',0)}; "
                 f"uncertain: {result.get('unmatched',0)}; "
                 f"manual edits protected: {result['skipped']}; "
                 f"errors: {len(result['errors'])}.")
        self.status.setText(summary)
        details=('\n\nErrors:\n'+'\n'.join(result['errors'][:8])) if result['errors'] else ''
        if result['tagged'] == 0 and not result['errors']:
            details+='\nNo eligible images processed. Files with manually reviewed metadata are protected.'
        QMessageBox.information(self,'AI classification results',summary+details+ '\n\n'
            'Select a photo to review its proposed activities and attraction. '
            'Save reviewed metadata to protect it from future AI changes.')

    def get_models(self):
        if QMessageBox.question(self,'Face model download',
             'Download the official OpenCV YuNet and SFace models to local app storage (approx. 37 MB)? '
             'No photos or faces will be uploaded.')!=QMessageBox.StandardButton.Yes:return
        self.task_start(lambda p:download_models(self.model_dir,p),lambda result:self.status.setText(result))

    def scan_faces(self):
        with db.connect(self.db_path) as con:
            remaining=len(db.ids_unprocessed(con))
        if not remaining:
            QMessageBox.information(self,'Faces','All indexed photos have already been scanned for faces.')
            return
        if QMessageBox.question(self,'Group faces locally',f'Scan {remaining:,} unprocessed photos and group similar faces on this PC? '
             'This may take time on large collections and can make incorrect matches.')!=QMessageBox.StandardButton.Yes:return
        self.task_start(lambda p:group_faces(self.db_path,self.model_dir,p),self.finish_faces)

    def finish_faces(self,result):
        self.refresh_groups();self.reset_page()
        self.status.setText(f"Face scan: {result['scanned']:,} photos, {result['faces']:,} faces, {result['groups']:,} groups")
        if result['errors']:QMessageBox.warning(self,'Face scan warnings','\n'.join(result['errors']))

    def cloud_selected(self):
        ids=self.selected_ids()
        if not ids:return
        if len(ids)>50:
            QMessageBox.warning(self,'Batch too large','Cloud AI is limited to 50 selected photos per request to control cost.')
            return
        key,okay=QInputDialog.getText(self,'OpenAI API key (session only)',
            'API key is used for this operation only and is not saved:',QLineEdit.EchoMode.Password)
        if not okay or not key:return
        model,okay=QInputDialog.getText(self,'Cloud model','OpenAI vision-capable model:',text='gpt-4.1-mini')
        if not okay or not model.strip():return
        answer=QMessageBox.question(self,'Privacy and API charges',
            f'Upload {len(ids)} resized photos to OpenAI for classification? This sends image pixels to an external service '
            'and may incur API charges. Face embeddings will NOT be uploaded.')
        if answer!=QMessageBox.StandardButton.Yes:return
        self.task_start(lambda p:run_cloud(self.db_path,ids,key,model.strip(),p),self.finished_tags)

    def move_selected(self):
        ids=self.selected_ids()
        if not ids:return
        folder=QFileDialog.getExistingDirectory(self,'Choose ORGANIZED destination folder (may be on another drive)')
        if not folder:return
        try:plan=preview_moves(self.db_path,ids,Path(folder))
        except Exception as exc:QMessageBox.critical(self,'Cannot preview moves',str(exc));return
        if not plan:
            QMessageBox.information(self,'No moves','No eligible files found for these selections.');return
        dialog=ReviewDialog(plan,self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        self.task_start(lambda p:execute_moves(self.db_path,plan,p),self.finish_move)

    def finish_move(self,result):
        self.reset_page()
        self.status.setText(f"Moved {result['moved']} images. Errors: {len(result['errors'])}. Undo last moves is available.")
        if result['errors']:QMessageBox.warning(self,'Move warnings','\n'.join(result['errors']))

    def undo_moves(self):
        if QMessageBox.question(self,'Undo last move batch',
            'Restore the most recent move batch to its original paths? Existing files will never be overwritten.')!=QMessageBox.StandardButton.Yes:return
        self.task_start(lambda p:undo_last_batch(self.db_path,p),self.finish_undo)

    def finish_undo(self,result):
        self.reset_page()
        self.status.setText(f"Restored {result['restored']} files. Errors: {len(result['errors'])}")
        if result['errors']:QMessageBox.warning(self,'Undo warnings','\n'.join(result['errors']))

    def export_selected(self):
        ids=self.selected_ids()
        if not ids:return
        dlg=ExportDialog(self)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        folder=QFileDialog.getExistingDirectory(self,'Select export destination')
        if not folder:return
        values={'width':dlg.width.value(),'height':dlg.height.value(),
                'fmt':dlg.format.currentText(),'mode':dlg.mode.currentText(),'quality':dlg.quality.value(),
                'seo_names':dlg.seo_names.isChecked()}
        self.task_start(lambda p:export_photos(self.db_path,ids,Path(folder),progress=p,**values),self.finish_export)

    def finish_export(self,result):
        self.status.setText(f"Exported {result['exported']} photos to {result['destination']}. CSV manifest: {result['manifest']}")
        msg=f"Exported {result['exported']} photos.\n\nFolder: {result['destination']}\nManifest: {result['manifest']}"
        if result['errors']: msg+='\n\nErrors:\n'+'\n'.join(result['errors'][:8])
        QMessageBox.information(self,'Export complete',msg)

    def refresh_groups(self):
        with db.connect(self.db_path) as con: rows=db.groups(con)
        self.groups_table.setRowCount(len(rows))
        for n,row in enumerate(rows):
            vals=[str(row['id']),row['label'] or f'Person {row["id"]} (unnamed)',str(row['photos']),str(row['faces'])]
            for j,value in enumerate(vals):self.groups_table.setItem(n,j,QTableWidgetItem(value))

    def rename_group(self):
        idx=self.groups_table.currentRow()
        if idx<0:return
        gid=int(self.groups_table.item(idx,0).text())
        current=self.groups_table.item(idx,1).text()
        new,okay=QInputDialog.getText(self,'Rename face group','Optional person/group label:',text=current)
        if not okay:return
        with db.connect(self.db_path) as con:
            con.execute('UPDATE face_groups SET label=? WHERE id=?',(new.strip()[:100],gid))
            con.commit()
        self.refresh_groups()

    def open_group(self,index):
        row=index.row()
        self.group_filter=int(self.groups_table.item(row,0).text())
        self.tabs.setCurrentIndex(0)
        self.reset_page()
        self.status.setText(f'Browsing photos for face group #{self.group_filter}. Click Clear filters to return to all photos.')

    def reset_page(self):
        self.offset=0;self.load_page()

    def clear_filters(self):
        self.group_filter=None
        self.search.clear()
        self.locations.setCurrentIndex(0)
        self.activities.setCurrentIndex(0)
        self.tabs.setCurrentIndex(0)
        self.reset_page()

    def previous_page(self):
        self.offset=max(0,self.offset-PAGE_SIZE);self.load_page()
    def next_page(self):
        if self.offset+PAGE_SIZE<self.total:self.offset+=PAGE_SIZE;self.load_page()
