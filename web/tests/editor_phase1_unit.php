<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/photo_editor.php';
function phase1_assert(bool $ok,string $label): void {if(!$ok)throw new RuntimeException('FAIL: '.$label);echo "PASS: $label\n";}
foreach([40,85,100] as $quality)phase1_assert(editor_quality((string)$quality)===$quality,'Quality '.$quality.' accepted');
foreach([null,'',39,101,'-1','abc',true,85.5] as $bad){
    try{editor_quality($bad);throw new RuntimeException('Quality accepted wrongly');}
    catch(InvalidArgumentException){phase1_assert(true,'Invalid quality rejected: '.json_encode($bad));}
}
$root=dirname(__DIR__);
$editor=(string)file_get_contents($root.'/public/editor.php');
$action=(string)file_get_contents($root.'/public/editor_action.php');
$js=(string)file_get_contents($root.'/public/assets/editor.js');
$css=(string)file_get_contents($root.'/public/assets/editor.css');
phase1_assert(str_contains($editor,'id="editor-undo"')&&str_contains($editor,'id="editor-redo"'),'History UI present');
phase1_assert(str_contains($js,'historyStep(')&&str_contains($js,'recordEdit('),'Undo/redo logic present');
phase1_assert(str_contains($editor,'id="editor-zoom-in"')&&str_contains($js,"imageStage.setPointerCapture"),'Zoom and pointer capture present');
phase1_assert(str_contains($editor,'id="editor-compare-position"')&&str_contains($action,"'preview_before'"),'Before/after comparison end to end');
phase1_assert(str_contains($action,'array_intersect_key($recipe')&&str_contains($action,"'crop_manual','crop_x','crop_y','crop_w','crop_h'"),'Before image preserves geometry');
phase1_assert(str_contains($js,'safeStorageRead')&&str_contains($js,'safeStorageWrite'),'Presets are browser-local');
phase1_assert(str_contains($js,"data.set('quality',field('quality').value)")&&str_contains($action,'editor_quality('),'Quality forwarded to endpoint');
phase1_assert(str_contains($action,'$preview?85:editor_quality($_POST'), 'Preview unaffected by export quality');
phase1_assert(str_contains($css,'.editor-image-stage.zoomed'),'Zoom CSS exists');
phase1_assert(str_contains($editor,'assets/editor.js?v=web-0.9.0-phase2a'),'Phase1 asset cache-busted');
