<?php
/** Regression check for native photo editor link navigation (no MySQL required). */
declare(strict_types=1);
$root=dirname(__DIR__);
$page=(string)file_get_contents($root.'/public/index.php');
$js=(string)file_get_contents($root.'/public/assets/app.js');
$editor=(string)file_get_contents($root.'/public/editor.php');
$checks=[
    'Native editor link exists'=>str_contains($page,'id="edit-current" href="editor.php"'),
    'Gallery JS cache-busted'=>str_contains($page,'assets/app.js?v=web-0.7.1'),
    'Editor JS cache-busted'=>str_contains($editor,'assets/editor.js?v=web-0.7.1'),
    'Photo ID bound to editor link'=>str_contains($js,'edit-current\').href=`editor.php?id=${encodeURIComponent(String(p.id))}`'),
    'No JS-only navigation handler'=>!str_contains($js,'window.location.assign(`editor.php?id='),
];
foreach($checks as $name=>$ok){
    if(!$ok){fwrite(STDERR,"FAIL: $name\n");exit(1);}
}
echo "Editor navigation smoke checks passed\n";
