<?php
/** Structural smoke checks for the photo studio redesign; no DB required. */
declare(strict_types=1);
$base=dirname(__DIR__).'/public';
$editor=file_get_contents($base.'/editor.php');
$js=file_get_contents($base.'/assets/editor.js');
$css=file_get_contents($base.'/assets/editor.css');
$assertions=[
  'Large preview canvas'=>str_contains($editor,'class="studio-canvas"') && str_contains($editor,'id="editor-preview"'),
  'Tool rail target ids'=>!array_diff(['panel-light','panel-color','panel-crop','panel-detail','panel-export'],array_map(fn($id)=>str_contains($editor,'id="'.$id.'"')?$id:'', ['panel-light','panel-color','panel-crop','panel-detail','panel-export'])),
  'Original preview control'=>str_contains($editor,'id="editor-before"'),
  'Editor save/export functional controls'=>str_contains($editor,'id="editor-save"') && str_contains($editor,'id="editor-export"'),
  'All recipe sliders'=>!array_filter(['exposure','contrast','highlights','shadows','saturation','warmth','sharpness'],fn($key)=>!str_contains($editor,"'".$key."'=>")&&!str_contains($editor,'name="'.$key.'"')),
  'Script cache version'=>str_contains($editor,'assets/editor.js?v=web-0.8.0-phase1a'),
  'Style cache version'=>str_contains($editor,'assets/editor.css?v=web-0.8.0-phase1a'),
  'Responsive CSS'=>str_contains($css,'@media (max-width:630px)'),
  'No photo source overwrite JS'=>!str_contains($js,'photo_path('),
];
foreach($assertions as $label=>$valid){if(!$valid){fwrite(STDERR,"FAIL $label\n");exit(1);}}
echo "Photo Studio UI structure checks passed\n";
