<?php
declare(strict_types=1);
require_once __DIR__.'/drive.php';

class ApiBadRequest extends RuntimeException {}
function api_page_number(mixed $input): int {
    return is_scalar($input) && ctype_digit((string)$input) ? max(1,min(100000,(int)$input)) : 1;
}
function api_page_size(mixed $input): int {
    return is_scalar($input) && ctype_digit((string)$input) ? max(1,min(100,(int)$input)) : 48;
}
function api_folder_filter(mixed $value): ?int {
    if ($value===null || $value==='' || $value==='root') return null;
    $valid = filter_var($value,FILTER_VALIDATE_INT,['options'=>['min_range'=>1]]);
    if ($valid===false) throw new ApiBadRequest('Invalid folder ID');
    return (int)$valid;
}
function api_json_body(string $raw): array {
    if ($raw==='' || strlen($raw)>65536)throw new ApiBadRequest('JSON body must be a non-empty object under 64 KB');
    try {$data=json_decode($raw,true,32,JSON_THROW_ON_ERROR);}catch(JsonException){throw new ApiBadRequest('Malformed JSON body');}
    if (!is_array($data) || array_is_list($data))throw new ApiBadRequest('JSON body must be an object');
    return $data;
}
function api_read_json_request(): array {
    if (strtolower(trim(explode(';',$_SERVER['CONTENT_TYPE']??'')[0])) !== 'application/json') {
        throw new ApiBadRequest('Content-Type must be application/json');
    }
    if ((int)($_SERVER['CONTENT_LENGTH']??0)>65536)throw new ApiBadRequest('Request body exceeds 64 KB');
    $raw=file_get_contents('php://input',false,null,0,65537);
    return api_json_body(is_string($raw)?$raw:'');
}
function api_safe_filename(string $name): string {
    $safe=basename(str_replace('\\','/',$name));
    $safe=preg_replace('/[^A-Za-z0-9._-]/','_', $safe)?:'photo';
    return substr($safe,0,130);
}
function api_photo_id(): int {
    try {return int_id($_GET['id']??null);}catch(Throwable){throw new ApiBadRequest('Valid id required');}
}
function api_photo_public(array $row): array {
    // Exact SHA-256 supports desktop deduplication; disk path and private name are never exposed.
    $keys=['id','original_name','sha256','mime','file_size','width','height','folder_id','camera','taken_at',
           'location','attraction','activities','source_folder','source_url','photographer',
           'copyright_text','license','rights_status','ai_status','ai_note','created_at','updated_at'];
    return array_intersect_key($row,array_fill_keys($keys,true));
}
function api_send(array $data,int $status=200): never {
    respond($data,$status);
}
function api_fail(int $status,string $code,string $message): never {
    api_send(['error'=>['code'=>$code,'message'=>$message]],$status);
}

/** Deterministic, read-only collision test for the desktop companion. */
function api_sync_sha(mixed $value): string {
    if (!is_string($value) || !preg_match('/\A[a-f0-9]{64}\z/D',$value))
        throw new ApiBadRequest('sha256 must be 64 lowercase hexadecimal characters');
    return $value;
}
function api_sync_decision(array $matches, string $sha, string $name): array {
    foreach ($matches as $row) {
        if (hash_equals((string)$row['sha256'],$sha))
            return ['decision'=>'duplicate','id'=>(int)$row['id'],'sha256'=>$sha];
    }
    foreach ($matches as $row) {
        if ((string)$row['original_name']===$name)
            return ['decision'=>'conflict','id'=>(int)$row['id'],'sha256'=>$row['sha256']];
    }
    return ['decision'=>'upload','id'=>null,'sha256'=>null];
}
function api_sync_match(PDO $db, ?int $folder, string $sha, string $name): array {
    $stmt=$db->prepare('SELECT id,original_name,sha256 FROM photos WHERE deleted_at IS NULL AND folder_id '
        .($folder===null?'IS NULL':'=?').' AND (sha256=? OR original_name=?) ORDER BY CASE WHEN sha256=? THEN 0 ELSE 1 END, id ASC LIMIT 30');
    $stmt->execute($folder===null?[$sha,$name,$sha]:[$folder,$sha,$name,$sha]);
    return api_sync_decision($stmt->fetchAll(),$sha,$name);
}
