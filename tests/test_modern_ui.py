"""Real Qt smoke tests when PySide6 is available (Windows CI and developer PC)."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import pytest
from PIL import Image

pytest.importorskip('PySide6')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from app import db
from app.ui import Window


@pytest.fixture(scope='module')
def application():
    app = QApplication.instance() or QApplication([])
    yield app


def test_modern_sidebar_gallery_filters_inspector_and_rights(application, tmp_path):
    folder = tmp_path / 'photos'
    folder.mkdir()
    Image.new('RGB', (800, 600), (35, 120, 85)).save(folder / 'sigiriya.jpg')
    Image.new('RGB', (800, 600), (145, 170, 195)).save(folder / 'nine-arch.jpg')
    app_dir = tmp_path / 'state'
    window = Window(app_dir)
    try:
        db.scan_folder(window.db_path, folder)
        window.load_page()
        application.processEvents()
        assert window.list.count() == 2
        assert window.list.objectName() == 'PhotoGrid'
        assert not window.inspector.isVisible()  # opens on selection
        assert len(window.nav_buttons) == 10
        assert window.filter_panel.isHidden()
        window.navigate('locations')
        assert not window.filter_panel.isHidden()
        window.navigate('people')
        assert window.tabs.currentIndex() == 1
        window.navigate('all')
        assert window.tabs.currentIndex() == 0
        window.render_thumbs(0)
        assert not window.list.item(0).icon().isNull()
        window.list.item(0).setSelected(True)
        application.processEvents()
        assert not window.inspector.isHidden()
        assert window.current_id is not None
        window.rights_status.setCurrentText('Permission required')
        photo_id = window.current_id
        window.save_details()
        with db.connect(window.db_path) as con:
            assert db.photo_by_id(con, photo_id)['rights_status'] == 'Permission required'
        window.toggle_grid_density(True)
        assert window.list.gridSize().width() == 205
        window.toggle_grid_density(False)
        assert window.list.gridSize().width() == 252
    finally:
        window.close()


def test_photo_card_labels_and_search(application, tmp_path):
    folder = tmp_path / 'pics'
    folder.mkdir()
    Image.new('RGB', (420, 420), (200, 100, 50)).save(folder / 'elephant.jpg')
    window = Window(tmp_path / 'app_data')
    try:
        db.scan_folder(window.db_path, folder)
        window.load_page()
        item = window.list.item(0)
        assert item.data(Qt.ItemDataRole.UserRole + 1) == 'elephant.jpg'
        window.search.setText('not-in-file')
        window.search_timer.stop()
        window.reset_page()
        assert window.list.count() == 0
        assert not window.empty_label.isHidden()
        window.search.setText('elephant')
        window.search_timer.stop()
        window.reset_page()
        assert window.list.count() == 1
    finally:
        window.close()


def test_my_drive_navigation_and_trash(application,tmp_path):
    from app import drive
    folder=tmp_path/'source';folder.mkdir()
    Image.new('RGB',(64,64),'green').save(folder/'image.jpg')
    window=Window(tmp_path/'app_data')
    try:
        imported=drive.import_tree(window.db_path,folder)
        assert imported['indexed']==1
        window.refresh_folder_tree()
        window.navigate('drive')
        assert window.folder_tree.topLevelItemCount()==1
        fid=window.folder_tree.topLevelItem(0).data(0,Qt.ItemDataRole.UserRole)
        window.open_drive_folder(fid)
        assert window.drive_view=='folder' and window.list.count()==1
        window.view_toggle.setChecked(True)
        assert window.view_mode=='list'
        window.view_toggle.setChecked(False)
        assert window.view_mode=='grid'
        pid=window.list.item(0).data(Qt.ItemDataRole.UserRole)
        with db.connect(window.db_path) as con:drive.trash_photos(con,[pid])
        window.navigate('trash')
        assert window.list.count()==1
        with db.connect(window.db_path) as con:drive.restore_photos(con,[pid])
        window.navigate('all')
        assert window.list.count()==1
    finally:window.close()
