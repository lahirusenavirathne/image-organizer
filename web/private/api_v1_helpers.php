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

/** Photo metadata bridge: no replacement, no deletion, and no automatic rights inference. */
function api_metadata_limits(): array {
    return ['location'=>150,'attraction'=>190,'activities'=>500,'source_url'=>1000,
            'photographer'=>255,'copyright_text'=>1000,'license'=>255,'rights_status'=>32];
}
function api_metadata_fillable(array $current, array $incoming): array {
    if (!$incoming || count($incoming)>8) throw new ApiBadRequest('Provide at least one supported metadata field');
    $fillable=[];$ignored=[];
    foreach ($incoming as $key=>$value) {
        $limits=api_metadata_limits();
        if (!isset($limits[$key]) || !is_string($value)) throw new ApiBadRequest('Unsupported metadata field');
        $clean=clean_text($value,$limits[$key]);
        if ($clean==='' || strlen($value)>$limits[$key]*4) throw new ApiBadRequest('Metadata value is empty or too long');
        if ($key==='source_url' && (!filter_var($clean,FILTER_VALIDATE_URL) ||
             !in_array(strtolower((string)parse_url($clean,PHP_URL_SCHEME)),['http','https'],true)))
            throw new ApiBadRequest('source_url must be HTTP(S)');
        if ($key==='rights_status' && !in_array($clean,['Verified','Permission required'],true))
            throw new ApiBadRequest('Invalid explicit rights status');
        $old=trim((string)($current[$key]??''));
        $empty=$old==='' || ($key==='rights_status' && $old==='Unknown');
        $reviewed=($current['ai_status']??'')==='reviewed' &&
                  in_array($key,['location','attraction','activities','rights_status'],true);
        if ($empty && !$reviewed) $fillable[$key]=$clean;
        else $ignored[]=$key;
    }
    return ['fillable'=>$fillable,'ignored'=>$ignored];
}
function api_metadata_fill(PDO $db,int $id,string $sha,array $incoming): array {
    api_sync_sha($sha);
    $db->beginTransaction();
    try {
        $stmt=$db->prepare('SELECT * FROM photos WHERE id=? AND deleted_at IS NULL FOR UPDATE');
        $stmt->execute([$id]);$record=$stmt->fetch();
        if (!$record) throw new ApiBadRequest('Photo does not exist');
        if (!hash_equals((string)$record['sha256'],$sha))
            throw new ApiBadRequest('Metadata fingerprint differs from the actual photo');
        $decision=api_metadata_fillable($record,$incoming);
        if ($decision['fillable']) {
            $set=[];$args=[];
            foreach ($decision['fillable'] as $field=>$value) {
                $set[]=$field.'=?';$args[]=$value;
            }
            $args[]=$id;
            $db->prepare('UPDATE photos SET '.implode(',',$set).' WHERE id=?')->execute($args);
        }
        $db->commit();
        return ['updated'=>array_keys($decision['fillable']),'ignored'=>$decision['ignored']];
    } catch(Throwable $e) {$db->rollBack();throw $e;}
}
