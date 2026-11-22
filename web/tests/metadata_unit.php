<?php
/** Fast pure metadata policy checks; live database integration is required on DreamHost. */
declare(strict_types=1);
require_once dirname(__DIR__).'/private/api_v1_helpers.php';
function verify_m(bool $pass,string $name):void { if(!$pass)throw new RuntimeException($name); echo "PASS: $name\n"; }
$base=['location'=>'','attraction'=>'Existing human name','activities'=>'',
       'source_url'=>'','photographer'=>'','copyright_text'=>'',
       'license'=>'','rights_status'=>'Unknown','ai_status'=>'suggested'];
$x=api_metadata_fillable($base,['location'=>'Kandy','attraction'=>'Wrong','rights_status'=>'Verified']);
verify_m($x['fillable']===['location'=>'Kandy','rights_status'=>'Verified'],'only empty metadata is filled');
verify_m($x['ignored']===['attraction'],'conflicting value ignored');
$reviewed=$base;$reviewed['ai_status']='reviewed';
$x=api_metadata_fillable($reviewed,['location'=>'Kandy','rights_status'=>'Verified','photographer'=>'Owner']);
verify_m($x['fillable']===['photographer'=>'Owner'],'reviewed tags and rights protected');
try{api_metadata_fillable($base,['source_url'=>'javascript:alert(1)']);throw new RuntimeException('invalid URL accepted');}
catch(ApiBadRequest){verify_m(true,'rejects non-http links');}
try{api_metadata_fillable($base,['folder_id'=>'42']);throw new RuntimeException('folder_id allowed');}
catch(ApiBadRequest){verify_m(true,'no structural changes via metadata route');}
