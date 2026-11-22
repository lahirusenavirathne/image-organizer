<?php
/** Regression checks for existing photo metadata projection and the safe browser rendering. */
declare(strict_types=1);
$root=dirname(__DIR__);
$api=(string)file_get_contents($root.'/public/drive_api.php');
$html=(string)file_get_contents($root.'/public/index.php');
$js=(string)file_get_contents($root.'/public/assets/app.js');
$css=(string)file_get_contents($root.'/public/assets/style.css');
$checks=[
 'Camera returned by API'=>str_contains($api,'p.camera'),
 'Capture date returned by API'=>str_contains($api,'p.taken_at'),
 'Fingerprint returned by API'=>str_contains($api,'p.sha256'),
 'Catalog update date returned by API'=>str_contains($api,'p.updated_at'),
 'Dedicated file facts panel'=>str_contains($html,'id="detail-facts"'),
 'File facts populated'=>str_contains($js,'populatePhotoFacts(p);'),
 'Date, camera and file metadata list'=>str_contains($js,'photoListMetadata(p)'),
 'Missing data explicit'=>str_contains($js,"'Not recorded'"),
 'Untrusted content rendered safely'=>str_contains($js,'description.textContent=knownText(value);'),
 'List metadata CSS'=>str_contains($css,'.gallery.list-mode .photo-list-fields'),
 'Photo details CSS'=>str_contains($css,'.detail-facts-section'),
 'Style version updated'=>substr_count($html,'assets/style.css?v=web-0.7.4')===2,
 'Script version updated'=>str_contains($html,'assets/app.js?v=web-0.7.4'),
];
foreach($checks as $title=>$valid){if(!$valid){fwrite(STDERR,"FAIL $title\n");exit(1);}}
echo "Rich photo metadata checks passed\n";
