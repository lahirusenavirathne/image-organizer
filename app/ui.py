"""Windows-oriented Qt desktop UI. All long-running operations use worker threads."""
from __future__ import annotations
import hashlib
import json
from urllib.parse import urlsplit
from pathlib import Path
from typing import Callable
from . import web_sync, folder_sync
from .editor_ui import PhotoEditorDialog
from PySide6.QtCore import Qt, QThread, Signal, QSize, QTimer
from PySide6.QtGui import QIcon, QPixmap, QImage, QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QLineEdit, QTextEdit,
    QFileDialog, QMessageBox, QListWidget, QListWidgetItem, QListView, QComboBox,
    QVBoxLayout, QHBoxLayout, QFormLayout, QSplitter, QScrollArea, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QSpinBox, QDialog, QDialogButtonBox,
    QProgressBar, QGroupBox, QInputDialog, QAbstractItemView, QCheckBox,
    QFrame, QToolButton, QMenu, QTreeWidget, QTreeWidgetItem, QStyledItemDelegate
)
from PIL import Image, ImageOps
from . import db, drive
from .catalog import ACTIVITIES
from .operations import preview_moves, execute_moves, undo_last_batch, export_photos
from .faces import download_models, group_faces
from .recognition import run_local, run_cloud, local_ai_missing, test_local_model, format_local_report
from .library_tools import analyze_library, exact_duplicates, similar_pairs, set_rights
from .visual_search import (index_visuals, indexed_count, find_similar, set_reference,
                            match_reference_examples, apply_reference)
from .ai_cache import review_pending, review as review_ai
from .modern_widgets import STYLE, PhotoCardDelegate

PAGE_SIZE=120


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

class SimilarityDialog(QDialog):
    """Compare two photos before treating a visual match as a true match."""
    def __init__(self, original_path, results, parent=None, reference_mode=False):
        super().__init__(parent)
        self.results = results
        self.reference_mode = reference_mode
        self.setWindowTitle('Visual reference matches' if reference_mode else 'Visually similar photographs')
        self.resize(1050, 700)
        v = QVBoxLayout(self)
        note = QLabel('Scores are image similarity, not identification probabilities. '
                      'A visually similar image may be a different place. No originals are moved or deleted.')
        note.setWordWrap(True);v.addWidget(note)
        preview_row=QHBoxLayout()
        self.left_preview=QLabel('Selected photograph')
        self.right_preview=QLabel('Matching photograph')
        for label in (self.left_preview,self.right_preview):
            label.setMinimumHeight(210)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet('background:#0B1220;border:1px solid #344155;border-radius:8px;')
            preview_row.addWidget(label,1)
        v.addLayout(preview_row)
        self._preview(self.left_preview,original_path)
        self.table=QTableWidget(len(results),5)
        self.table.setHorizontalHeaderLabels(['Candidate photo','Relationship','Visual score','Hash distance','Trusted reference'])
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4,QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for row,m in enumerate(results):
            vals=[Path(m['path']).name,m['relationship'],
                  f"{m['cosine']:.3f}" if m['cosine'] is not None else 'Not indexed',
                  str(m['hash_distance']) if m['hash_distance'] is not None else '-',
                  (m.get('reference_kind') or '')+(': '+m['reference_label'] if m.get('reference_label') else '')]
            for col,value in enumerate(vals):
                item=QTableWidgetItem(value)
                item.setToolTip(m['path'])
                self.table.setItem(row,col,item)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        v.addWidget(self.table,1)
        self.selection_info=QLabel('Select a row to compare photographs.')
        self.selection_info.setWordWrap(True);v.addWidget(self.selection_info)
        buttons=QDialogButtonBox()
        if reference_mode:
            use=buttons.addButton('Apply selected reference label',QDialogButtonBox.ButtonRole.AcceptRole)
            use.setObjectName('Primary')
        buttons.addButton('Close',QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)
        if results:self.table.selectRow(0)

    def _preview(self,label,path):
        try:
            with Image.open(path) as opened:
                im=ImageOps.exif_transpose(opened).convert('RGB')
                im.thumbnail((480,240),Image.Resampling.LANCZOS)
                raw=im.tobytes('raw','RGB')
                qimg=QImage(raw,im.width,im.height,im.width*3,QImage.Format.Format_RGB888)
                pix=QPixmap.fromImage(qimg.copy())
                label.setPixmap(pix)
        except Exception as exc:
            label.setText('Preview not available: '+str(exc))

    def selection_changed(self):
        row=self.table.currentRow()
        if 0<=row<len(self.results):
            item=self.results[row]
            self._preview(self.right_preview,item['path'])
            self.selection_info.setText(item['path']+'\n'+item['relationship']+
                ' — Review both pictures; similarity does not prove the same attraction.')

    def selected_result(self):
        row=self.table.currentRow()
        return self.results[row] if 0<=row<len(self.results) else None


class FolderSyncSelectionDialog(QDialog):
    """An explicit list of eligible folders; no all-library sync switch."""
    def __init__(self, folders: list[dict], checked_ids: list[int], parent=None):
        super().__init__(parent)
        self.setWindowTitle('Choose local folders to sync')
        self.setMinimumSize(490,480)
        layout=QVBoxLayout(self)
        note=QLabel('Only checked folders and their subfolders can transfer in either direction. '
                    'Checking a parent includes its descendants. Photos in unselected '
                    'sibling folders or My Drive root will NOT be synced.\n\n'
                    'Up to 20 uploads/downloads per click. Nothing will be overwritten or deleted.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tree=QTreeWidget()
        self.tree.setHeaderLabels(['Local folders (choose individually)'])
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        layout.addWidget(self.tree,1)
        items={}
        for f in sorted(folders, key=lambda row:(len(row['path']),row['path'])):
            parent_item=items.get(f['parent_id'])
            item=QTreeWidgetItem(parent_item if parent_item is not None else self.tree,
                                 [f['name']])
            item.setData(0,Qt.ItemDataRole.UserRole,f['id'])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0,Qt.CheckState.Checked if f['id'] in checked_ids else Qt.CheckState.Unchecked)
            items[f['id']]=item
        self.tree.expandToDepth(1)
        self.folder_items=list(items.values())
        self.count_label=QLabel('Select one or more folders to continue')
        self.count_label.setObjectName('Subtle')
        layout.addWidget(self.count_label)
        self.tree.itemChanged.connect(self.update_count)
        self.update_count()
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Use selected folders')
        buttons.accepted.connect(self.validate_selection)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_ids(self) -> list[int]:
        return [int(item.data(0,Qt.ItemDataRole.UserRole)) for item in self.folder_items
                if item.checkState(0)==Qt.CheckState.Checked]

    def update_count(self, *args):
        self.count_label.setText(f'{len(self.selected_ids())} selected — no other folders will sync')

    def validate_selection(self):
        if not self.selected_ids():
            QMessageBox.warning(self,'Choose folders','Select at least one local folder. The full library cannot be synced from this action.')
            return
        self.accept()


