<?php
/** Structure checks for Phase 2A studio visual redesign. */
declare(strict_types=1);
$root=dirname(__DIR__);
$page=(string)file_get_contents($root.'/public/editor.php');
$js=(string)file_get_contents($root.'/public/assets/editor.js');
$css=(string)file_get_contents($root.'/public/assets/editor.css');
$checks=[
 'Professional workspace tabs'=>str_contains($page,'class="studio-workspace-tabs"'),
 'Working tabs wired to tool navigation'=>str_contains($js,".studio-tool[data-jump],.studio-workspace-tab[data-jump]"),
 'Histogram in inspector'=>str_contains($page,'class="studio-histogram"'),
 'Histogram remains visible on desktop'=>str_contains($css,'.editor-page .studio-histogram')&&str_contains($css,'position:sticky;top:0'),
 'HSL palette tabs'=>str_contains($page,'data-hsl-select='),
 'HSL palette event listeners'=>str_contains($js,'showColorFamily(button.dataset.hslSelect)'),
 'Only one color family visible'=>str_contains($js,'group.hidden=!selected'),
 'Camera preview and crop unchanged'=>str_contains($page,'id="editor-preview"')&&str_contains($page,'id="editor-crop-box"'),
 'Library save and export buttons unchanged'=>str_contains($page,'id="editor-save-copy"')&&str_contains($page,'id="editor-export"'),
 'New CSS version'=>str_contains($page,'assets/editor.css?v=web-0.9.1-studio-ui'),
 'New JS version'=>str_contains($page,'assets/editor.js?v=web-0.9.1-studio-ui')
];
foreach($checks as $label=>$ok){if(!$ok){fwrite(STDERR,"FAIL $label\n");exit(1);}}
echo "Professional Studio visual structure checks passed\n";
