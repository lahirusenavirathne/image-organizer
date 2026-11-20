<?php
declare(strict_types=1);
require_once __DIR__ . '/bootstrap.php';

function gd_supported(): bool { return extension_loaded('gd') && function_exists('imagecreatetruecolor'); }
function check_gd(): void { if (!gd_supported()) throw new RuntimeException('PHP GD image extension is required. Enable GD in DreamHost PHP settings.'); }
function mime_extension(string $mime): string { return ['image/jpeg'=>'jpg','image/png'=>'png','image/webp'=>'webp'][$mime] ?? throw new RuntimeException('Unsupported image'); }
function open_image(string $path, string $mime): GdImage {
    check_gd();
    $image = match ($mime) {
        'image/jpeg' => imagecreatefromjpeg($path),
        'image/png' => imagecreatefrompng($path),
        'image/webp' => function_exists('imagecreatefromwebp') ? imagecreatefromwebp($path) : false,
        default => false
    };
    if (!$image instanceof GdImage) throw new RuntimeException('Could not decode image; format may not be enabled in GD');
    if ($mime === 'image/jpeg' && function_exists('exif_read_data')) {
        try {
            $exif = @exif_read_data($path) ?: [];
            $orientation = (int)($exif['Orientation'] ?? 1);
            $angle = match ($orientation) {3=>180,6=>270,8=>90,default=>0};
            if ($angle) {$rotated = imagerotate($image,$angle,0); if ($rotated instanceof GdImage) {$image=$rotated;}}
        } catch (Throwable) { /* metadata optional */ }
    }
    return $image;
}
function details(string $file): array {
    $bytes = filesize($file);
    if ($bytes === false || $bytes < 1 || $bytes > MAX_FILE_BYTES) throw new RuntimeException('Image exceeds 25 MB or is empty');
    $mime = supported_mime($file);
    if (!$mime) throw new RuntimeException('Only JPG, PNG and WebP are accepted');
    $dimension = @getimagesize($file);
    if (!$dimension || $dimension[0] < 1 || $dimension[1] < 1 || $dimension[0]*$dimension[1] > MAX_PIXELS) {
        throw new RuntimeException('Invalid or excessively large image (maximum 28 megapixels)');
    }
    if (($dimension['mime'] ?? '') !== $mime) throw new RuntimeException('MIME validation failed');
    return [$mime,(int)$dimension[0],(int)$dimension[1],$bytes];
}
function image_dhash(GdImage $img): string {
    check_gd();
    $small=imagecreatetruecolor(9,8);imagecopyresampled($small,$img,0,0,0,0,9,8,imagesx($img),imagesy($img));
    $out='';
    for($y=0;$y<8;$y++) {
        $bits=0;
        for($x=0;$x<8;$x++) {
            $a=imagecolorsforindex($small,imagecolorat($small,$x,$y));
            $b=imagecolorsforindex($small,imagecolorat($small,$x+1,$y));
            $la=($a['red']*299+$a['green']*587+$a['blue']*114);
            $lb=($b['red']*299+$b['green']*587+$b['blue']*114);
            $bits=($bits<<1) | (int)($la>$lb);
        }
        $out.=sprintf('%02x',$bits);
    }
    return $out;
}
function hamming_hex(string $left, string $right): int {
    if (!preg_match('/\A[a-f0-9]{16}\z/', $left) || !preg_match('/\A[a-f0-9]{16}\z/',$right)) return 65;
    $count=[0,1,1,2,1,2,2,3,1,2,2,3,2,3,3,4];$distance=0;
    for ($i=0;$i<16;$i++) $distance += $count[hexdec($left[$i]) ^ hexdec($right[$i])];
    return $distance;
}
function average_color(GdImage $img): string {
    $small=imagecreatetruecolor(8,8);
    imagecopyresampled($small,$img,0,0,0,0,8,8,imagesx($img),imagesy($img));
    $r=$g=$b=0;
    for($y=0;$y<8;$y++) for($x=0;$x<8;$x++) {
        $c=imagecolorsforindex($small,imagecolorat($small,$x,$y));
        $r+=$c['red'];$g+=$c['green'];$b+=$c['blue'];
    }
    return sprintf('%02x%02x%02x',(int)round($r/64),(int)round($g/64),(int)round($b/64));
}
function color_distance(string $a, string $b): float {
    if(!preg_match('/\A[a-f0-9]{6}\z/',$a)||!preg_match('/\A[a-f0-9]{6}\z/',$b))return 999;
    $d=0;
    foreach([0,2,4] as $i) $d+=(hexdec(substr($a,$i,2))-hexdec(substr($b,$i,2)))**2;
    return sqrt($d);
}
function thumbnail(string $source, string $dest, string $mime): array {
    $img=open_image($source,$mime);
    $w=imagesx($img);$h=imagesy($img);$scale=min(400/$w,300/$h,1);
    $dw=max(1,(int)round($w*$scale));$dh=max(1,(int)round($h*$scale));
    $out=imagecreatetruecolor($dw,$dh);
    $bg=imagecolorallocate($out,246,247,247);imagefill($out,0,0,$bg);
    imagecopyresampled($out,$img,0,0,0,0,$dw,$dh,$w,$h);
    if (!imagejpeg($out,$dest,83)) throw new RuntimeException('Unable to create thumbnail');
    return [image_dhash($img),average_color($img)];
}
function safe_basename(string $name): string {
    $name=str_replace('\\','/',$name);
    $name=basename($name);
    $name=preg_replace('/[^\pL\pN. _()-]+/u','_', $name) ?: 'image';
    return substr($name,0,220);
}
function ingest_image(string $temp, string $name, string $source, bool $is_upload): array {
    ensure_dirs();check_gd();
    [$mime,$w,$h,$bytes]=details($temp);
    $stored=bin2hex(random_bytes(20)).'.'.mime_extension($mime);
    $new=private_path('originals/'.$stored);
    $thumb=private_path('thumbnails/'.$stored.'.jpg');
    $sha=hash_file('sha256',$temp);
    $camera='';$taken='';$photographer='';$copyright='';
    if ($mime==='image/jpeg' && function_exists('exif_read_data')) {
        try {
            $exif=@exif_read_data($temp) ?: [];
            $camera=clean_text((string)($exif['Model'] ?? ''),255);
            $taken=clean_text((string)($exif['DateTimeOriginal'] ?? ''),64);
            $photographer=clean_text((string)($exif['Artist'] ?? ''),255);
            $copyright=clean_text((string)($exif['Copyright'] ?? ''),1000);
        } catch (Throwable) { }
    }
    if ($is_upload) {$ok=is_uploaded_file($temp) && move_uploaded_file($temp,$new);}
    else {$ok=rename($temp,$new);}
    if (!$ok) throw new RuntimeException('Could not move the uploaded photo into private storage');
    try {
        $fingerprints=thumbnail($new,$thumb,$mime);
        $stm=pdo()->prepare('INSERT INTO photos(stored_name,original_name,sha256,dhash,color_sig,mime,file_size,width,height,camera,taken_at,source_folder,photographer,copyright_text) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)');
        $stm->execute([$stored,safe_basename($name),$sha,$fingerprints[0],$fingerprints[1],$mime,$bytes,$w,$h,$camera,$taken,clean_text($source,500),$photographer,$copyright]);
        return ['id'=>(int)pdo()->lastInsertId(),'name'=>safe_basename($name),'hash'=>$fingerprints[0]];
    } catch(Throwable $e) { @unlink($new);@unlink($thumb);throw $e; }
}
function make_export(array $photo,int $w,int $h,string $format): array {
    check_gd();
    $mime=$photo['mime'];$src=photo_path($photo);
    $img=open_image($src,$mime);$sw=imagesx($img);$sh=imagesy($img);
    if($w===0 && $h===0) throw new RuntimeException('Specify at least one dimension');
    if($w===0)$w=max(1,(int)round($sw*$h/$sh));
    if($h===0)$h=max(1,(int)round($sh*$w/$sw));
    if($w<1||$h<1||$w>2500||$h>2500||$w*$h>6250000)throw new RuntimeException('Export dimensions exceed safety limits');
    $out=imagecreatetruecolor($w,$h);
    $fill=imagecolorallocate($out,255,255,255);imagefill($out,0,0,$fill);
    $scale=max($w/$sw,$h/$sh);$cw=(int)round($w/$scale);$ch=(int)round($h/$scale);
    $sx=max(0,(int)floor(($sw-$cw)/2));$sy=max(0,(int)floor(($sh-$ch)/2));
    imagecopyresampled($out,$img,0,0,$sx,$sy,$w,$h,min($cw,$sw),min($ch,$sh));
    $path=private_path('tmp/'.bin2hex(random_bytes(12)).'.'.$format);
    $ok=match($format){'webp'=>function_exists('imagewebp')?imagewebp($out,$path,83):false,
        'jpg'=>imagejpeg($out,$path,86),'png'=>imagepng($out,$path,6),default=>false};
    if(!$ok){@unlink($path);throw new RuntimeException('Cannot export '.$format.' on this PHP installation');}
    return [$path,$w,$h];
}

/** Move failed SFTP imports to quarantine instead of retrying the same invalid file forever. */
function quarantine_import(string $source): void {
    ensure_dirs();
    if(!is_file($source))return;
    $dest=private_path('rejected/'.bin2hex(random_bytes(8)).'-'.safe_basename(basename($source)));
    if(!rename($source,$dest))error_log('GLPM: unable to quarantine failed file '.basename($source));
}
