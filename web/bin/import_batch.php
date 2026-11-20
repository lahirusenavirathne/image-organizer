<?php
declare(strict_types=1);
/** Cron-safe incremental SFTP import; run with DreamHost PHP CLI, never through HTTP. */
if(PHP_SAPI!=='cli'){http_response_code(403);exit('CLI only');}
require_once dirname(__DIR__).'/private/images.php';
if(!installed())exit("Application not installed\n");
ensure_dirs();
$lock=fopen(private_path('import.lock'),'c');
if(!$lock||!flock($lock,LOCK_EX|LOCK_NB))exit("Another import is already running\n");
$root=realpath(private_path('incoming'));$done=0;$failed=0;
try {
    $iterator=new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root,FilesystemIterator::SKIP_DOTS));
    foreach($iterator as $file) {
        if($done+$failed>=20)break;
        if(!$file->isFile()||$file->isLink()||!preg_match('/\.(jpg|jpeg|png|webp)$/i',$file->getFilename()))continue;
        $source=realpath($file->getPathname());
        if(!$source||!str_starts_with($source,$root.DIRECTORY_SEPARATOR))continue;
        try{
            ingest_image($source,$file->getFilename(),'SFTP incoming/'.substr($source,strlen($root)+1),false);
            $done++;
        }catch(Throwable $e){
            fwrite(STDERR,safe_basename($file->getFilename()).': '.$e->getMessage()."\n");quarantine_import($source);$failed++;
        }
    }
    echo date(DATE_ATOM)." Imported: $done; Failed: $failed\n";
}finally{flock($lock,LOCK_UN);fclose($lock);}
