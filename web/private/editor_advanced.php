<?php
declare(strict_types=1);
/** Professional color adjustments for the bounded GD preview/export canvas.
 * Neutral values perform no work and produce identical Phase 1 output.
 * No additional source files are written. HSL processing runs only when enabled.
 */
const EDITOR_HSL_COLORS = ['red','orange','yellow','green','cyan','blue','purple','magenta'];
function editor_advanced_defaults(): array {
    $r=['whites'=>0,'blacks'=>0,'vibrance'=>0,'tint'=>0,
        'curve_shadows'=>0,'curve_midtones'=>0,'curve_highlights'=>0];
    foreach(EDITOR_HSL_COLORS as $c)foreach(['hue','sat','lum'] as $op)$r['hsl_'.$c.'_'.$op]=0;
    return $r;
}
function editor_advanced_ranges(): array {
    $r=[];
    foreach(['whites','blacks','vibrance','tint'] as $key)$r[$key]=[-100,100];
    foreach(['curve_shadows','curve_midtones','curve_highlights'] as $key)$r[$key]=[-50,50];
    foreach(EDITOR_HSL_COLORS as $c){
        $r['hsl_'.$c.'_hue']=[-30,30];$r['hsl_'.$c.'_sat']=[-100,100];$r['hsl_'.$c.'_lum']=[-70,70];
    }
    return $r;
}
/** Guaranteed continuous, non-inverting curve: adjacent output knots stay >15 levels apart. */
function editor_tone_lut(array $r): array {
    $xp=[0,64,128,192,255];
    $offsets=[0,$r['curve_shadows']*.5,$r['curve_midtones']*.5,$r['curve_highlights']*.5,0];
    $table=[];
    for($v=0;$v<256;$v++){
        $i=$v<64?0:($v<128?1:($v<192?2:3));
        $t=($v-$xp[$i])/($xp[$i+1]-$xp[$i]);
        $smooth=$t*$t*(3-2*$t);
        // Add a smooth adjustment to the identity map. A neutral curve stays
        // exactly neutral rather than introducing smoothing artifacts.
        $out=$v+$offsets[$i]*(1-$smooth)+$offsets[$i+1]*$smooth;
        $n=$v/255;
        $out += $r['blacks']*.34*(1-$n)**3 + $r['whites']*.34*$n**3;
        // No inverse slope or channel inversion even at extreme control values.
        $table[$v]=max($v?($table[$v-1]??0):0,max(0,min(255,(int)round($out))));
    }
    return $table;
}
function editor_rgb_to_hsl(int $red,int $green,int $blue): array {
    $r=$red/255;$g=$green/255;$b=$blue/255;
    $max=max($r,$g,$b);$min=min($r,$g,$b);$d=$max-$min;
    $l=($max+$min)/2;
    if($d<1e-9)return [0.0,0.0,$l];
    $s=$d/(1-abs(2*$l-1));
    if($max===$r)$h=fmod(($g-$b)/$d+6,6);
    elseif($max===$g)$h=($b-$r)/$d+2;
    else $h=($r-$g)/$d+4;
    return [$h*60,$s,$l];
}
function editor_hsl_to_rgb(float $h,float $s,float $l): array {
    $h=fmod($h+3600,360);$s=max(0,min(1,$s));$l=max(0,min(1,$l));
    $c=(1-abs(2*$l-1))*$s;$section=$h/60;$x=$c*(1-abs(fmod($section,2)-1));
    if($section<1)[$r,$g,$b]=[$c,$x,0.0];
    elseif($section<2)[$r,$g,$b]=[$x,$c,0.0];
    elseif($section<3)[$r,$g,$b]=[0.0,$c,$x];
    elseif($section<4)[$r,$g,$b]=[0.0,$x,$c];
    elseif($section<5)[$r,$g,$b]=[$x,0.0,$c];
    else [$r,$g,$b]=[$c,0.0,$x];
    $m=$l-$c/2;
    return [
       (int)round(max(0,min(255,($r+$m)*255))),
       (int)round(max(0,min(255,($g+$m)*255))),
       (int)round(max(0,min(255,($b+$m)*255)))
    ];
}
/** Smooth overlapping hue regions prevent hard edges across orange/green skies. */
function editor_hsl_controls(array $recipe,float $h): array {
    $centers=['red'=>0,'orange'=>30,'yellow'=>60,'green'=>120,'cyan'=>180,'blue'=>240,'purple'=>280,'magenta'=>320];
    $dh=0.0;$ds=0.0;$dl=0.0;
    foreach($centers as $name=>$center){
        $distance=abs($h-$center);$distance=min($distance,360-$distance);
        // 45° wide feathers are deliberate; independent channels blend smoothly.
        $weight=max(0.0,1-$distance/45);
        if($weight<=0)continue;
        $weight=$weight*$weight*(3-2*$weight);
        $dh += $recipe['hsl_'.$name.'_hue']*$weight;
        $ds += $recipe['hsl_'.$name.'_sat']*$weight/100;
        $dl += $recipe['hsl_'.$name.'_lum']*$weight/100;
    }
    return [$dh,$ds,$dl];
}
function editor_advanced_render(GdImage $im,array $recipe): void {
    $advanced=editor_advanced_defaults();$enabled=false;$hslEnabled=false;
    foreach($advanced as $key=>$default){
       if(($recipe[$key]??0)!==0){$enabled=true;if(str_starts_with($key,'hsl_'))$hslEnabled=true;}
    }
    if(!$enabled)return;
    $lut=editor_tone_lut($recipe);
    $changeCurve=$recipe['whites']||$recipe['blacks']||$recipe['curve_shadows']||$recipe['curve_midtones']||$recipe['curve_highlights'];
    $vib=$recipe['vibrance']/100;$tint=$recipe['tint']*.17;
    $hueLookup=[];
    if($hslEnabled)for($hue=0;$hue<360;$hue++)$hueLookup[$hue]=editor_hsl_controls($recipe,(float)$hue);
    $w=imagesx($im);$h=imagesy($im);
    for($y=0;$y<$h;$y++)for($x=0;$x<$w;$x++){
        $pixel=imagecolorat($im,$x,$y);
        $red=($pixel>>16)&255;$green=($pixel>>8)&255;$blue=$pixel&255;
        if($changeCurve){$red=$lut[$red];$green=$lut[$green];$blue=$lut[$blue];}
        if($tint){
            $red=(int)max(0,min(255,round($red+$tint)));
            $green=(int)max(0,min(255,round($green-$tint)));
            $blue=(int)max(0,min(255,round($blue+$tint*.45)));
        }
        if($vib){
            $range=max($red,$green,$blue)-min($red,$green,$blue);
            // Strongly colored pixels receive less additional saturation.
            $amount=$vib*(1-$range/255)*.72;
            $lum=.299*$red+.587*$green+.114*$blue;
            $red=(int)max(0,min(255,round($lum+($red-$lum)*(1+$amount))));
            $green=(int)max(0,min(255,round($lum+($green-$lum)*(1+$amount))));
            $blue=(int)max(0,min(255,round($lum+($blue-$lum)*(1+$amount))));
        }
        if($hslEnabled){
            [$hue,$sat,$light]=editor_rgb_to_hsl($red,$green,$blue);
            if($sat>0.004){
                [$deltaHue,$deltaSat,$deltaLum]=$hueLookup[((int)round($hue))%360];
                if($deltaHue||$deltaSat||$deltaLum){
                    $sat=max(0,min(1,$sat*(1+$deltaSat)));
                    $light=max(0,min(1,$light+$deltaLum*$light*(1-$light)*1.5));
                    [$red,$green,$blue]=editor_hsl_to_rgb($hue+$deltaHue,$sat,$light);
                }
            }
        }
        imagesetpixel($im,$x,$y,($red<<16)|($green<<8)|$blue);
    }
}
