<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/drive.php';
require_once dirname(__DIR__).'/private/images.php';

/** Small original-image ZIPs; no photo editing or image recompression. */
try {
    require_login('editor');drive_migrate(pdo());method_post();verify_csrf();
    if(!class_exists('ZipArchive'))throw new RuntimeException('PHP ZIP extension is required for downloads');
    $db=pdo();$mode=(string)($_POST['mode']??'selected');$photos=[];
    if($mode==='selected'){
        $ids=drive_photo_ids(json_decode((string)($_POST['ids']??''),true),24);
        foreach($ids as $id)$photos[]=drive_photo($db,$id);
    }elseif($mode==='folder'){
        $folder=int_id($_POST['folder']??null);drive_folder($db,$folder);
        $ids=drive_descendants(drive_folder_children($db),$folder,true);
        $stmt=$db->prepare('SELECT * FROM photos WHERE deleted_at IS NULL AND folder_id IN ('.drive_sql_ids($ids).') ORDER BY id LIMIT 25');
        $stmt->execute($ids);$photos=$stmt->fetchAll();
        if(count($photos)>24)throw new RuntimeException('This folder contains more than 24 images. Download them in smaller selections.');
        if(!$photos)throw new RuntimeException('Folder contains no photographs');
    }else throw new RuntimeException('Unknown download mode');
    ensure_dirs();$zipPath=private_path('tmp/'.bin2hex(random_bytes(16)).'.zip');$zip=new ZipArchive();
    if($zip->open($zipPath,ZipArchive::CREATE)!==true)throw new RuntimeException('Unable to create download ZIP');
    $manifest=fopen('php://temp','w+');fputcsv($manifest,['Download filename','Original name','Photo ID','Photographer','Copyright','License','Source folder','Source URL']);
    try {
        foreach($photos as $index=>$photo){
            $path=photo_path($photo);if(!is_file($path))throw new RuntimeException('A photo file is unavailable');
            $ext=mime_extension($photo['mime']);
            // Prefix avoids collisions between two files with the same original name.
            $stem=safe_basename(pathinfo($photo['original_name'],PATHINFO_FILENAME));
            $filename=sprintf('%03d_', $index+1).substr($stem,0,120).'.'.$ext;
            if(!$zip->addFile($path,$filename))throw new RuntimeException('Unable to add photo to ZIP');
            fputcsv($manifest,[$filename,$photo['original_name'],$photo['id'],$photo['photographer'],$photo['copyright_text'],$photo['license'],$photo['source_folder'],$photo['source_url']]);
        }
        rewind($manifest);$zip->addFromString('rights-and-sources.csv',(string)stream_get_contents($manifest));
    }finally {fclose($manifest);$zip->close();}
    header('Content-Type: application/zip');header('Content-Disposition: attachment; filename="guia-lanka-originals.zip"');header('Cache-Control: no-store');header('Content-Length: '.filesize($zipPath));
    readfile($zipPath);@unlink($zipPath);exit;
}catch(Throwable $e){if(http_response_code()<400)http_response_code(400);header('Content-Type: text/plain; charset=utf-8');exit('Download failed: '.$e->getMessage());}
