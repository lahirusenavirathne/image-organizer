<?php
declare(strict_types=1);
require_once dirname(__DIR__).'/private/images.php';
try{
    if(!installed())respond(['error'=>'Application not installed'],503);
    require_login();
    $action=(string)($_GET['action']??$_POST['action']??'list');
    $con=pdo();
    if($_SERVER['REQUEST_METHOD']==='GET') {
        if($action==='list'){
            $page=max(1,min(999999,(int)($_GET['page']??1)));$size=48;
            $wheres=[];$params=[];
            $q=clean_text($_GET['q']??'',120);
            if($q!==''){
                $like='%'.str_replace(['\\','%','_'],['\\\\','\\%','\\_'],$q).'%';
                $wheres[]='(original_name LIKE ? OR location LIKE ? OR attraction LIKE ? OR activities LIKE ? OR source_folder LIKE ? OR photographer LIKE ?)';
                array_push($params,$like,$like,$like,$like,$like,$like);
            }
            $loc=clean_text($_GET['location']??'',150);
            if($loc!==''){$wheres[]='location=?';$params[]=$loc;}
            $activity=clean_text($_GET['activity']??'',120);
            if($activity!==''){$wheres[]='activities LIKE ?';$params[]='%'.$activity.'%';}
            $rights=clean_text($_GET['rights']??'',32);
            if(in_array($rights,['Unknown','Verified','Permission required'],true)){$wheres[]='rights_status=?';$params[]=$rights;}
            if(($_GET['view']??'')==='review'){$wheres[]="ai_status='suggested'";}
            $where=$wheres?' WHERE '.implode(' AND ',$wheres):'';
            $st=$con->prepare('SELECT COUNT(*) FROM photos'.$where);$st->execute($params);$total=(int)$st->fetchColumn();
            $page=max(1,min($page,max(1,(int)ceil($total/$size))));
            $st=$con->prepare('SELECT id,original_name,mime,width,height,file_size,location,attraction,activities,rights_status,photographer,source_folder,source_url,copyright_text,license,ai_status,ai_note,created_at FROM photos'.$where.' ORDER BY id DESC LIMIT '.$size.' OFFSET '.(($page-1)*$size));
            $st->execute($params);$photos=$st->fetchAll();
            $locs=$con->query("SELECT DISTINCT location FROM photos WHERE location<>'' ORDER BY location LIMIT 300")->fetchAll(PDO::FETCH_COLUMN);
            respond(['photos'=>$photos,'page'=>$page,'pages'=>max(1,(int)ceil($total/$size)),'total'=>$total,'locations'=>$locs]);
        }
        if($action==='similar'){
            $id=int_id($_GET['id']??null);$st=$con->prepare('SELECT * FROM photos WHERE id=?');$st->execute([$id]);$ref=$st->fetch();if(!$ref)respond(['error'=>'Photo not found'],404);
            $rows=$con->query('SELECT id,sha256,dhash,color_sig,original_name,location,attraction FROM photos ORDER BY id DESC LIMIT 25000')->fetchAll();
            $scores=[];foreach($rows as $row){
                if((int)$row['id']===$id)continue;
                $exact=hash_equals($ref['sha256'],$row['sha256']);
                $distance=hamming_hex($ref['dhash'],$row['dhash']);
                if($exact||($distance<=10 && color_distance($ref['color_sig'],$row['color_sig'])<=100))$scores[]=['id'=>(int)$row['id'],'name'=>$row['original_name'],'location'=>$row['location'],'attraction'=>$row['attraction'],'distance'=>$distance,'type'=>$exact?'Exact duplicate':($distance<=5?'Likely edited copy':'Visually similar (review)')];
            }
            usort($scores,fn($a,$b)=>(($a['type']==='Exact duplicate'?0:1)<=>($b['type']==='Exact duplicate'?0:1))?:($a['distance']<=>$b['distance']));
            respond(['matches'=>array_slice($scores,0,30),'reference'=>$id,'note'=>'Perceptual hashes are good for edits/resizes; they may not match different angles of an attraction. Review each result.']);
        }
        respond(['error'=>'Unknown read action'],404);
    }
    method_post();verify_csrf();
    if($action==='upload'){
        $file=$_FILES['photo']??null;
        if(!$file||($file['error']??UPLOAD_ERR_NO_FILE)!==UPLOAD_ERR_OK||!is_uploaded_file($file['tmp_name']??''))throw new RuntimeException('Upload failed. Check PHP upload_max_filesize and post_max_size on DreamHost.');
        $record=ingest_image($file['tmp_name'],(string)$file['name'],'Browser upload',true);respond(['success'=>true,'photo'=>$record]);
    }
    if($action==='import_inbox'){
        ensure_dirs();$root=realpath(private_path('incoming'));
        if(!$root)throw new RuntimeException('SFTP incoming folder missing');
        $result=[];$fail=[];
        $iter=new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root,FilesystemIterator::SKIP_DOTS));
        foreach($iter as $file){
            if(count($result)+count($fail)>=BATCH_SIZE)break;
            if(!$file->isFile()||$file->isLink()||!preg_match('/\.(jpg|jpeg|png|webp)$/i',$file->getFilename()))continue;
            $real=realpath($file->getPathname());
            if(!$real || !str_starts_with($real,$root.DIRECTORY_SEPARATOR))continue;
            try{$result[]=ingest_image($real,$file->getFilename(),'SFTP incoming/'.substr($real,strlen($root)+1),false);}
            catch(Throwable $e){$fail[]=safe_basename($file->getFilename()).': '.$e->getMessage();quarantine_import($real);}
        }
        respond(['success'=>true,'imported'=>count($result),'failures'=>$fail,'batch_limit'=>BATCH_SIZE]);
    }
    if($action==='save'){
        $id=int_id($_POST['id']??null);
        $fields=['location'=>150,'attraction'=>190,'activities'=>500,'source_folder'=>500,'source_url'=>1000,'photographer'=>255,'copyright_text'=>1000,'license'=>255];
        $data=[];foreach($fields as $key=>$max)$data[$key]=clean_text($_POST[$key]??'',$max);
        if($data['source_url']!==''&&!filter_var($data['source_url'],FILTER_VALIDATE_URL))throw new RuntimeException('Enter a valid source URL');
        $rights=(string)($_POST['rights_status']??'Unknown');if(!in_array($rights,['Unknown','Verified','Permission required'],true))throw new RuntimeException('Invalid rights status');
        $st=$con->prepare("UPDATE photos SET location=?,attraction=?,activities=?,source_folder=?,source_url=?,photographer=?,copyright_text=?,license=?,rights_status=?,ai_status='reviewed' WHERE id=?");
        $st->execute([...array_values($data),$rights,$id]);respond(['success'=>true]);
    }
    if($action==='cloud_ai'){
        $id=int_id($_POST['id']??null);
        if(($_POST['confirm']??'')!=='yes')throw new RuntimeException('Explicit consent required before image upload to OpenAI');
        $key=(string)(config()['openai_api_key']??'');if($key==='')throw new RuntimeException('Cloud AI not configured. Add your API key to private/config.php on the server.');
        if(!function_exists('curl_init'))throw new RuntimeException('PHP cURL extension is required for cloud tagging');
        $st=$con->prepare('SELECT * FROM photos WHERE id=?');$st->execute([$id]);$row=$st->fetch();if(!$row)throw new RuntimeException('Photo not found');
        if($row['ai_status']==='reviewed')throw new RuntimeException('Manually reviewed metadata is protected. Select an unreviewed photo.');
        // Generate a resized temporary image; never upload EXIF or the original file.
        [$temp]=make_export($row,768,768,'jpg');
        try {$encoded=base64_encode((string)file_get_contents($temp));}finally{@unlink($temp);}
        $prompt='Classify this travel photo conservatively. Return exactly one JSON object with keys "activities" (up to 4 short categories as array), "attraction" (name if visually distinctive or empty), "location" (area if supported visually or empty), "note" (brief uncertainty). Do not identify people or infer copyright, photographer, web source or precise location from generic scenery. Sri Lanka-specific possibilities include Sigiriya, Nine Arch Bridge, Galle Fort, Dambulla, Ramboda Falls, Ravana Falls, Yala and village experiences.';
        $request=['model'=>'gpt-4.1-mini','input'=>[['role'=>'user','content'=>[['type'=>'input_text','text'=>$prompt],['type'=>'input_image','image_url'=>'data:image/jpeg;base64,'.$encoded]]]],'max_output_tokens'=>300];
        $h=curl_init('https://api.openai.com/v1/responses');curl_setopt_array($h,[CURLOPT_POST=>true,CURLOPT_HTTPHEADER=>['Authorization: Bearer '.$key,'Content-Type: application/json'],CURLOPT_POSTFIELDS=>json_encode($request),CURLOPT_RETURNTRANSFER=>true,CURLOPT_TIMEOUT=>65]);
        $raw=curl_exec($h);$status=(int)curl_getinfo($h,CURLINFO_HTTP_CODE);$err=curl_error($h);curl_close($h);
        if(!is_string($raw)||$status<200||$status>=300)throw new RuntimeException('OpenAI classification failed (HTTP '.$status.'). '.$err);
        $response=json_decode($raw,true);$text='';foreach(($response['output']??[])as $unit)foreach(($unit['content']??[])as $chunk)if(($chunk['type']??'')==='output_text')$text.=$chunk['text'];
        $data=json_decode(trim(preg_replace('/^```(?:json)?|```$/m','',$text)??''),true);
        if(!is_array($data))throw new RuntimeException('AI response could not be interpreted');
        $activity=is_array($data['activities']??null)?implode(', ',array_slice(array_filter($data['activities'],'is_string'),0,4)):'';
        $location=clean_text($data['location']??'',150);$attraction=clean_text($data['attraction']??'',190);$note=clean_text($data['note']??'',400);
        $st=$con->prepare("UPDATE photos SET activities=?,attraction=?,location=IF(location='',?,location),ai_status='suggested',ai_note=? WHERE id=? AND ai_status<>'reviewed'");$st->execute([clean_text($activity,500),$attraction,$location,$note,$id]);
        respond(['success'=>true,'result'=>['activities'=>$activity,'attraction'=>$attraction,'location'=>$location,'note'=>$note]]);
    }
    respond(['error'=>'Unknown action'],404);
}catch(Throwable $e){error_log('GLPM API: '.get_class($e).': '.$e->getMessage());$code=http_response_code();respond(['error'=>$e instanceof PDOException?'Database error. Check hosting configuration.':$e->getMessage()],$code>=400?$code:400);}
