<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/photo_editor.php';
function check_editor(bool $ok,string $label): void {if(!$ok)throw new RuntimeException('FAIL: '.$label);echo "PASS: $label\n";}
$default=editor_defaults();
check_editor($default['exposure']===0&&$default['crop']==='original','default recipe conservative');
check_editor(editor_validate(['crop'=>'272:300','rotate'=>90,'warmth'=>-10])['warmth']===-10,'validate crop rotate and warmth');
check_editor(editor_parse_recipe('{"exposure":24,"sharpness":10}')['sharpness']===10,'JSON recipe');
foreach([['rotate'=>45],['crop'=>'../../escape'],['warmth'=>101],['newfield'=>'surprise'],['sharpness'=>0.5]] as $bad){
    try{editor_validate($bad);throw new RuntimeException('Accepted unsafe edit recipe');}
    catch(InvalidArgumentException){check_editor(true,'invalid edit rejected');}
}
foreach(['[]','"text"','{"contrast":200}','broken'] as $bad){
    try{editor_parse_recipe($bad);throw new RuntimeException('Accepted malformed edit input');}
    catch(InvalidArgumentException){check_editor(true,'malformed recipe rejected');}
}
check_editor(editor_output_size(4000,3000,0,0,true)===[850,638],'preview scaled to bounded size');
check_editor(editor_output_size(4000,3000,272,300,false)===[272,300],'export exact thumbnail preset');
try{editor_output_size(4000,3000,2500,2500,false);throw new RuntimeException('Oversize export accepted');}
catch(InvalidArgumentException){check_editor(true,'oversized export rejected');}
if(extension_loaded('gd')){
    $image=imagecreatetruecolor(300,200);$red=imagecolorallocate($image,200,80,50);imagefill($image,0,0,$red);
    $rendered=editor_render($image,editor_validate(['crop'=>'square','rotate'=>90,'exposure'=>8,'warmth'=>14]),272,300,false);
    check_editor(imagesx($rendered)===272&&imagesy($rendered)===300,'GD edited export rendering');
}else echo "SKIP: GD rendering (extension not available on this test machine)\n";
