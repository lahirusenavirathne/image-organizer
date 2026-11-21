<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/api_tokens.php';
require_once dirname(__DIR__).'/private/api_v1_helpers.php';
function check(bool $value,string $name): void {if(!$value)throw new RuntimeException('FAILED: '.$name);echo "PASS: $name\n";}
$valid='glpm_v1_'.str_repeat('a',64);
check(api_token_format($valid),'256-bit token format');
check(!api_token_format('short'),'reject malformed token');
check(api_bearer_from_header('Bearer '.$valid)===$valid,'parse bearer header');
check(api_bearer_from_header('Basic '.$valid)===null,'reject basic authentication');
check(api_bearer_from_header('Bearer '.$valid.' extra')===null,'reject token trailing garbage');
check(api_bearer_from_header(null)===null,'no absent authorization');
check(api_role_permitted('viewer','read','read'),'viewer can read');
check(!api_role_permitted('viewer','write','write'),'viewer cannot write');
check(!api_role_permitted('editor','read','write'),'read scope cannot write');
check(api_role_permitted('editor','write','write'),'editor writes');
check(api_role_permitted('admin','write','write'),'admin writes');
check(!api_role_permitted('disabled','write','read'),'unknown role denied');
check(api_page_size('1000')===100,'pagination capped at 100');
check(api_page_size('not-a-number')===48,'invalid size default');
check(api_page_number('-2')===1,'page lower bound');
check(api_folder_filter('root')===null,'root folder selection');
check(api_folder_filter('42')===42,'folder id selection');
try{api_json_body('{');throw new RuntimeException('json accepted malformed');}catch(ApiBadRequest $e){check(true,'malformed JSON rejected');}
check(api_json_body('{"foo":1}')['foo']===1,'JSON object parsed');
check(api_safe_filename('../photo.jpg')==='photo.jpg','download filename sanitized');
