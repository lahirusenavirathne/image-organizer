<?php
declare(strict_types=1);
// CLI regression checks for API authentication, no real DB required.
$path=dirname(__DIR__).'/public/api/v1/index.php';
$contents=file_get_contents($path);
if (!is_string($contents))throw new RuntimeException('API router missing');
foreach (['api_authenticated_user','api_role_permitted','api_read_json_request','drive_trash_photos','drive_trash_folder','is_file($path)','drive_photo($db,$id)'] as $needle) {
    if (!str_contains($contents,$needle)) throw new RuntimeException('Missing API protection / route: '.$needle);
}
echo "PASS: API router includes authentication, permissions, validation, Trash, and protected files\n";
