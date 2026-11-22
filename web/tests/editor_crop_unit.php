<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/photo_editor.php';
function crop_check(bool $ok,string $name): void {if(!$ok)throw new RuntimeException('FAIL: '.$name);echo "PASS: $name\n";}
$defaults=editor_defaults();
crop_check($defaults['crop_manual']===0&&$defaults['crop_w']===1000&&$defaults['straighten']===0,'Old recipes retain original centered-crop behavior');
$manual=editor_validate(['crop'=>'free','crop_manual'=>1,'crop_x'=>160,'crop_y'=>220,'crop_w'=>550,'crop_h'=>400,'straighten'=>-35]);
crop_check($manual['crop_x']===160&&$manual['crop_w']===550&&$manual['straighten']===-35,'Manual crop and 0.1-degree correction preserved');
foreach([['straighten'=>151],['straighten'=>-151],['crop_x'=>990,'crop_w'=>30,'crop_manual'=>1],['crop_y'=>800,'crop_h'=>220,'crop_manual'=>1],['crop_w'=>0],['crop_manual'=>2],['crop_x'=>-2],['crop'=>'unknown']] as $bad){
 try{editor_validate($bad);throw new RuntimeException('Unsafe recipe accepted');}
 catch(InvalidArgumentException){crop_check(true,'Invalid crop or angle rejected');}
}
$legacy=editor_parse_recipe('{"rotate":90,"crop":"square"}');
crop_check($legacy['crop_manual']===0&&$legacy['straighten']===0,'Legacy saved recipe upgraded without changing interpretation');
$web=dirname(__DIR__);
$action=file_get_contents($web.'/public/editor_action.php');
$js=file_get_contents($web.'/public/assets/editor.js');
$html=file_get_contents($web.'/public/editor.php');
$css=file_get_contents($web.'/public/assets/editor.css');
crop_check(str_contains($action,"'straighten','crop','crop_manual','crop_x','crop_y','crop_w','crop_h'"),'Before/after uses the same crop rectangle and geometry');
crop_check(str_contains($js,"crop:'original',crop_manual:0") && str_contains($js,'cropMode?'),'Crop UI previews the full image while dragging');
crop_check(str_contains($js,"setPointerCapture(event.pointerId)")&&str_contains($js,"handle.addEventListener('keydown'"),'Pointer and keyboard crop controls');
crop_check(str_contains($html,'data-crop-handle="nw"')&&str_contains($html,'data-crop-handle="se"')&&str_contains($html,'id="editor-crop-toggle"'),'Crop handles and mode toggle exist');
crop_check(str_contains($html,'min="-150" max="150" step="1"'),'Straighten control uses tenths of a degree');
crop_check(str_contains($css,'.editor-crop-box')&&str_contains($css,'.crop-handle'),'Crop boundary visuals exist');
if(extension_loaded('gd')){
 $im=imagecreatetruecolor(1200,800);$red=imagecolorallocate($im,200,30,20);imagefill($im,0,0,$red);
 $out=editor_render($im,$manual,0,0,true);
 crop_check(imagesx($out)>0&&imagesy($out)>0&&imagesx($out)<1200,'GD actual crop and straighten render');
} else echo "SKIP: GD rendering unavailable in this environment\n";
echo "Phase 1B crop unit checks passed\n";
