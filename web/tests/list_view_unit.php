<?php
/** Structure smoke checks for the folder and photo view mode switch. No DB required. */
declare(strict_types=1);
$root=dirname(__DIR__);
$html=(string)file_get_contents($root.'/public/index.php');
$js=(string)file_get_contents($root.'/public/assets/app.js');
$css=(string)file_get_contents($root.'/public/assets/style.css');
$checks=[
 'Library CSS cache version'=>substr_count($html,'assets/style.css?v=web-0.7.4')===2,
 'Library JS cache version'=>str_contains($html,'assets/app.js?v=web-0.7.4'),
 'Photo gallery list styling'=>str_contains($css,'.gallery.list-mode'),
 'Folder list styling'=>str_contains($css,'.folder-grid.list-mode'),
 'Both containers change together'=>str_contains($js,"$('folder-grid').classList.toggle('list-mode',state.listView)") && str_contains($js,"$('gallery').classList.toggle('list-mode',state.listView)"),
 'Toggle handler'=>str_contains($js,"$('view-toggle').addEventListener('click',toggleViewMode)"),
 'ARIA state'=>str_contains($js,"button.setAttribute('aria-pressed',String(state.listView))"),
 'Preference storage fallback'=>str_contains($js,"window.localStorage.setItem(VIEW_MODE_KEY") && str_contains($js,'catch{}'),
];
foreach($checks as $name=>$valid){if(!$valid){fwrite(STDERR,"FAIL $name\n");exit(1);}}
echo "List/grid view structure checks passed\n";
