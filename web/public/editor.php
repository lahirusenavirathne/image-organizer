<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/photo_editor.php';
try{
    if(!installed()){http_response_code(503);exit('Application not installed');}
    $me=auth_require_user('editor');
    $id=int_id($_GET['id']??null);
    $db=pdo();drive_migrate($db);editor_migrate($db);
    $photo=editor_photo($db,$id);$saved=editor_stored($db,$id);
}catch(Throwable){http_response_code(404);exit('Photo unavailable or not authorized');}
function h(string $value):string{return htmlspecialchars($value,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8');}
header('Cache-Control: no-store');
?><!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="csrf-token" content="<?=h(csrf_token())?>"><title>Photo editor · Guia Lanka</title><link rel="stylesheet" href="assets/style.css"><link rel="stylesheet" href="assets/editor.css"></head>
<body class="editor-page"><main class="editor-shell" id="photo-editor" data-photo-id="<?=$id?>" data-revision="<?=$saved['version']?>" data-recipe="<?=h(json_encode($saved['recipe'],JSON_INVALID_UTF8_SUBSTITUTE))?>">
<header class="editor-top"><a href="index.php" class="small-button">← Photo Library</a><div><h1>Photo editor</h1><p class="fine"><?=h($photo['original_name'])?></p></div><span class="fine">Original preserved · Export creates a copy</span></header>
<div class="editor-columns"><section class="editor-view" aria-label="Image preview"><div class="editor-image-holder"><img id="editor-preview" alt="Current adjusted photo preview" fetchpriority="high"><div id="editor-loading" role="status" aria-live="polite">Preparing preview…</div></div><div class="editor-image-actions"><label class="editor-compare"><input type="checkbox" id="editor-before"> Show unedited original</label><span class="fine">Preview generated on the server</span></div></section>
<form class="editor-controls" id="editor-form"><h2>Adjustments</h2>
<label>Crop ratio<select name="crop"><option value="original">Original aspect</option><option value="square">Square (1:1)</option><option value="4:3">4:3</option><option value="3:2">3:2</option><option value="16:9">16:9</option><option value="272:300">Blog thumbnail (272:300)</option></select></label>
<label>Rotate clockwise<select name="rotate"><option value="0">0°</option><option value="90">90°</option><option value="180">180°</option><option value="270">270°</option></select></label>
<?php foreach(['exposure'=>[-100,100],'contrast'=>[-100,100],'highlights'=>[-100,100],'shadows'=>[-100,100], 'saturation'=>[-100,100],'warmth'=>[-100,100],'sharpness'=>[0,100]] as $field=>$range): ?>
<label class="editor-slider"><?=ucfirst($field)?> <output for="edit-<?=$field?>" id="edit-<?=$field?>-value">0</output><input id="edit-<?=$field?>" name="<?=$field?>" type="range" min="<?=$range[0]?>" max="<?=$range[1]?>" step="1" value="0"></label>
<?php endforeach; ?>
<div class="editor-controls-actions"><button class="small-button" id="editor-reset" type="button">Reset sliders</button><button class="button primary" type="button" id="editor-save">Save adjustments</button></div>
<hr><h2>Export edited copy</h2><p class="fine">Choose both dimensions for an exact center-cropped size. 0 preserves aspect ratio. Exports are limited to 2.5 megapixels on shared hosting.</p>
<div class="dimension-fields"><label>Width (px)<input name="width" type="number" min="0" max="2500" value="272" required></label><label>Height (px)<input name="height" type="number" min="0" max="2500" value="300" required></label></div>
<label>Output format<select name="format"><option value="webp">WebP</option><option value="jpg">JPEG</option><option value="png">PNG</option></select></label>
<button class="button primary" id="editor-export" type="button">Download edited copy</button><div role="status" aria-live="polite" id="editor-status"></div>
</form></div></main><script src="assets/editor.js" defer></script></body></html>
