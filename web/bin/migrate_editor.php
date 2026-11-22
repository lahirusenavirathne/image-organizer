<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli')exit("CLI only\n");
require_once dirname(__DIR__).'/private/photo_editor.php';
if(!installed())exit("Install application first\n");
editor_migrate(pdo());
echo "Photo editor recipe schema ready; originals unchanged.\n";
