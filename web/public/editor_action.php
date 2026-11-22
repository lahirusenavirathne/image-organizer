<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/photo_editor.php';
try {
    if(!installed()){http_response_code(503);exit('Application not installed');}
    method_post();$me=auth_require_user('editor');verify_csrf();
    $db=pdo();drive_migrate($db);editor_migrate($db);
    $id=int_id($_POST['id']??null);$photo=editor_photo($db,$id);
    $recipe=editor_parse_recipe($_POST['recipe']??null);
    $action=(string)($_POST['action']??'');
    if($action==='save'){
        $expected=filter_var($_POST['version']??null,FILTER_VALIDATE_INT);
        if($expected===false||$expected<0)throw new InvalidArgumentException('Invalid editor revision');
        $version=editor_save($db,$id,$recipe,$expected,(int)$me['id']);
        respond(['success'=>true,'version'=>$version]);
    }
    if(!in_array($action,['preview','export','save_copy'],true))throw new InvalidArgumentException('Unsupported editor action');
    $preview=$action==='preview';
    $format=$preview?'jpg':(string)($_POST['format']??'webp');
    if(!in_array($format,['jpg','webp','png'],true))throw new InvalidArgumentException('Unsupported export format');
    $width=$preview?0:filter_var($_POST['width']??null,FILTER_VALIDATE_INT);
    $height=$preview?0:filter_var($_POST['height']??null,FILTER_VALIDATE_INT);
    if($width===false||$height===false)throw new InvalidArgumentException('Invalid export dimensions');
    if($action==='save_copy')editor_copy_filename($_POST['copy_name']??null,$format);
    $original=open_image(photo_path($photo),$photo['mime']);
    $image=editor_render($original,$recipe,$width,$height,$preview);
    if($action==='save_copy'){
        $result=editor_save_as_copy($db,$photo,$image,$format,(string)($_POST['copy_name']??''));
        imagedestroy($image);
        respond(['success'=>true,'id'=>$result['id'],'name'=>$result['name'],'folder_id'=>$result['folder_id']]);
    }
    header('Content-Type: '.(['jpg'=>'image/jpeg','webp'=>'image/webp','png'=>'image/png'][$format]));
    header('Cache-Control: private, no-store');header('X-Content-Type-Options: nosniff');
    if(!$preview)header('Content-Disposition: attachment; filename="photo-'.(int)$id.'-edited.'.$format.'"');
    else header('Content-Disposition: inline');
    $ok=match($format){'jpg'=>imagejpeg($image,null,83),'webp'=>imagewebp($image,null,86),'png'=>imagepng($image)};
    if(!$ok)error_log('GLPM edit render failed for photo id '.(int)$id);
    exit;
}catch(DomainException $e){respond(['error'=>$e->getMessage()],409);
}catch(InvalidArgumentException $e){respond(['error'=>$e->getMessage()],422);
}catch(Throwable $e){error_log('GLPM editor: '.get_class($e));$status=http_response_code();respond(['error'=>'Photo edit could not be completed'], $status>=400?$status:400);}
