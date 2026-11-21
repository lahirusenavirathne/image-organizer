<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/images.php';
require_once dirname(__DIR__).'/private/drive.php';
try{
    require_login((($_GET['download']??'')==='1')?'editor':'viewer');drive_migrate(pdo());$id=int_id($_GET['id']??null);$type=(string)($_GET['type']??'thumb');
    if(!in_array($type,['thumb','original'],true))throw new RuntimeException('Invalid file type');
    $st=pdo()->prepare('SELECT * FROM photos WHERE id=? AND deleted_at IS NULL');$st->execute([$id]);$row=$st->fetch();
    if(!$row){http_response_code(404);exit('Photo not found');}
    $thumb=$type==='thumb';$path=photo_path($row,$thumb);
    if(!is_file($path)){http_response_code(404);exit('File missing');}
    header('Content-Type: '.($thumb?'image/jpeg':$row['mime']));
    header('Content-Disposition: '.((($_GET['download']??'')==='1')?'attachment':'inline').'; filename="'.($thumb?'thumb.jpg':'photo.'.mime_extension($row['mime'])).'"');
    header('Cache-Control: private, no-store');
    header('X-Content-Type-Options: nosniff');header('Content-Length: '.(string)filesize($path));
    readfile($path);
}catch(Throwable $e){http_response_code(403);exit('Not authorized to view image');}
