<?php
declare(strict_types=1);
require_once __DIR__.'/images.php';
require_once __DIR__.'/drive.php';

/** Portable non-destructive edit recipes; all source bytes remain private and unchanged. */
function editor_defaults(): array {
    return ['rotate'=>0,'crop'=>'original','exposure'=>0,'contrast'=>0,'highlights'=>0,
        'shadows'=>0,'saturation'=>0,'warmth'=>0,'sharpness'=>0];
}
function editor_validate(mixed $candidate): array {
    if (!is_array($candidate) || ($candidate!==[] && array_is_list($candidate))) throw new InvalidArgumentException('Edit settings must be an object');
    $r=editor_defaults();
    $ranges=['exposure'=>[-100,100],'contrast'=>[-100,100], 'highlights'=>[-100,100],
        'shadows'=>[-100,100],'saturation'=>[-100,100],'warmth'=>[-100,100], 'sharpness'=>[0,100]];
    foreach($candidate as $key=>$value) {
        if(!array_key_exists($key,$r))throw new InvalidArgumentException('Unsupported editing parameter');
        if($key==='crop'){
            if(!is_string($value) || !in_array($value,['original','square','4:3','3:2','16:9','272:300'],true))
                throw new InvalidArgumentException('Invalid crop preset');
        }elseif($key==='rotate'){
            if(!is_int($value)||!in_array($value,[0,90,180,270],true))throw new InvalidArgumentException('Invalid rotation');
        }elseif(!is_int($value)||$value<$ranges[$key][0]||$value>$ranges[$key][1])
            throw new InvalidArgumentException('Invalid adjustment range');
        $r[$key]=$value;
    }
    return $r;
}
function editor_parse_recipe(mixed $raw): array {
    if(!is_string($raw)||strlen($raw)>2048)throw new InvalidArgumentException('Invalid edit recipe');
    try{$candidate=json_decode($raw,false,16,JSON_THROW_ON_ERROR);}catch(JsonException){throw new InvalidArgumentException('Malformed edit recipe');}
    if(!$candidate instanceof stdClass)throw new InvalidArgumentException('Edit recipe must be a JSON object');
    return editor_validate((array)$candidate);
}
function editor_migrate(PDO $db): void {
    if(is_file(private_path('editor-v1-ready')))return;
    $lock=fopen(private_path('editor-v1-migrate.lock'),'c');
    if(!$lock||!flock($lock,LOCK_EX))throw new RuntimeException('Editor schema migration locked');
    try {
        if(is_file(private_path('editor-v1-ready')))return;
        $db->exec("CREATE TABLE IF NOT EXISTS photo_edit_recipes (
            photo_id BIGINT UNSIGNED PRIMARY KEY,
            recipe_json TEXT NOT NULL,
            version INT UNSIGNED NOT NULL DEFAULT 1,
            updated_by BIGINT UNSIGNED NOT NULL,
            updated_at DATETIME NOT NULL,
            CONSTRAINT fk_photo_edit_photo FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
        $tmp=private_path('editor-v1-ready.tmp');
        if(file_put_contents($tmp,"ready\n",LOCK_EX)===false||!rename($tmp,private_path('editor-v1-ready')))
            throw new RuntimeException('Editor schema marker could not be saved');
        @chmod(private_path('editor-v1-ready'),0600);
    } finally {flock($lock,LOCK_UN);fclose($lock);}
}
function editor_photo(PDO $db,int $id): array {
    $stmt=$db->prepare('SELECT * FROM photos WHERE id=? AND deleted_at IS NULL');$stmt->execute([$id]);
    $photo=$stmt->fetch();if(!$photo)throw new RuntimeException('Photograph not found or in Trash');
    return $photo;
}
function editor_stored(PDO $db,int $id): array {
    $q=$db->prepare('SELECT recipe_json,version FROM photo_edit_recipes WHERE photo_id=?');$q->execute([$id]);
    $row=$q->fetch();return $row?['recipe'=>editor_parse_recipe((string)$row['recipe_json']),'version'=>(int)$row['version']]:['recipe'=>editor_defaults(),'version'=>0];
}
/** Compare-and-swap prevents one editor from silently replacing another person's recipe. */
function editor_save(PDO $db,int $id,array $recipe,int $expected,int $userId): int {
    if($expected<0)throw new InvalidArgumentException('Invalid editor version');
    editor_photo($db,$id);
    $json=json_encode(editor_validate($recipe),JSON_THROW_ON_ERROR);
    if($expected===0){
        $stmt=$db->prepare('INSERT INTO photo_edit_recipes(photo_id,recipe_json,version,updated_by,updated_at) VALUES(?,?,1,?,UTC_TIMESTAMP())');
        try{$stmt->execute([$id,$json,$userId]);return 1;}catch(PDOException $e){
            if(($e->errorInfo[1]??null)==1062)throw new DomainException('Editor recipe changed elsewhere; reload the page');
            throw $e;
        }
    }
    $stmt=$db->prepare('UPDATE photo_edit_recipes SET recipe_json=?,version=version+1,updated_by=?,updated_at=UTC_TIMESTAMP() WHERE photo_id=? AND version=?');
    $stmt->execute([$json,$userId,$id,$expected]);
    if($stmt->rowCount()!==1)throw new DomainException('Editor recipe changed elsewhere; reload the page');
    return $expected+1;
}

function editor_crop(GdImage $source,string $crop): GdImage {
    $ratios=['square'=>1.0,'4:3'=>4/3,'3:2'=>1.5,'16:9'=>16/9,'272:300'=>272/300];
    if(!isset($ratios[$crop]))return $source;
    $w=imagesx($source);$h=imagesy($source);$ratio=$ratios[$crop];
    if($w/$h>$ratio){$cw=max(1,min($w,(int)round($h*$ratio)));$rect=['x'=>(int)floor(($w-$cw)/2),'y'=>0,'width'=>$cw,'height'=>$h];}
    else{$ch=max(1,min($h,(int)round($w/$ratio)));$rect=['x'=>0,'y'=>(int)floor(($h-$ch)/2),'width'=>$w,'height'=>$ch];}
    $out=imagecrop($source,$rect);
    if(!$out instanceof GdImage)throw new RuntimeException('Cropping failed');
    return $out;
}
function editor_output_size(int $w,int $h,int $requestedW,int $requestedH,bool $preview): array {
    if($requestedW<0||$requestedH<0||$requestedW>2500||$requestedH>2500)throw new InvalidArgumentException('Invalid export size');
    if($preview) {
        $ratio=min(850/$w,850/$h,1.0);
        return [max(1,(int)round($w*$ratio)),max(1,(int)round($h*$ratio))];
    }
    if($requestedW===0&&$requestedH===0)throw new InvalidArgumentException('Enter export width or height');
    if($requestedW && $requestedH){$ow=$requestedW;$oh=$requestedH;}
    elseif($requestedW){$ow=$requestedW;$oh=max(1,(int)round($h*$ow/$w));}
    else{$oh=$requestedH;$ow=max(1,(int)round($w*$oh/$h));}
    if($ow>2500||$oh>2500||$ow*$oh>2500000)throw new InvalidArgumentException('Export exceeds shared-hosting image limits (2.5 megapixels)');
    return [$ow,$oh];
}
function editor_render(GdImage $original,array $input,int $targetW=0,int $targetH=0,bool $preview=true): GdImage {
    $r=editor_validate($input);
    $source=$original;
    // Downsample before rotation/cropping to bound memory usage on shared hosting.
    $sourceW=imagesx($source);$sourceH=imagesy($source);
    $maximum=$preview?1200:3100;
    if(max($sourceW,$sourceH)>$maximum){
        $factor=$maximum/max($sourceW,$sourceH);
        $scaled=imagescale($source,max(1,(int)round($sourceW*$factor)),max(1,(int)round($sourceH*$factor)),IMG_BICUBIC_FIXED);
        if(!$scaled instanceof GdImage)throw new RuntimeException('Unable to create bounded source image');
        $source=$scaled;
    }
    if($r['rotate']){
        $rotated=imagerotate($source,360-$r['rotate'],0);
        if(!$rotated instanceof GdImage)throw new RuntimeException('Rotation failed');
        $source=$rotated;
    }
    $source=editor_crop($source,$r['crop']);
    $w=imagesx($source);$h=imagesy($source);
    [$ow,$oh]=editor_output_size($w,$h,$targetW,$targetH,$preview);
    // Center-crop when both dimensions are specified, preserving aspect ratios.
    if(!$preview&&$targetW&&$targetH){$source=editor_crop($source,'original');$aspect=$ow/$oh;
        if($w/$h>$aspect){$cw=max(1,min($w,(int)round($h*$aspect)));$cut=['x'=>(int)floor(($w-$cw)/2),'y'=>0,'width'=>$cw,'height'=>$h];}
        else{$ch=max(1,min($h,(int)round($w/$aspect)));$cut=['x'=>0,'y'=>(int)floor(($h-$ch)/2),'width'=>$w,'height'=>$ch];}
        $clipped=imagecrop($source,$cut);if(!$clipped instanceof GdImage)throw new RuntimeException('Export crop failed');
        $source=$clipped;$w=imagesx($source);$h=imagesy($source);
    }
    // A flat RGB canvas handles PNG transparency predictably; it does not change originals.
    $im=imagecreatetruecolor($ow,$oh);$white=imagecolorallocate($im,255,255,255);imagefilledrectangle($im,0,0,$ow,$oh,$white);
    imagealphablending($im,true);
    imagecopyresampled($im,$source,0,0,0,0,$ow,$oh,$w,$h);
    if($r['exposure']||$r['contrast']||$r['saturation']||$r['warmth']||$r['highlights']||$r['shadows']){
        $exposureFactor=2 ** ($r['exposure']/100);$contrastFactor=1+$r['contrast']/100;
        $sat=1+$r['saturation']/100;$shift=$r['warmth']*.24;
        $sh=$r['shadows']/100;$hi=$r['highlights']/100;
        $tone=function(float $n)use($sh,$hi):int{
            $v=max(0,min(255,$n));$normalized=$v/255;
            return (int)round(max(0,min(255,$v+$sh*76*(1-$normalized)**2+$hi*76*$normalized**2)));
        };
        for($y=0;$y<$oh;$y++)for($x=0;$x<$ow;$x++){ 
            $v=imagecolorat($im,$x,$y);$red=($v>>16)&255;$green=($v>>8)&255;$blue=$v&255;
            $red=($red*$exposureFactor-128)*$contrastFactor+128;
            $green=($green*$exposureFactor-128)*$contrastFactor+128;
            $blue=($blue*$exposureFactor-128)*$contrastFactor+128;
            $gray=.299*$red+.587*$green+.114*$blue;
            $red=$gray+($red-$gray)*$sat+$shift;
            $green=$gray+($green-$gray)*$sat;
            $blue=$gray+($blue-$gray)*$sat-$shift;
            imagesetpixel($im,$x,$y,($tone($red)<<16)|($tone($green)<<8)|$tone($blue));
        }
    }
    if($r['sharpness']){
        $k=$r['sharpness']/200;
        imageconvolution($im,[[0,-$k,0],[-$k,1+4*$k,-$k],[0,-$k,0]],1.0,0.0);
    }
    return $im;
}
