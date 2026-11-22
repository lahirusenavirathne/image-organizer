<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/photo_editor.php';
try {
    if (!installed()) {http_response_code(503);exit('Application not installed');}
    $me=auth_require_user('editor');
    $id=int_id($_GET['id']??null);
    $db=pdo();drive_migrate($db);editor_migrate($db);
    $photo=editor_photo($db,$id);$saved=editor_stored($db,$id);
} catch(Throwable $e) {
    error_log('GLPM photo editor page: '.get_class($e));
    $status=http_response_code();
    if ($status===401 || $status===403) exit('Please sign in with an Editor or Administrator account to edit photos.');
    if ($e instanceof PDOException || str_contains($e->getMessage(),'migration') || str_contains($e->getMessage(),'schema')) {
        http_response_code(503);
        exit('The photo editor database is not ready. Run web/bin/migrate_editor.php from SSH and check PHP logs.');
    }
    http_response_code(404);
    exit('Photo unavailable. Check the photo ID and confirm it is not in Trash.');
}
function h(string $value):string {return htmlspecialchars($value,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8');}
header('Cache-Control: no-store');
?><!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#141b19">
<meta name="csrf-token" content="<?=h(csrf_token())?>">
<title>Photo Studio · <?=h((string)$photo['original_name'])?> · Guia Lanka</title>
<link rel="stylesheet" href="assets/style.css?v=web-0.7.2">
<link rel="stylesheet" href="assets/editor.css?v=web-0.7.5">
</head>
<body class="editor-page">
<div class="editor-shell" id="photo-editor" data-photo-id="<?=$id?>" data-revision="<?=h((string)$saved['version'])?>" data-recipe="<?=h(json_encode($saved['recipe'],JSON_INVALID_UTF8_SUBSTITUTE))?>">
<header class="studio-header">
  <div class="studio-brand"><span class="studio-mark" aria-hidden="true">GL</span><span class="studio-brand-copy"><strong>Guia Lanka</strong><small>PHOTO STUDIO</small></span></div>
  <span class="studio-header-divider" aria-hidden="true"></span>
  <a class="studio-back" href="index.php" aria-label="Return to photo library">← <span>Library</span></a>
  <div class="studio-document"><span class="studio-document-label">NOW EDITING</span><span class="studio-document-name" title="<?=h((string)$photo['original_name'])?>"><?=h((string)$photo['original_name'])?></span></div>
  <div class="studio-header-actions">
    <span id="editor-save-state" class="studio-save-state" role="status" aria-live="polite"><span class="studio-state-dot" aria-hidden="true"></span> Ready to edit</span>
    <button id="editor-save" type="button" class="studio-button studio-button-outline">Save adjustments</button>
    <button id="editor-top-export" type="button" class="studio-button studio-button-primary">Export image <span aria-hidden="true">↗</span></button>
  </div>
</header>
<div class="studio-workspace">
  <nav class="studio-tools" aria-label="Editor tools">
    <span class="studio-tools-heading">TOOLS</span>
    <button class="studio-tool active" type="button" data-jump="panel-light" aria-label="Light adjustments" aria-current="true"><span class="studio-tool-icon" aria-hidden="true">☼</span><span>Light</span></button>
    <button class="studio-tool" type="button" data-jump="panel-color" aria-label="Color adjustments"><span class="studio-tool-icon" aria-hidden="true">◒</span><span>Color</span></button>
    <button class="studio-tool" type="button" data-jump="panel-crop" aria-label="Crop and rotate"><span class="studio-tool-icon" aria-hidden="true">⊞</span><span>Crop</span></button>
    <button class="studio-tool" type="button" data-jump="panel-detail" aria-label="Detail and sharpening"><span class="studio-tool-icon" aria-hidden="true">✧</span><span>Detail</span></button>
    <span class="studio-tools-spacer"></span>
    <button class="studio-tool" type="button" data-jump="panel-export" aria-label="Export settings"><span class="studio-tool-icon" aria-hidden="true">↧</span><span>Export</span></button>
  </nav>
  <main class="studio-canvas" aria-label="Photo editing workspace">
    <div class="studio-canvas-head"><div><span class="studio-eyebrow">PREVIEW CANVAS</span><h1>Photo editor</h1></div><span class="studio-canvas-hint">Non-destructive editing <span aria-hidden="true">·</span> Original protected</span></div>
    <div class="editor-image-holder">
      <div class="studio-image-backdrop" aria-hidden="true"></div>
      <img id="editor-preview" alt="Current adjusted photo preview" fetchpriority="high">
      <div id="editor-loading" role="status" aria-live="polite">Preparing preview…</div>
    </div>
    <div class="studio-canvas-foot">
      <label class="studio-before-toggle" for="editor-before"><input type="checkbox" id="editor-before"><span aria-hidden="true" class="studio-toggle-track"></span><span>Show original</span></label>
      <span class="studio-foot-info">Preview generated privately on DreamHost</span>
      <span class="studio-foot-format">Photo #<?=$id?></span>
    </div>
    <div class="studio-canvas-status" id="editor-preview-help">Adjust the controls to preview changes. Exporting always creates a new file.</div>
  </main>
  <aside class="studio-inspector" aria-label="Photo adjustments">
    <div class="studio-panel-intro"><div><span class="studio-eyebrow">WORKSPACE</span><h2>Adjustments</h2></div><span class="studio-panel-version">STUDIO v0.7.5</span></div>
    <form id="editor-form" class="editor-controls">
      <details id="panel-light" class="studio-section" open>
        <summary><span><span class="studio-section-symbol" aria-hidden="true">☼</span> Light</span><span class="studio-section-summary">Tone &amp; exposure</span></summary>
        <div class="studio-section-body">
        <?php foreach(['exposure'=>[-100,100],'contrast'=>[-100,100],'highlights'=>[-100,100],'shadows'=>[-100,100]] as $key=>$range): ?>
          <label class="editor-slider"><span class="studio-slider-heading"><span><?=ucfirst($key)?></span><output for="edit-<?=$key?>" id="edit-<?=$key?>-value">0</output></span><input id="edit-<?=$key?>" name="<?=$key?>" type="range" min="<?=$range[0]?>" max="<?=$range[1]?>" step="1" value="0"></label>
        <?php endforeach; ?>
        </div>
      </details>
      <details id="panel-color" class="studio-section" open>
        <summary><span><span class="studio-section-symbol" aria-hidden="true">◒</span> Color</span><span class="studio-section-summary">Balance &amp; intensity</span></summary>
        <div class="studio-section-body">
        <?php foreach(['saturation'=>[-100,100],'warmth'=>[-100,100]] as $key=>$range): ?>
          <label class="editor-slider"><span class="studio-slider-heading"><span><?=ucfirst($key)?></span><output for="edit-<?=$key?>" id="edit-<?=$key?>-value">0</output></span><input id="edit-<?=$key?>" name="<?=$key?>" type="range" min="<?=$range[0]?>" max="<?=$range[1]?>" step="1" value="0"></label>
        <?php endforeach; ?>
        </div>
      </details>
      <details id="panel-crop" class="studio-section" open>
        <summary><span><span class="studio-section-symbol" aria-hidden="true">⊞</span> Crop &amp; rotate</span><span class="studio-section-summary">Composition</span></summary>
        <div class="studio-section-body studio-selects">
          <label>Aspect ratio<select name="crop"><option value="original">Original proportions</option><option value="square">Square · 1:1</option><option value="4:3">Landscape · 4:3</option><option value="3:2">Classic · 3:2</option><option value="16:9">Widescreen · 16:9</option><option value="272:300">Blog thumbnail · 272:300</option></select></label>
          <label>Rotate clockwise<select name="rotate"><option value="0">0° · Original</option><option value="90">90°</option><option value="180">180°</option><option value="270">270°</option></select></label>
          <p class="studio-section-note">Crop is centered in this release. Freehand crop is not yet available.</p>
        </div>
      </details>
      <details id="panel-detail" class="studio-section" open>
        <summary><span><span class="studio-section-symbol" aria-hidden="true">✧</span> Details</span><span class="studio-section-summary">Finishing</span></summary>
        <div class="studio-section-body">
          <label class="editor-slider"><span class="studio-slider-heading"><span>Sharpness</span><output for="edit-sharpness" id="edit-sharpness-value">0</output></span><input id="edit-sharpness" name="sharpness" type="range" min="0" max="100" step="1" value="0"></label>
          <p class="studio-section-note">Keep sharpening subtle for natural wildlife textures.</p>
        </div>
      </details>
      <div class="studio-section-actions"><button type="button" class="studio-button studio-button-muted" id="editor-reset">↺ Reset all adjustments</button></div>
      <section id="panel-export" class="studio-export" aria-labelledby="export-section-title">
        <span class="studio-eyebrow">FINISH &amp; DOWNLOAD</span><h2 id="export-section-title">Export edited copy</h2>
        <p class="studio-section-note">Original stays in your photo library. Choose both dimensions for an exact center crop.</p>
        <div class="dimension-fields">
          <label>Width (px)<input name="width" type="number" min="0" max="2500" value="272" required></label>
          <label>Height (px)<input name="height" type="number" min="0" max="2500" value="300" required></label>
        </div>
        <label class="studio-export-format">File format<select name="format"><option value="webp">WebP · Web optimized</option><option value="jpg">JPEG</option><option value="png">PNG</option></select></label>
        <label class="studio-copy-name" for="editor-copy-name">Save copy with filename
          <input id="editor-copy-name" name="copy_name" type="text" minlength="1" maxlength="180" required
                 value="<?=h(editor_copy_suggested_name((string)$photo['original_name']))?>"
                 aria-describedby="editor-copy-help">
        </label>
        <p class="studio-section-note" id="editor-copy-help">Both actions use the format and dimensions above. Save as copy adds a new photograph to the same library folder, keeping the original and its metadata intact.</p>
        <div class="studio-copy-buttons">
          <button class="studio-button studio-button-primary" id="editor-save-copy" type="button">Save as copy</button>
          <button class="studio-button studio-button-outline" id="editor-export" type="button">Download edited copy <span aria-hidden="true">↗</span></button>
        </div>
        <p class="studio-section-note">Maximum 2.5 megapixels per export or saved copy on shared hosting.</p>
      </section>
      <div role="status" aria-live="polite" id="editor-status" class="studio-message"></div>
    </form>
  </aside>
</div>
</div>
<script src="assets/editor.js?v=web-0.7.5" defer></script>
</body></html>
