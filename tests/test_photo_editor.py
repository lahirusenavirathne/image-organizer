"""Photo editor protects originals and validates portable edit recipes."""
from pathlib import Path
from PIL import Image
import pytest
from app import db, photo_editor


def test_recipe_validation():
    assert photo_editor.normalize_recipe(None)==photo_editor.DEFAULT
    for recipe in ({'rotate':45},{'rotate':True},{'crop':'../../secret'},
                   {'exposure':101},{'warmth':1.5},{'surprise':12}):
        with pytest.raises(ValueError):photo_editor.normalize_recipe(recipe)


def test_rotations_crop_tonal_and_export_preserve_bytes(tmp_path):
    src=tmp_path/'source.png';Image.new('RGB',(160,90),(65,100,170)).save(src)
    old=src.read_bytes()
    recipe=photo_editor.normalize_recipe({'rotate':90,'crop':'square','exposure':25,'contrast':12,
                        'highlights':-20,'shadows':10,'saturation':-10,'warmth':18,'sharpness':12})
    with Image.open(src) as opened:
        out=photo_editor.apply_recipe(opened,recipe)
    assert out.width==out.height and out.size==(90,90)
    assert out.getpixel((0,0))!=(65,100,170)
    dest=tmp_path/'thumbnail.webp'
    assert photo_editor.export_copy(src,dest,recipe,width=272,height=300)==(272,300)
    with Image.open(dest) as saved:
        assert saved.size==(272,300)
    assert src.read_bytes()==old
    with pytest.raises(FileExistsError):photo_editor.export_copy(src,dest,recipe)
    with pytest.raises(ValueError):photo_editor.export_copy(src,src,recipe)
    assert dest.exists()


def test_edit_recipe_persists_and_blocks_trash(tmp_path):
    src=tmp_path/'photo.jpg';Image.new('RGB',(80,50),(130,65,25)).save(src)
    dbfile=tmp_path/'db.sqlite';db.init(dbfile)
    with db.connect(dbfile) as con:
        from app.metadata import read_image
        db.upsert(con,read_image(src))
        photo_id=con.execute('SELECT id FROM photos').fetchone()['id']
        assert photo_editor.load_recipe(con,photo_id)==photo_editor.DEFAULT
        photo_editor.save_recipe(con,photo_id,{'exposure':8,'crop':'4:3'})
    with db.connect(dbfile) as con:
        assert photo_editor.load_recipe(con,photo_id)['exposure']==8
        con.execute('UPDATE photos SET deleted_at=CURRENT_TIMESTAMP WHERE id=?',(photo_id,))
        with pytest.raises(ValueError):photo_editor.save_recipe(con,photo_id,{'contrast':10})
