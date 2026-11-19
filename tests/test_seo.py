import csv
import json
from PIL import Image
from app import db
from app.seo import slug,alt_text
from app.operations import export_photos


def test_slug_sanitized():
    assert slug('Ella & Nine Arch Bridge!')=='ella-nine-arch-bridge'
    assert slug('Cascadas de Ravána')=='cascadas-de-ravana'


def test_bilingual_export_and_preserve_source(tmp_path):
    photos=tmp_path/'source';photos.mkdir();source=photos/'DSC_1001.jpg'
    Image.new('RGB',(60,40),'orange').save(source)
    database=tmp_path/'images.sqlite';db.init(database);db.scan_folder(database,photos)
    with db.connect(database) as con:
        pid=con.execute('SELECT id FROM photos').fetchone()['id']
        db.update_metadata(con,pid,location='Ella',activity_text='Trekking',attraction='Nine Arch Bridge',
                           source_url='',artist='Alice',copyright='(c) Alice',license='Licensed')
        original=source.read_bytes()
    out=tmp_path/'out'
    result=export_photos(database,[pid],out,width=272,height=300,mode='Crop to fill',fmt='WEBP',quality=82,seo_names=True)
    assert result['exported']==1
    files=list(out.glob('*.webp'))
    assert len(files)==1 and 'nine-arch-bridge' in files[0].name
    with Image.open(files[0]) as im:assert im.size==(272,300)
    with open(result['manifest'],encoding='utf-8-sig',newline='') as f: row=next(csv.DictReader(f))
    assert 'Trekking' in row['alt_text_en'] and 'senderismo' in row['alt_text_es']
    assert row['rights_status']=='Unknown'
    assert source.read_bytes()==original


def test_unknown_photo_fallback(tmp_path):
    row={'attraction':'','location':'','activities':json.dumps([]),'path':'/path/unknown_photo.jpg'}
    eng,es=alt_text(row)
    assert eng and es