class WebSyncDialog(QDialog):
    """Explicit device connection; a token never enters the photo database."""
    def __init__(self, endpoint='', token='', folder_id=0, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Connect to Guia Lanka Web Photo Manager')
        self.setMinimumWidth(540)
        layout=QVBoxLayout(self)
        lead=QLabel('Manual selected-folder transfer: Windows ↔ DreamHost.\n'
                    'No deletions, overwrites, or background synchronization in either direction.')
        lead.setWordWrap(True)
        layout.addWidget(lead)
        form=QFormLayout()
        self.site=QLineEdit(endpoint or 'https://photos.guialankatours.com')
        self.site.setPlaceholderText('https://photos.guialankatours.com')
        self.site.setToolTip('The HTTPS origin hosting your web photo manager')
        self.initial_site=self.site.text()
        self.site.textChanged.connect(self.clear_token_when_host_changes)
        form.addRow('Web app address',self.site)
        self.token=QLineEdit(token)
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText('glpm_v1_...  (create a write token on the web app)')
        form.addRow('Write API token',self.token)
        self.load_saved=QPushButton('Load saved token for this website')
        self.load_saved.clicked.connect(self.restore_token)
        form.addRow('',self.load_saved)
        self.remember=QCheckBox('Remember in Windows Credential Manager (recommended)')
        self.remember.setChecked(bool(token))
        form.addRow('',self.remember)
        self.folder=QSpinBox()
        self.folder.setRange(0,2147483647)
        self.folder.setValue(folder_id)
        self.folder.setToolTip('Web base folder for the selected desktop folder trees; 0 = My Drive root')
        form.addRow('Web destination parent ID',self.folder)
        layout.addLayout(form)
        explanation=QLabel('Create a read/write token in Web → Account → API tokens. '
                           'Only selected local folder trees sync in both directions, in batches of 20 files. Interrupted batches '
                           'can be resumed later, one whole photograph at a time. '
                           'If a different photo uses the same filename, the app skips it for review.')
        explanation.setWordWrap(True)
        explanation.setObjectName('Subtle')
        layout.addWidget(explanation)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                 QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Continue')
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def clear_token_when_host_changes(self):
        # Never carry a secret from the original host into an edited destination.
        old=urlsplit(self.initial_site).netloc.lower()
        new=urlsplit(self.site.text()).netloc.lower()
        if new!=old:
            self.token.clear()
            self.remember.setChecked(False)

    def restore_token(self):
        try:
            secret=web_sync.saved_token(self.site.text())
            if not secret: raise ValueError('No stored token for this website.')
            self.token.setText(secret)
        except ValueError as exc:
            QMessageBox.information(self,'Saved API token',str(exc))

    def validate_and_accept(self):
        try:
            web_sync.api_url(self.site.text())
            web_sync.validate_token(self.token.text())
            self.accept()
        except ValueError as exc:
            QMessageBox.warning(self,'Connection settings',str(exc))


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
        self.drive_view='all'
        self.active_folder_id=None
        self.view_mode='grid'
        self.visible_rows={}
        self.current_id=None
        self.task=None
        self.web_sync_session_token=''
        self.action_buttons=[]
        self.setWindowTitle('Guia Lanka Photo Manager  |  Photo Library')
        self.resize(1500,930)
        self.setMinimumSize(1040,700)
        self.setStyleSheet(STYLE)
        self.build_ui()
        self.refresh_folder_tree()
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
        # Navigation is a persistent left-hand rail, not a row of 20 tiny buttons.
        root = QWidget()
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName('Sidebar')
        sidebar.setFixedWidth(210)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(15, 21, 15, 18)
        side.setSpacing(6)
        brand = QLabel('◉  GUIA LANKA')
        brand.setObjectName('Brand')
        side.addWidget(brand)
        edition = QLabel('PHOTO MANAGER  /  LOCAL LIBRARY')
        edition.setObjectName('Tiny')
        edition.setWordWrap(True)
        side.addWidget(edition)
        side.addSpacing(30)
        section = QLabel('LIBRARY')
        section.setObjectName('Tiny')
        side.addWidget(section)
        side.addSpacing(5)
        self.nav_buttons = {}
        for key, text in [
            ('all', '▦    All photos'),
            ('drive', '▣    My Drive'),
            ('recent', '◷    Recent'),
            ('starred', '★    Starred'),
            ('trash', '♻    Trash'),
            ('locations', '⌖    Locations'),
            ('activities', '◈    Activities'),
            ('people', '♙    People'),
            ('review', '◇    Review tags'),
            ('exports', '⇩    Exports')]:
            button = QPushButton(text)
            button.setObjectName('NavButton')
            button.setProperty('active', key == 'all')
            button.setMinimumHeight(40)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, name=key: self.navigate(name))
            side.addWidget(button)
            self.nav_buttons[key] = button
        side.addSpacing(12)
        folder_title=QLabel('MY FOLDERS')
        folder_title.setObjectName('Tiny')
        side.addWidget(folder_title)
        self.folder_tree=QTreeWidget()
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.setMinimumHeight(130)
        self.folder_tree.setMaximumHeight(280)
        self.folder_tree.itemClicked.connect(self.on_folder_selected)
        side.addWidget(self.folder_tree,1)
        new_folder=QPushButton('+ New folder')
        new_folder.clicked.connect(self.new_drive_folder)
        side.addWidget(new_folder)
        side.addStretch()
        side.addWidget(QLabel('ORGANIZE SAFELY'))
        helper = QLabel('Local photo library\nNo automatic file moves\nUnknown rights stay unknown')
        helper.setObjectName('Subtle')
        helper.setWordWrap(True)
        side.addWidget(helper)
        shell.addWidget(sidebar)

        workspace = QWidget()
        workspace.setObjectName('Workspace')
        shell.addWidget(workspace, 1)
        main = QVBoxLayout(workspace)
        main.setContentsMargins(22, 21, 22, 12)
        main.setSpacing(13)
        heading = QHBoxLayout()
        heading_text = QVBoxLayout()
        heading_text.setSpacing(3)
        self.heading_title = QLabel('Photo Library')
        self.heading_title.setObjectName('Headline')
        heading_text.addWidget(self.heading_title)
        self.heading_description = QLabel('Find, review and organize your Sri Lankan travel photography')
        self.heading_description.setObjectName('Subtle')
        heading_text.addWidget(self.heading_description)
        heading.addLayout(heading_text, 1)
        self.total_label = QLabel('0 photos indexed')
        self.total_label.setObjectName('Count')
        heading.addWidget(self.total_label)
        self.add_action(heading, '+  Add photos', self.import_folder, True)
        main.addLayout(heading)

        toolbar = QFrame()
        toolbar.setObjectName('Toolbar')
        toolbar_row = QHBoxLayout(toolbar)
        toolbar_row.setContentsMargins(12, 10, 12, 10)
        toolbar_row.setSpacing(8)
        self.search = QLineEdit()
        self.search.setObjectName('SearchInput')
        self.search.setPlaceholderText('Search elephants in Yala, filenames, locations, attractions...')
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumHeight(39)
        self.search.returnPressed.connect(self.reset_page)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(320)
        self.search_timer.timeout.connect(self.reset_page)
        self.search.textChanged.connect(lambda _value: self.search_timer.start())
        toolbar_row.addWidget(self.search, 1)
        self.filter_toggle = QToolButton()
        self.filter_toggle.setText('☷  Filters')
        self.filter_toggle.setCheckable(True)
        self.filter_toggle.toggled.connect(self.toggle_filters)
        self.filter_toggle.setToolTip('Filter by location and activity')
        toolbar_row.addWidget(self.filter_toggle)
        self.add_action(toolbar_row, 'AI tag', self.tag_selected)
        self.add_action(toolbar_row, 'Find similar', self.find_similar_selected)
        self.add_action(toolbar_row, 'Edit photo', self.edit_selected_photo)
        self.add_action(toolbar_row, 'Export selected', self.export_selected, True)
        more = QToolButton()
        more.setText('More ▾')
        more.setToolTip('Additional recognition and organization tools')
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_menu = QMenu(more)
        more.setMenu(self.more_menu)
        self._build_more_menu()
        toolbar_row.addWidget(more)
        main.addWidget(toolbar)

        self.filter_panel = QFrame()
        self.filter_panel.setObjectName('FilterPanel')
        filter_row = QHBoxLayout(self.filter_panel)
        filter_row.setContentsMargins(12, 11, 12, 11)
        filter_row.setSpacing(11)
        filter_row.addWidget(QLabel('Location'))
        self.locations = QComboBox()
        self.locations.setMinimumWidth(190)
        self.locations.addItem('All locations', '')
        self.locations.currentIndexChanged.connect(self.reset_page)
        filter_row.addWidget(self.locations)
        filter_row.addWidget(QLabel('Activity'))
        self.activities = QComboBox()
        self.activities.setMinimumWidth(200)
        self.activities.addItem('All activities', '')
        for name in ACTIVITIES:
            self.activities.addItem(name, name)
        self.activities.currentIndexChanged.connect(self.reset_page)
        filter_row.addWidget(self.activities)
        self.add_action(filter_row, 'Clear filters', self.clear_filters)
        filter_row.addStretch()
        self.filter_panel.hide()
        main.addWidget(self.filter_panel)

        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        self.tabs.setDocumentMode(True)
        main.addWidget(self.tabs, 1)
        photos = QWidget()
        photos.setObjectName('PhotoArea')
        self.tabs.addTab(photos, 'Photo Library')
        photo_layout = QVBoxLayout(photos)
        photo_layout.setContentsMargins(0, 0, 0, 0)
        photo_layout.setSpacing(8)
        # Virtual folder controls never move external original files.
        folder_nav=QHBoxLayout()
        self.up_folder=QPushButton('↑ Up')
        self.up_folder.clicked.connect(self.go_up_folder)
        self.folder_breadcrumb=QLabel('My Drive')
        self.folder_breadcrumb.setObjectName('Subtle')
        folder_nav.addWidget(self.up_folder)
        folder_nav.addWidget(self.folder_breadcrumb,1)
        photo_layout.addLayout(folder_nav)
        self.folder_buttons=QHBoxLayout()
        photo_layout.addLayout(self.folder_buttons)
        gallery_info = QHBoxLayout()
        self.gallery_title = QLabel('All photographs')
        self.gallery_title.setObjectName('SectionTitle')
        gallery_info.addWidget(self.gallery_title)
        self.selection_label = QLabel('Select photos to classify, compare or export')
        self.selection_label.setObjectName('Subtle')
        gallery_info.addWidget(self.selection_label)
        gallery_info.addStretch()
        self.sort_by=QComboBox()
        self.sort_by.addItem('Newest', 'newest')
        self.sort_by.addItem('Oldest', 'oldest')
        self.sort_by.addItem('Name', 'name')
        self.sort_by.addItem('Largest', 'size')
        self.sort_by.currentIndexChanged.connect(self.reset_page)
        gallery_info.addWidget(self.sort_by)
        self.view_toggle=QToolButton()
        self.view_toggle.setText('☷ List')
        self.view_toggle.setCheckable(True)
        self.view_toggle.toggled.connect(self.toggle_list_view)
        gallery_info.addWidget(self.view_toggle)
        compact = QToolButton()
        compact.setText('⊞  Compact')
        compact.setToolTip('Toggle smaller photo cards')
        compact.setCheckable(True)
        compact.toggled.connect(self.toggle_grid_density)
        gallery_info.addWidget(compact)
        photo_layout.addLayout(gallery_info)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        left = QWidget()
        left_v = QVBoxLayout(left)
        left_v.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.setObjectName('PhotoGrid')
        self.list.setItemDelegate(PhotoCardDelegate(self.list))
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setFlow(QListView.Flow.LeftToRight)
        self.list.setWrapping(True)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setIconSize(QSize(230, 146))
        self.list.setGridSize(QSize(252, 234))
        self.list.setSpacing(2)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.itemSelectionChanged.connect(self.select_photo)
        self.list.itemDoubleClicked.connect(self.show_full_image)
        self.list.setAccessibleName('Photo grid')
        left_v.addWidget(self.list, 1)
        self.empty_label = QLabel('No photographs in this view.\nClick + Add photos to import a local folder.')
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setObjectName('Subtle')
        self.empty_label.hide()
        left_v.addWidget(self.empty_label)
        paging = QHBoxLayout()
        self.prev = QPushButton('← Previous')
        self.next = QPushButton('Next →')
        self.prev.clicked.connect(self.previous_page)
        self.next.clicked.connect(self.next_page)
        self.page_label = QLabel('0 of 0')
        self.page_label.setObjectName('Subtle')
        paging.addWidget(self.prev)
        paging.addWidget(self.next)
        paging.addWidget(self.page_label)
        paging.addStretch()
        hint = QLabel('Ctrl+A: select visible page • Double-click: enlarge')
        hint.setObjectName('Tiny')
        paging.addWidget(hint)
        left_v.addLayout(paging)
        self.splitter.addWidget(left)

        self.inspector = QScrollArea()
        self.inspector.setWidgetResizable(True)
        self.inspector.setMinimumWidth(285)
        self.inspector.setMaximumWidth(420)
        panel = QWidget()
        panel.setObjectName('Inspector')
        panel_v = QVBoxLayout(panel)
        panel_v.setContentsMargins(15, 13, 15, 16)
        panel_v.setSpacing(10)
        inspector_heading = QHBoxLayout()
        title = QLabel('PHOTO DETAILS')
        title.setObjectName('SectionTitle')
        inspector_heading.addWidget(title)
        inspector_heading.addStretch()
        close_inspector = QToolButton()
        close_inspector.setText('✕')
        close_inspector.setToolTip('Close photo details')
        close_inspector.clicked.connect(self.close_inspector)
        inspector_heading.addWidget(close_inspector)
        panel_v.addLayout(inspector_heading)
        self.photo_title = QLabel('Select an image')
        self.photo_title.setWordWrap(True)
        panel_v.addWidget(self.photo_title)
        self.preview = QLabel('Photo preview')
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(210)
        self.preview.setStyleSheet('background:#EEF2F4; border:1px solid #DEE8EB; border-radius:10px;')
        panel_v.addWidget(self.preview)
        self.technical = QLabel('')
        self.technical.setObjectName('Subtle')
        self.technical.setWordWrap(True)
        panel_v.addWidget(self.technical)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setSpacing(8)
        self.edits = {}
        for field, label in [('location', 'Location'), ('activity', 'Activities'), ('attraction', 'Attraction'),
                             ('source_url', 'Source URL'), ('artist', 'Photographer'),
                             ('copyright', 'Copyright'), ('license', 'Usage rights')]:
            edit = QLineEdit()
            edit.setPlaceholderText(label)
            self.edits[field] = edit
            form.addRow(label, edit)
        self.rights_status = QComboBox()
        self.rights_status.addItems(['Unknown', 'Verified', 'Permission required'])
        form.addRow('Rights status', self.rights_status)
        panel_v.addLayout(form)
        self.add_action(panel_v, 'Save reviewed metadata', self.save_details, True)
        self.source_label = QLabel('Original source folder:')
        self.source_label.setObjectName('Subtle')
        self.source_label.setWordWrap(True)
        panel_v.addWidget(self.source_label)
        panel_v.addStretch()
        self.inspector.setWidget(panel)
        self.splitter.addWidget(self.inspector)
        self.splitter.setSizes([920, 335])
        self.inspector.hide()  # Photo grid fills the canvas until a photo is selected.
        photo_layout.addWidget(self.splitter, 1)

        people = QWidget()
        self.tabs.addTab(people, 'People / Face Groups')
        people_v = QVBoxLayout(people)
        people_v.setContentsMargins(0, 0, 0, 0)
        intro = QLabel('Faces stay on this computer. Groups are suggestions, not verified identities. Double-click a group to browse.')
        intro.setObjectName('Subtle')
        intro.setWordWrap(True)
        people_v.addWidget(intro)
        person_buttons = QHBoxLayout()
        self.add_action(person_buttons, 'Refresh face groups', self.refresh_groups)
        self.add_action(person_buttons, 'Rename selected group', self.rename_group)
        self.add_action(person_buttons, 'Show all photos', self.clear_filters)
        person_buttons.addStretch()
        people_v.addLayout(person_buttons)
        self.groups_table = QTableWidget(0, 4)
        self.groups_table.setHorizontalHeaderLabels(['Group ID', 'Name / label', 'Number of photos', 'Faces'])
        self.groups_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.groups_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.groups_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.groups_table.doubleClicked.connect(self.open_group)
        people_v.addWidget(self.groups_table, 1)

        footer = QHBoxLayout()
        self.status = QLabel('Ready. Import a photo folder to get started.')
        self.status.setObjectName('Subtle')
        footer.addWidget(self.status, 1)
        self.ai_notice = QLabel()
        self.ai_notice.setObjectName('Tiny')
        self.ai_notice.setMaximumWidth(330)
        footer.addWidget(self.ai_notice)
        self.refresh_ai_notice()
        self.busybar = QProgressBar()
        self.busybar.setMaximumWidth(170)
        self.busybar.hide()
        footer.addWidget(self.busybar)
        main.addLayout(footer)
        self.shortcuts = []
        for key, callback in [('Ctrl+F', self.search.setFocus),
                              ('Ctrl+I', self.import_folder),
                              ('Ctrl+E', self.export_selected)]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)

    def _build_more_menu(self):
        def entry(label, callback):
            action = self.more_menu.addAction(label)
            action.triggered.connect(callback)
            self.action_buttons.append(action)
            return action
        self.more_menu.addSection('AI RECOGNITION')
        entry('Refresh AI selected (ignore cache)', self.refresh_ai_selected)
        entry('Test local AI model', self.test_local_ai)
        entry('Cloud AI selected (opt-in)', self.cloud_selected)
        entry('Review AI tag suggestions', self.show_ai_reviews)
        self.more_menu.addSeparator()
        self.more_menu.addSection('VISUAL MATCHING')
        entry('Index selected images', self.index_visual_selection)
        entry('Index whole library', self.index_visual_matches)
        entry('Save selected photo as reference', self.save_visual_reference)
        entry('Match reference examples', self.find_reference_selected)
        self.more_menu.addSeparator()
        self.more_menu.addSection('ORGANIZE & QUALITY')
        self.more_menu.addSection('MY DRIVE — VIRTUAL FOLDERS')
        entry('New folder', self.new_drive_folder)
        entry('Rename current folder', self.rename_drive_folder)
        entry('Move current folder', self.move_drive_folder)
        entry('Move current folder to Trash', self.trash_drive_folder)
        entry('Rename selected photo (display name)', self.rename_drive_photo)
        entry('Move selected photos to folder', self.move_to_drive_folder)
        entry('Make local copies in folder', self.copy_to_drive_folder)
        entry('Star / unstar selected photos', self.star_drive_photos)
        entry('Move selected photos to Trash', self.trash_drive_photos)
        entry('Restore selected photos from Trash', self.restore_drive_photos)
        entry('Remove selected catalog records from Trash', self.purge_drive_photos)
        entry('Remove trashed folder from catalog', self.purge_drive_folder)
        entry('Save untouched originals to folder', self.download_originals)
        entry('Edit selected photograph (non-destructive)', self.edit_selected_photo)
        self.more_menu.addSeparator()
        self.more_menu.addSection('DREAMHOST WEB API — SELECTED FOLDERS')
        entry('Test web API connection', self.test_web_connection)
        entry('Sync selected folders (Windows ↔ Web)', self.sync_web_selected_folders)
        entry('Continue selected-folder sync', self.resume_selected_folder_sync)
        entry('Forget stored web API token', self.forget_web_token)
        self.more_menu.addSeparator()
        self.more_menu.addSection('ADVANCED FILE OPERATIONS')
        entry('Review and move selected photos', self.move_selected)
        entry('Undo last move batch', self.undo_moves)
        entry('Scan image quality', self.analyze_quality)
        entry('Review duplicates', self.show_duplicates)
        self.more_menu.addSeparator()
        self.more_menu.addSection('FACES (LOCAL ONLY)')
        entry('Download face models', self.get_models)
        entry('Group faces', self.scan_faces)

    def _set_nav_active(self, key):
        for name, button in self.nav_buttons.items():
            button.setProperty('active', name == key)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def navigate(self, key):
        if key in ('all','drive','recent','starred','trash'):
            self.drive_view=key
            self.active_folder_id=None
            self.group_filter=None
            self.tabs.setCurrentIndex(0)
            self._set_nav_active(key)
            self.reset_page()
            return
        self.drive_view='all'
        self.active_folder_id=None
        self._set_nav_active(key)
        if key == 'people':
            self.heading_title.setText('People & Face Groups')
            self.heading_description.setText('Review locally grouped faces; names are optional')
            self.tabs.setCurrentIndex(1)
            self.refresh_groups()
            return
        self.tabs.setCurrentIndex(0)
        headings = {
            'all': ('Photo Library', 'Find, review and organize your Sri Lankan travel photography'),
            'locations': ('Locations', 'Browse destinations from GPS, metadata and reviewed tags'),
            'activities': ('Activities', 'Explore safaris, village visits, beaches, trekking and more'),
            'review': ('Review AI suggestions', 'Check uncertain AI tags before organizing photos'),
            'exports': ('Export Photos', 'Choose images and export to WebP, JPEG, PNG or TIFF'),
        }
        title, description = headings.get(key, headings['all'])
        self.heading_title.setText(title)
        self.heading_description.setText(description)
        self.gallery_title.setText('Photographs' if key != 'all' else 'All photographs')
        if key in ('locations', 'activities'):
            self.filter_toggle.setChecked(True)
            (self.locations if key == 'locations' else self.activities).setFocus()
        elif key == 'review':
            self.show_ai_reviews()
        elif key == 'exports':
            self.status.setText('Select one or more photographs, then click Export selected.')

    def toggle_filters(self, checked):
        self.filter_panel.setVisible(bool(checked))

    def toggle_list_view(self, checked):
        self.view_mode='list' if checked else 'grid'
        self.list.setUpdatesEnabled(False)
        if checked:
            self.list.setItemDelegate(QStyledItemDelegate(self.list))
            self.list.setViewMode(QListView.ViewMode.ListMode)
            self.list.setGridSize(QSize())
            self.list.setIconSize(QSize(90,65))
            self.list.setWrapping(False)
            self.view_toggle.setText('▦ Grid')
        else:
            self.list.setItemDelegate(PhotoCardDelegate(self.list))
            self.list.setViewMode(QListView.ViewMode.IconMode)
            self.list.setWrapping(True)
            self.list.setGridSize(QSize(252,234))
            self.list.setIconSize(QSize(230,146))
            self.view_toggle.setText('☷ List')
        self.list.setUpdatesEnabled(True)
        self.list.viewport().update()

    def toggle_grid_density(self, compact):
        if self.view_mode=='list':return
        if compact:
            self.list.setIconSize(QSize(180, 120))
            self.list.setGridSize(QSize(205, 208))
        else:
            self.list.setIconSize(QSize(230, 146))
            self.list.setGridSize(QSize(252, 234))
        self.list.viewport().update()

    def close_inspector(self):
        self.inspector.hide()
        self.list.clearSelection()
        self.current_id = None

    def show_full_image(self, item):
        row = self.visible_rows.get(item.data(Qt.ItemDataRole.UserRole))
        if not row: return
        dialog = QDialog(self)
        dialog.setWindowTitle(Path(row['path']).name)
        dialog.resize(1050, 780)
        layout = QVBoxLayout(dialog)
        preview = QLabel()
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        with Image.open(row['path']) as source:
            picture = ImageOps.exif_transpose(source).convert('RGB')
            picture.thumbnail((1500, 1100), Image.Resampling.LANCZOS)
            qimage = QImage(picture.tobytes(), picture.width, picture.height,
                            picture.width * 3, QImage.Format.Format_RGB888).copy()
        preview.setPixmap(QPixmap.fromImage(qimage).scaled(
            1000, 720, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(preview)
        close = QPushButton('Close preview')
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

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
        destination=self.active_folder_id if self.drive_view in ('drive','folder') else None
        self.task_start(lambda progress:drive.import_tree(self.db_path,Path(folder),destination,source,progress),self.finish_import)

    def finish_import(self,result):
        self.refresh_folder_tree()
        self.navigate('all')
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
            rows, total = drive.query_photos(con, self.search.text().strip(),
                self.locations.currentData() or '', self.activities.currentData() or '',
                self.group_filter, self.offset, PAGE_SIZE, view=self.drive_view,
                folder_id=self.active_folder_id, sort=self.sort_by.currentData() or 'newest')
        self.refresh_folder_strip()
        if self.offset and not rows and total:
            self.offset = max(0, ((total - 1) // PAGE_SIZE) * PAGE_SIZE)
            return self.load_page()
        self.total = total
        self.visible_rows = {r['id']: dict(r) for r in rows}
        self.list.blockSignals(True)
        self.list.clear()
        for row in rows:
            path = Path(row['path'])
            try:
                tags = json.loads(row['activities'] or '[]')
            except (ValueError, TypeError):
                tags = []
            display=row['display_name'] or path.name
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, row['id'])
            item.setData(Qt.ItemDataRole.UserRole + 1, display)
            item.setData(Qt.ItemDataRole.UserRole + 2,
                row['location'] or row['attraction'] or (tags[0] if tags else 'Unclassified'))
            item.setData(Qt.ItemDataRole.UserRole + 3, 'AI tagged' if row['ai_source'] and row['ai_source'] != 'Manual' else '')
            item.setToolTip('\n'.join([str(path),
                'Location: ' + (row['location'] or 'Unknown'),
                'Activities: ' + (', '.join(tags) if tags else 'Not identified'),
                'Attraction: ' + (row['attraction'] or 'Unknown'),
                'AI status: ' + (row['ai_source'] or 'Not tagged')]))
            self.list.addItem(item)
        self.list.blockSignals(False)
        self.current_id = None
        self.inspector.hide()
        self.photo_title.setText('Select an image')
        self.preview.clear()
        self.preview.setText('Photo preview')
        self.total_label.setText(f'{total:,} photos in this view')
        self.gallery_title.setText({'all':'All photographs','drive':'My Drive','folder':'Current folder',
                                    'recent':'Recent photographs','starred':'Starred photographs','trash':'Trash'}.get(self.drive_view,'Photographs'))
        self.selection_label.setText('Select photos to classify, compare or export')
        self.page_label.setText(f'{self.offset+1 if total else 0}–{min(self.offset+PAGE_SIZE,total)} of {total:,}')
        self.prev.setEnabled(self.offset > 0)
        self.next.setEnabled(self.offset + PAGE_SIZE < total)
        self.empty_label.setVisible(total == 0)
        QTimer.singleShot(20, lambda: self.render_thumbs(0))

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

    def thumbnail(self, row):
        source = Path(row['path'])
        key = hashlib.sha1(f"card-v2|{source}|{row['mtime']}".encode('utf-8')).hexdigest()
        thumb = self.thumb_dir / (key + '.jpg')
        if thumb.exists():
            return thumb
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert('RGB')
            # Cropping is thumbnail-only; the original photograph is untouched.
            image = ImageOps.fit(image, (230, 146), method=Image.Resampling.LANCZOS)
            image.save(thumb, 'JPEG', quality=83)
        return thumb

    def select_photo(self):
        chosen=self.list.selectedItems()
        if not chosen: return
        pid=chosen[-1].data(Qt.ItemDataRole.UserRole)
        row=self.visible_rows.get(pid)
        if not row:return
        self.current_id=pid
        self.inspector.show()
        self.splitter.setSizes([920, 340])
        count = len(chosen)
        self.selection_label.setText(f'{count} selected')
        self.photo_title.setText(row['display_name'] or Path(row['path']).name)
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
            set_rights(con, self.current_id, self.rights_status.currentText())
        self.status.setText('Reviewed metadata saved. Manual tags are protected from future AI changes.')
        self.load_page()

    def _web_settings_path(self):
        return self.app_dir/'web_connection.json'

    def _web_settings(self):
        try:
            data=json.loads(self._web_settings_path().read_text(encoding='utf-8'))
            return {'endpoint':str(data.get('endpoint','https://photos.guialankatours.com')),
                    'folder_id':max(0,int(data.get('folder_id',0))),
                    'selected_folder_ids':[int(i) for i in data.get('selected_folder_ids',[])
                                           if type(i) is int and i>0][:100]}
        except (OSError,ValueError,TypeError):
            return {'endpoint':'https://photos.guialankatours.com','folder_id':0,'selected_folder_ids':[]}

    def _web_client_settings(self):
        settings=self._web_settings()
        token=self.web_sync_session_token or web_sync.saved_token(settings['endpoint'])
        dialog=WebSyncDialog(settings['endpoint'],token,settings['folder_id'],self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return None
        endpoint=web_sync.api_url(dialog.site.text())
        token=web_sync.validate_token(dialog.token.text())
        target=int(dialog.folder.value())
        # Config holds no secrets. Credentials are stored only on explicit consent.
        config=json.dumps({'endpoint':endpoint,'folder_id':target,
                           'selected_folder_ids':settings.get('selected_folder_ids',[])},indent=2)
        path=self._web_settings_path();temp=path.with_suffix('.tmp')
        temp.write_text(config,encoding='utf-8');temp.replace(path)
        if dialog.remember.isChecked():
            try:web_sync.remember_token(endpoint,token)
            except web_sync.SyncError as exc:
                QMessageBox.warning(self,'Secure token storage',str(exc)+'\nYou can still use this token until the app closes.')
        self.web_sync_session_token=token
        return endpoint,token,target

    def test_web_connection(self):
        settings=self._web_client_settings()
        if settings is None:return
        endpoint,token,_=settings
        def finished(result):
            QMessageBox.information(self,'Web API connection successful',
                f"Signed in as: {result.get('email','')}\n"
                f"Role: {result.get('role','')}  |  Token scope: {result.get('scope','')}\n"
                'This confirms API access only; no photos were transferred.')
        self.task_start(lambda progress:web_sync.ApiClient(endpoint,token).me(),finished)

    def sync_web_selected_folders(self):
        all_local=folder_sync.available_folders(self.db_path)
        if not all_local:
            QMessageBox.information(self,'No folders',
                'Import a photo folder first, or create folders in My Drive. Root-level photos are not included.')
            return
        settings=self._web_settings()
        stored=settings['selected_folder_ids']
        dialog=FolderSyncSelectionDialog(all_local,stored,self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        chosen=dialog.selected_ids()
        try:
            plan=folder_sync.folder_selection(self.db_path,chosen)
        except ValueError as exc:
            QMessageBox.warning(self,'Selected folders',str(exc));return
        connection=self._web_client_settings()
        if connection is None:return
        endpoint,token,base_id=connection
        root_names=['/'.join(f['path']) for f in plan['roots']]
        if QMessageBox.question(self,'Confirm selected-folder sync',
                'Sync ONLY these local folders (including their descendants):\n\n'
                +'\n'.join('• '+name for name in root_names[:12])
                +(f'\n...and {len(root_names)-12} more' if len(root_names)>12 else '')
                +f'\n\n{plan["photo_count"]} eligible photos. Up to 20 per run.\n'
                +'Unselected folders and root-level photos are excluded.\n'
                +'Only missing photo metadata is filled, with conflicts kept for review.\n'
                +'Existing files on either side will never be overwritten or deleted. Continue?') \
                !=QMessageBox.StandardButton.Yes:return
        saved=self._web_settings()
        saved['selected_folder_ids']=chosen
        self._save_web_settings(saved)
        self._start_folder_sync(endpoint,token,base_id,chosen)

    def _save_web_settings(self,values):
        # Server endpoint, base destination and checked folder IDs are not secrets.
        path=self._web_settings_path();temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(values,indent=2),encoding='utf-8')
        temporary.replace(path)

    def resume_selected_folder_sync(self):
        settings=self._web_settings()
        ids=settings.get('selected_folder_ids',[])
        if not ids:
            QMessageBox.information(self,'No selected folders',
                'Use “Choose folders and sync to web” first. No folders are synced by default.')
            return
        try:plan=folder_sync.folder_selection(self.db_path,ids)
        except ValueError as exc:
            QMessageBox.warning(self,'Review selected folders',str(exc));return
        connection=self._web_client_settings()
        if connection is None:return
        endpoint,token,base_id=connection
        if QMessageBox.question(self,'Continue selected-folder sync',
                f'Continue syncing ONLY the {len(plan["roots"])} previously selected folders?\n'
                'Up to 20 transfers in this batch. No deletions or overwrites.')!=QMessageBox.StandardButton.Yes:
            return
        self._start_folder_sync(endpoint,token,base_id,ids)

    def _start_folder_sync(self,endpoint,token,base_id,selected_folder_ids):
        def work(progress):
            client=web_sync.ApiClient(endpoint,token)
            return folder_sync.sync_selected_folder_trees(self.db_path,client,
                selected_ids=selected_folder_ids,remote_parent_id=base_id,progress=progress)
        def finish(result):
            message=('Selected folder roots: {selected_folders}\n'
                     'Eligible photos: {in_scope_photos}\n'
                     'Uploaded in this batch: {uploaded}\nAlready on web: {already_on_web}\n'
                     'Previously uploaded (unchanged): {previously_completed}\n'
                     'Previously reported conflicts: {previous_conflicts}\n'
                     'Filename conflicts: {conflicts}\nFailed uploads: {failed}\n'
                     'Downloaded from web: {downloaded}\n'
                     'Web download conflicts: {download_conflicts}\n'
                     'Failed downloads: {download_failed}\n'
                     'New web folders: {remote_folders_created}\n'
                     'Metadata matches checked: {metadata_pairs}\n'
                     'Metadata filled on web: {metadata_web_updated}\n'
                     'Metadata filled on Windows: {metadata_local_updated}\n'
                     'Metadata conflicts for review: {metadata_conflicts}\n'
                     'Metadata failures: {metadata_failed}').format(**result)
            if result['more_may_remain']:
                message+='\n\nMore selected-folder photos may remain. Use “Continue selected-folder sync” again.'
            if result['examples']:message+='\n\n'+'\n'.join(result['examples'])
            message+='\n\nExisting metadata is preserved; only empty fields are filled. No originals were replaced or deleted.'
            QMessageBox.information(self,'Selected-folder sync completed',message)
            self.status.setText('Selected-folder sync: '+str(result['uploaded'])+' uploaded')
        self.task_start(work,finish)

    def forget_web_token(self):
        settings=self._web_settings()
        if QMessageBox.question(self,'Forget stored web API token',
                'Remove this website API token from Windows Credential Manager?\n'
                'You can also revoke it immediately in the web app.')!=QMessageBox.StandardButton.Yes:
            return
        web_sync.forget_token(settings['endpoint'])
        self.web_sync_session_token=''
        self.status.setText('Saved web API token removed from this device.')

    def selected_ids(self):
        ids=[it.data(Qt.ItemDataRole.UserRole) for it in self.list.selectedItems()]
        if not ids: QMessageBox.information(self,'Select photos','Select one or more photos in the Photo Library. Ctrl+A selects the visible page.')
        return ids

    def _one_visual_id(self):
        ids=self.selected_ids()
        if len(ids)!=1:
            if ids:
                QMessageBox.information(self,'Select one photo','Select exactly one photograph as the search example.')
            return None
        return ids[0]

    def index_visual_selection(self):
        ids=self.selected_ids()
        if not ids:return
        if QMessageBox.question(self,'Index selected visual matches',
                f'Compute local visual fingerprints for {len(ids)} selected photos?\n'
                'No images will be uploaded or moved.') != QMessageBox.StandardButton.Yes:
            return
        self.task_start(lambda progress:index_visuals(self.db_path,ids=ids,progress=progress),
                        self.visual_index_complete)

    def index_visual_matches(self):
        with db.connect(self.db_path) as con:
            total=con.execute('SELECT COUNT(*) FROM photos').fetchone()[0]
            existing=indexed_count(con)
        if not total:
            QMessageBox.information(self,'No photos','Add a folder of images first.')
            return
        if QMessageBox.question(self,'Create local visual index',
                f'Index visual fingerprints for {total:,} photos? ({existing:,} indexed already.)\n\n'
                'Uses offline OpenCLIP and can take substantial time on CPU for 10,000 images. '
                'Existing up-to-date fingerprints will be reused. Nothing will be uploaded or moved.') \
                != QMessageBox.StandardButton.Yes:
            return
        self.task_start(lambda progress:index_visuals(self.db_path,progress=progress),
                        self.visual_index_complete)

    def visual_index_complete(self,result):
        summary=(f"Visual index: {result['indexed']} new, {result['cached']} already indexed, "
                 f"{result['failed']} reported errors")
        self.status.setText(summary)
        details='\n'.join(result['errors'][:8])
        QMessageBox.information(self,'Visual index completed',summary+(('\n\n'+details) if details else '')+
            '\nSelect an image and click Find similar photos.')

    def find_similar_selected(self):
        pid=self._one_visual_id()
        if pid is None:return
        with db.connect(self.db_path) as con:
            count=indexed_count(con)
            results=find_similar(con,pid,limit=40,visual_threshold=0.58)
            source=db.photo_by_id(con,pid)['path']
        if count<2:
            QMessageBox.information(self,'Visual index needed',
                'Click Index selected or Index whole library first. The existing Scan quality action only detects '
                'exact or near-duplicate photographs, not different photos of the same subject.')
            return
        if not results:
            QMessageBox.information(self,'No similar photos found',
                'No matches currently exceed the visual threshold. Try indexing all photos '
                'or choose another example image.')
            return
        SimilarityDialog(source,results,self).exec()

    def save_visual_reference(self):
        pid=self._one_visual_id()
        if pid is None:return
        kind,okay=QInputDialog.getItem(self,'Trusted visual reference','What does this example represent?',
                                      ['Attraction','Activity','Location'],0,False)
        if not okay:return
        label,okay=QInputDialog.getText(self,'Trusted visual reference',
                   'Enter a label you have verified (for example Nine Arch Bridge):')
        if not okay:return
        try:
            with db.connect(self.db_path) as con:set_reference(con,pid,kind,label)
        except ValueError as exc:
            QMessageBox.warning(self,'Reference not saved',str(exc));return
        QMessageBox.information(self,'Reference saved',
            f'Added verified example: {kind} — {label.strip()}.\n\n'
            'Other photos can now be compared with this example using Match reference examples. '
            'This does not automatically assign tags.')

    def find_reference_selected(self):
        pid=self._one_visual_id()
        if pid is None:return
        try:
            with db.connect(self.db_path) as con:
                matches=match_reference_examples(con,pid)
                source=db.photo_by_id(con,pid)['path']
        except (RuntimeError,OSError,ValueError) as exc:
            QMessageBox.warning(self,'Reference search unavailable',str(exc));return
        if not matches:
            QMessageBox.information(self,'No indexed reference examples',
                 'Save one or more trusted photos as reference examples and click Index selected (or Index whole library).')
            return
        dlg=SimilarityDialog(source,matches,self,reference_mode=True)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        match=dlg.selected_result()
        if not match:return
        prompt=(f"Copy the trusted '{match['reference_kind']}' label "
                f"'{match['reference_label']}' to the selected photo?\n\n"
                f"Similarity score: {match['cosine']:.3f} (not a probability).\n"
                'Confirm only if you visually verified both photographs.')
        if QMessageBox.question(self,'Confirm manual reference tag',prompt) != QMessageBox.StandardButton.Yes:
            return
        with db.connect(self.db_path) as con:
            applied=apply_reference(con,pid,match['id'])
        self.load_page()
        self.status.setText(f"Approved reference label: {applied['kind']} — {applied['label']}")

    # ----- My Drive: local virtual folders, protected originals -----
    def refresh_folder_tree(self):
        if not hasattr(self,'folder_tree'):return
        with db.connect(self.db_path) as con: rows=drive.all_folders(con)
        self.folder_tree.blockSignals(True)
        self.folder_tree.clear()
        nodes={}
        for row in rows:
            item=QTreeWidgetItem([row['name']])
            item.setData(0,Qt.ItemDataRole.UserRole,row['id'])
            nodes[row['id']]=item
        for row in rows:
            item=nodes[row['id']]
            parent=nodes.get(row['parent_id'])
            if parent:parent.addChild(item)
            else:self.folder_tree.addTopLevelItem(item)
        self.folder_tree.expandToDepth(1)
        self.folder_tree.blockSignals(False)

    def refresh_folder_strip(self):
        if not hasattr(self,'folder_buttons'):return
        while self.folder_buttons.count():
            item=self.folder_buttons.takeAt(0)
            widget=item.widget()
            if widget:widget.deleteLater()
        self.up_folder.setVisible(self.drive_view=='folder')
        if self.drive_view not in ('folder','drive','trash'):
            self.folder_breadcrumb.setText('')
            return
        with db.connect(self.db_path) as con:
            if self.drive_view=='folder':
                try:
                    trail=drive.ancestors(con,self.active_folder_id)
                    self.folder_breadcrumb.setText('My Drive / '+' / '.join(x['name'] for x in trail))
                    rows=drive.children(con,self.active_folder_id)
                except ValueError:
                    self.drive_view='drive';self.active_folder_id=None
                    rows=drive.children(con,None)
            elif self.drive_view=='drive':
                self.folder_breadcrumb.setText('My Drive')
                rows=drive.children(con,None)
            else:
                self.folder_breadcrumb.setText('Deleted folders — select to restore')
                rows=drive.all_folders(con,include_trashed=True)
        for row in rows[:12]:
            fid=row['id'];name=row['name']
            button=QPushButton(('♻ ' if self.drive_view=='trash' else '📁 ')+name)
            button.setToolTip(name)
            button.clicked.connect(lambda checked=False,number=fid:self.open_drive_folder(number))
            self.folder_buttons.addWidget(button)
        self.folder_buttons.addStretch()

    def on_folder_selected(self,item,column):
        fid=item.data(0,Qt.ItemDataRole.UserRole)
        if fid:self.open_drive_folder(int(fid))

    def open_drive_folder(self,fid):
        if self.drive_view=='trash':
            if QMessageBox.question(self,'Restore folder','Restore this folder and the photographs deleted with it?')!=QMessageBox.StandardButton.Yes:return
            try:
                with db.connect(self.db_path) as con:drive.restore_folder(con,fid)
            except Exception as exc:QMessageBox.warning(self,'Restore failed',str(exc));return
            self.refresh_folder_tree();self.reset_page();return
        self.drive_view='folder';self.active_folder_id=fid
        self._set_nav_active('drive')
        self.tabs.setCurrentIndex(0)
        self.reset_page()

    def go_up_folder(self):
        if self.drive_view!='folder':return
        try:
            with db.connect(self.db_path) as con:
                row=drive.folder(con,self.active_folder_id)
                parent=row['parent_id']
        except ValueError:parent=None
        self.active_folder_id=parent
        self.drive_view='folder' if parent is not None else 'drive'
        self.reset_page()

    def new_drive_folder(self):
        name,okay=QInputDialog.getText(self,'New folder','Folder name:')
        if not okay:return
        try:
            with db.connect(self.db_path) as con:
                drive.create_folder(con,name,self.active_folder_id if self.drive_view in ('folder','drive') else None)
            self.refresh_folder_tree();self.navigate('drive')
        except Exception as exc:QMessageBox.warning(self,'Folder error',str(exc))

    def rename_drive_folder(self):
        if self.active_folder_id is None:
            QMessageBox.information(self,'Select folder','Open a folder from the sidebar first.');return
        with db.connect(self.db_path) as con:row=drive.folder(con,self.active_folder_id)
        name,okay=QInputDialog.getText(self,'Rename folder','New folder name:',text=row['name'])
        if not okay:return
        try:
            with db.connect(self.db_path) as con:drive.rename_folder(con,self.active_folder_id,name)
            self.refresh_folder_tree();self.reset_page()
        except Exception as exc:QMessageBox.warning(self,'Rename failed',str(exc))

    def choose_drive_folder(self,title):
        with db.connect(self.db_path) as con:
            folders=drive.all_folders(con)
            paths=[]
            for row in folders:
                trail=drive.ancestors(con,row['id'])
                paths.append(('/'.join(r['name'] for r in trail),row['id']))
        options=['My Drive (root)']+[name for name,_ in paths]
        choice,okay=QInputDialog.getItem(self,title,'Destination folder:',options,0,False)
        if not okay:return False,None
        return True,None if choice==options[0] else dict(paths)[choice]

    def move_drive_folder(self):
        if self.active_folder_id is None:return
        okay,target=self.choose_drive_folder('Move folder')
        if not okay:return
        try:
            with db.connect(self.db_path) as con:drive.move_folder(con,self.active_folder_id,target)
            self.refresh_folder_tree();self.reset_page()
        except Exception as exc:QMessageBox.warning(self,'Move failed',str(exc))

    def trash_drive_folder(self):
        if self.active_folder_id is None:return
        if QMessageBox.question(self,'Trash folder','Hide this folder and its contents in local Trash? Original files remain on disk.')!=QMessageBox.StandardButton.Yes:return
        try:
            with db.connect(self.db_path) as con:drive.trash_folder(con,self.active_folder_id)
            self.active_folder_id=None;self.drive_view='drive';self.refresh_folder_tree();self.reset_page()
        except Exception as exc:QMessageBox.warning(self,'Trash failed',str(exc))

    def rename_drive_photo(self):
        ids=self.selected_ids()
        if len(ids)!=1:return
        with db.connect(self.db_path) as con:row=drive._active_photo(con,ids[0])
        name,okay=QInputDialog.getText(self,'Rename display name','Original file is not renamed on disk:',text=row['display_name'] or Path(row['path']).name)
        if not okay:return
        try:
            with db.connect(self.db_path) as con:drive.set_photo_name(con,ids[0],name)
            self.reset_page()
        except Exception as exc:QMessageBox.warning(self,'Rename failed',str(exc))

    def move_to_drive_folder(self):
        ids=self.selected_ids()
        if not ids:return
        okay,destination=self.choose_drive_folder('Move to folder')
        if not okay:return
        try:
            with db.connect(self.db_path) as con:count=drive.move_photos(con,ids,destination)
            self.reset_page();self.status.setText(f'{count} photos organized; physical originals unchanged.')
        except Exception as exc:QMessageBox.warning(self,'Move failed',str(exc))

    def copy_to_drive_folder(self):
        ids=self.selected_ids()
        if not ids:return
        okay,destination=self.choose_drive_folder('Copy photos')
        if not okay:return
        if QMessageBox.question(self,'Create copies','Make new local copies in application-managed storage? Source originals are unchanged.')!=QMessageBox.StandardButton.Yes:return
        self.task_start(lambda p:drive.copy_photos(self.db_path,ids,self.app_dir,destination,p),self.finish_drive_copies)

    def finish_drive_copies(self,result):
        self.reset_page();self.status.setText(f"Copied {result['copied']} photographs")
        if result['errors']:QMessageBox.warning(self,'Copy warnings','\n'.join(result['errors']))

    def star_drive_photos(self):
        ids=self.selected_ids()
        if not ids:return
        try:
            with db.connect(self.db_path) as con:
                active=[drive._active_photo(con,i) for i in ids]
                drive.set_star(con,ids,not all(row['starred'] for row in active))
            self.reset_page()
        except Exception as exc:QMessageBox.warning(self,'Star failed',str(exc))

    def trash_drive_photos(self):
        ids=self.selected_ids()
        if not ids:return
        if QMessageBox.question(self,'Move to Trash',f'Move {len(ids)} photographs to catalog Trash? Original files remain on disk.')!=QMessageBox.StandardButton.Yes:return
        try:
            with db.connect(self.db_path) as con:drive.trash_photos(con,ids)
            self.reset_page()
        except Exception as exc:QMessageBox.warning(self,'Trash failed',str(exc))

    def restore_drive_photos(self):
        if self.drive_view!='trash':QMessageBox.information(self,'Trash','Open Trash first.');return
        ids=self.selected_ids()
        if not ids:return
        try:
            with db.connect(self.db_path) as con:drive.restore_photos(con,ids)
            self.reset_page()
        except Exception as exc:QMessageBox.warning(self,'Restore failed',str(exc))

    def purge_drive_photos(self):
        if self.drive_view!='trash':QMessageBox.information(self,'Trash','Open Trash first.');return
        ids=self.selected_ids()
        if not ids:return
        answer=QMessageBox.question(self,'Remove catalog records',
            f'Permanently remove {len(ids)} records from the Photo Manager catalog?\n\n'
            'The source photographs on disk are NEVER deleted by this action.\n'
            'Catalog labels, references, and related recognition data may be lost.')
        if answer!=QMessageBox.StandardButton.Yes:return
        try:
            with db.connect(self.db_path) as con:drive.remove_catalog_records(con,ids)
            self.reset_page()
        except Exception as exc:QMessageBox.warning(self,'Removal failed',str(exc))

    def purge_drive_folder(self):
        if self.drive_view!='trash':
            QMessageBox.information(self,'Trash','Open Trash first.');return
        with db.connect(self.db_path) as con:
            rows=drive.all_folders(con,include_trashed=True)
            options={f"{r['name']} (#{r['id']})":r['id'] for r in rows}
        if not options:return
        name,okay=QInputDialog.getItem(self,'Remove trashed folder','Folder:',list(options),0,False)
        if not okay:return
        if QMessageBox.question(self,'Permanent catalog removal',
            'Remove this folder, its descendants and trashed photo records from the local catalog?\n\n'
            'Source photographs on disk are NEVER deleted. This cannot be undone.')!=QMessageBox.StandardButton.Yes:return
        try:
            with db.connect(self.db_path) as con:result=drive.purge_folder(con,options[name])
            self.refresh_folder_tree();self.reset_page()
            self.status.setText(f"Removed {result['folders']} virtual folders and {result['catalog_records']} catalog records")
        except Exception as exc:QMessageBox.warning(self,'Removal failed',str(exc))

    def download_originals(self):
        ids=self.selected_ids()
        if not ids:return
        dest=QFileDialog.getExistingDirectory(self,'Choose destination for untouched originals')
        if not dest:return
        self.task_start(lambda p:drive.save_originals(self.db_path,ids,Path(dest),p),self.finish_saved_originals)

    def finish_saved_originals(self,result):
        self.status.setText(f"Saved {result['copied']} original image copies in {result['destination']}")
        if result['errors']:QMessageBox.warning(self,'Save warnings','\n'.join(result['errors']))

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

    def refresh_ai_selected(self):
        ids = self.selected_ids()
        if not ids:
            return
        if local_ai_missing():
            QMessageBox.warning(self, 'Local AI unavailable',
                'Run INSTALL_AI_WINDOWS.bat and DIAGNOSE_AI_WINDOWS.bat first.')
            return
        okay = QMessageBox.question(self, 'Refresh local AI predictions',
            f'Recompute OpenCLIP suggestions for {len(ids)} selected photographs, ignoring cached results?\n'
            'This is offline and free. Manually reviewed tags remain protected. '
            'No photographs will be moved or uploaded.')
        if okay != QMessageBox.StandardButton.Yes:
            return
        self.task_start(lambda p: run_local(self.db_path, ids, p, force=True),
                        self.finished_tags)

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
        summary = (f"Analyzed {result['tagged']}; with activity: {result['with_activity']}; "
                   f"tentative landmarks: {result['with_attraction']}; "
                   f"no tags: {result['unmatched']}; cached: {result['cached']}; "
                   f"skipped/protected: {result['skipped']}; errors: {len(result['errors'])}.")
        self.status.setText(summary)
        self.show_report('Local AI classification - detailed results',
                         format_local_report(result))

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

    def edit_selected_photo(self):
        ids=self.selected_ids()
        if len(ids)!=1:
            if ids: QMessageBox.information(self,'Edit one photograph','Select exactly one photograph to open the photo editor.')
            return
        try:
            dlg=PhotoEditorDialog(self.db_path,int(ids[0]),self)
            dlg.exec()
        except Exception as exc:
            QMessageBox.warning(self,'Photo editor unavailable',str(exc))

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
        self._set_nav_active('all')
        self.reset_page()
        self.status.setText(f'Browsing photos for face group #{self.group_filter}. Click Clear filters to return to all photos.')

    def reset_page(self):
        self.offset=0;self.load_page()

    def clear_filters(self):
        self.group_filter=None
        self.drive_view='all'
        self.active_folder_id=None
        self.search.clear()
        self.locations.setCurrentIndex(0)
        self.activities.setCurrentIndex(0)
        self.tabs.setCurrentIndex(0)
        self._set_nav_active('all')
        self.reset_page()

    def previous_page(self):
        self.offset=max(0,self.offset-PAGE_SIZE);self.load_page()
    def next_page(self):
        if self.offset+PAGE_SIZE<self.total:self.offset+=PAGE_SIZE;self.load_page()
