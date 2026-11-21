<?php
/** Run explicitly over DreamHost SSH for the file manager upgrade. */
declare(strict_types=1);
if(PHP_SAPI!=='cli')exit("CLI only\n");
require_once dirname(__DIR__).'/private/drive.php';
if(!installed())exit("Install the application first\n");
drive_migrate(pdo());
echo "File manager database migration complete; existing photos retained.\n";
