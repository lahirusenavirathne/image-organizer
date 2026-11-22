<?php
/** Regression checks for compact Phase 1A Undo/Redo controls. */
declare(strict_types=1);
$root=dirname(__DIR__);
$css=(string)file_get_contents($root.'/public/assets/editor.css');
$page=(string)file_get_contents($root.'/public/editor.php');
$cases=[
    'Undo button exists'=>str_contains($page,'id="editor-undo"'),
    'Redo button exists'=>str_contains($page,'id="editor-redo"'),
    'Header buttons constrained'=>str_contains($css,'.editor-page .studio-header-actions .studio-button'),
    'Auto width for header'=>str_contains($css,'width:auto;'),
    'Header can wrap'=>str_contains($css,'flex-wrap:wrap;'),
    'Tablet row layout'=>str_contains($css,'order:4;'),
    'Versioned CSS'=>str_contains($page,'assets/editor.css?v=web-0.8.0-phase1a.1'),
];
foreach($cases as $name=>$ok){if(!$ok){fwrite(STDERR,"FAIL: $name\n");exit(1);}}
echo "Phase1A compact header checks passed\n";
