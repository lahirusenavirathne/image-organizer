<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/photo_editor.php';
function phase2_check(bool $ok, string $label): void {if(!$ok)throw new RuntimeException('FAIL: '.$label);echo "PASS: $label\n";}
$defaults=editor_defaults();
foreach(['whites','blacks','vibrance','tint','curve_shadows','curve_midtones','curve_highlights','hsl_green_hue','hsl_blue_sat','hsl_red_lum'] as $name)
 phase2_check(($defaults[$name]??null)===0,'Neutral default '.$name);
phase2_check(editor_validate(['whites'=>-25,'curve_midtones'=>18,'hsl_green_sat'=>-30])['hsl_green_sat']===-30,'New controls validated');
foreach([['whites'=>101],['curve_shadows'=>51],['curve_midtones'=>-51],['hsl_blue_hue'=>31],['hsl_green_sat'=>-101],['hsl_red_lum'=>71],['hsl_synthetic_hue'=>1],['curve_midtones'=>0.4]] as $bad){
 try{editor_validate($bad);throw new RuntimeException('Accepted out-of-range control');}
 catch(InvalidArgumentException){phase2_check(true,'Unsafe control rejected');}
}
$legacy=editor_parse_recipe('{"rotate":90,"crop":"square","exposure":7}');
phase2_check($legacy['hsl_green_hue']===0&&$legacy['curve_midtones']===0&&$legacy['exposure']===7,'Phase 1 recipes remain compatible');
$full=editor_defaults();$decoded=editor_parse_recipe(json_encode($full));
phase2_check(count($decoded)===count($full),'Complete edited recipe fits parser length limit');
$neutral=editor_tone_lut($full);
phase2_check($neutral[0]===0&&$neutral[255]===255,'Neutral curve endpoints');
phase2_check($neutral===range(0,255),'Neutral tone curve preserves every original level');
$curve=editor_tone_lut(editor_validate(['curve_shadows'=>20,'curve_midtones'=>-13,'curve_highlights'=>12]));
phase2_check($curve[64]>$neutral[64]&&$curve[128]<$neutral[128]&&$curve[192]>$neutral[192],'Tone curve sliders change correct ranges');
for($i=1;$i<256;$i++)if($curve[$i]<$curve[$i-1])throw new RuntimeException('Curve is not monotonic at '.$i);
phase2_check(true,'Tone curve remains monotonic across 256 levels');
foreach([[201,111,34],[35,145,220],[130,130,130],[255,0,0],[0,255,0],[0,0,255]] as $rgb){
 [$h,$s,$l]=editor_rgb_to_hsl(...$rgb);$restored=editor_hsl_to_rgb($h,$s,$l);
 phase2_check(max(array_map(fn($a,$b)=>abs($a-$b),$rgb,$restored))<=1,'RGB HSL round trip '.join(',',$rgb));
}
$hsl=editor_validate(['hsl_green_hue'=>18,'hsl_green_sat'=>-25,'hsl_green_lum'=>12]);
phase2_check(editor_hsl_controls($hsl,120)[0]>10,'Green hue control affects green');
phase2_check(editor_hsl_controls($hsl,240)[0]===0.0,'Green hue leaves blue unchanged');
$root=dirname(__DIR__);
$html=(string)file_get_contents($root.'/public/editor.php');
$js=(string)file_get_contents($root.'/public/assets/editor.js');
$css=(string)file_get_contents($root.'/public/assets/editor.css');
phase2_check(str_contains($html,'id="editor-histogram"')&&str_contains($js,'refreshHistogram()'),'Histogram connected to preview');
phase2_check(str_contains($html,'id="editor-tone-curve"')&&str_contains($js,'updateToneCurve()'),'Tone curve interface updates');
phase2_check(str_contains($html,'name="<?=$key?>"')&&str_contains($html,'EDITOR_HSL_COLORS'),'HSL channel PHP controls present');
phase2_check(str_contains($js,'...advancedFields')&&str_contains($js,'for (const key of toneFields)'),'HSL edits tracked by undo/presets');
phase2_check(str_contains($html,'assets/editor.js?v=web-0.9.1-studio-ui')&&str_contains($html,'assets/editor.css?v=web-0.9.1-studio-ui'),'New files are cache-busted');
phase2_check(str_contains($css,'.studio-histogram')&&str_contains($css,'.hsl-color-group'),'Mobile-capable editor styles present');
phase2_check(str_contains($css,'flex:0 0 13px'),'HSL swatches stay circular');
if(extension_loaded('gd')){
 $source=imagecreatetruecolor(200,120);$color=imagecolorallocate($source,90,145,76);imagefill($source,0,0,$color);
 $output=editor_render($source,$hsl,0,0,true);
 phase2_check(imagesx($output)===200&&imagesy($output)===120,'GD advanced renderer works');
 imagedestroy($output);imagedestroy($source);
} else echo "SKIP: GD actual image processing (not installed)\n";
echo "Phase 2A professional tone/color checks passed\n";
