<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/images.php';
require_once dirname(__DIR__).'/private/drive.php';
try{
    require_login('editor');drive_migrate(pdo());method_post();verify_csrf();check_gd();
    if(!class_exists('ZipArchive'))throw new RuntimeException('PHP ZipArchive extension is required');
    $raw=explode(',',(string)($_POST['ids']??''));
    if(count($raw)<1||count($raw)>BATCH_SIZE)throw new RuntimeException('Select between 1 and '.BATCH_SIZE.' photographs per export');
    $ids=array_unique(array_map('int_id',$raw));
    $w=filter_var($_POST['width']??null,FILTER_VALIDATE_INT);$h=filter_var($_POST['height']??null,FILTER_VALIDATE_INT);
    if($w===false||$h===false||$w<0||$h<0||$w>2500||$h>2500||($w===0&&$h===0))throw new RuntimeException('Invalid dimensions');
    $format=(string)($_POST['format']??'webp');if(!in_array($format,['webp','jpg','png'],true))throw new RuntimeException('Unsupported output format');
    ensure_dirs();$zipPath=private_path('tmp/'.bin2hex(random_bytes(15)).'.zip');$zip=new ZipArchive();
    if($zip->open($zipPath,ZipArchive::CREATE)!==true)throw new RuntimeException('Unable to create ZIP');
    $csv=fopen('php://temp','w+');fputcsv($csv,['File','Original filename','Location','Activities','Attraction','Photographer','Copyright','License','Rights status','Source folder','Source URL']);
    $tmp=[];
    try{
        $stmt=pdo()->prepare('SELECT * FROM photos WHERE id=? AND deleted_at IS NULL');$index=1;
        foreach($ids as $id){
            $stmt->execute([$id]);$photo=$stmt->fetch();if(!$photo)continue;
            [$file,$ew,$eh]=make_export($photo,$w,$h,$format);$tmp[]=$file;
            $name=sprintf('%03d-', $index++).preg_replace('/[^a-zA-Z0-9_-]+/','-',pathinfo($photo['original_name'],PATHINFO_FILENAME)).'-'.$ew.'x'.$eh.'.'.$format;
            if(!$zip->addFile($file,$name))throw new RuntimeException('Could not add exported photo to ZIP');
            fputcsv($csv,[$name,$photo['original_name'],$photo['location'],$photo['activities'],$photo['attraction'],$photo['photographer'],$photo['copyright_text'],$photo['license'],$photo['rights_status'],$photo['source_folder'],$photo['source_url']]);
        }
        rewind($csv);$zip->addFromString('photo-rights-and-sources.csv',(string)stream_get_contents($csv));
        $zip->addFromString('READ-ME.txt','Image resizing does not confer usage rights. Confirm copyright/permissions separately. Metadata is in the CSV manifest.');
    }finally{fclose($csv);$zip->close();foreach($tmp as $file)@unlink($file);}
    header('Content-Type: application/zip');header('Content-Disposition: attachment; filename="guia-lanka-exports.zip"');header('Content-Length: '.filesize($zipPath));
    header('Cache-Control: no-store');readfile($zipPath);@unlink($zipPath);exit;
}catch(Throwable $e){if(http_response_code()<400)http_response_code(400);header('Content-Type: text/plain; charset=utf-8');exit('Export failed: '.$e->getMessage());}
