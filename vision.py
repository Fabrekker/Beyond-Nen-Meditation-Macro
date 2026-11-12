"""Pure image processing and timing; importing this module never clicks."""
from dataclasses import dataclass, field
from collections import deque
import re
import cv2
import numpy as np


def feedback_search_rect(game,client=None):
    """Search only the feedback side of the game, even in full-screen capture."""
    left,top=game['left'],game['top']
    right,bottom=left+game['width'],top+game['height']
    if client:
        left=max(left,client['left']); top=max(top,client['top'])
        right=min(right,client['left']+client['width'])
        bottom=min(bottom,client['top']+client['height'])
    if right<=left or bottom<=top:
        return None
    width,height=right-left,bottom-top
    x=left+int(width*.65); y=top+int(height*.25)
    return {'left':x,'top':y,'width':right-x,'height':max(1,int(height*.60))}


def masks(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    yellow = cv2.inRange(hsv, (17, 105, 100), (40, 255, 255))
    white = cv2.inRange(hsv, (0, 0, 155), (179, 100, 255))
    return yellow, white


def hue_distance(a,b):
    return abs((float(a)-float(b)+90)%180-90)


def color_name(hue):
    for edge,name in ((8,'Red'),(20,'Orange'),(36,'Yellow'),(86,'Green'),(100,'Cyan'),(130,'Blue'),(153,'Purple'),(172,'Pink'),(180,'Red')):
        if hue<edge:
            return name


def color_mask(hsv,hue):
    distance=np.abs(hsv[:,:,0].astype(np.int16)-round(hue))
    return (((np.minimum(distance,180-distance)<=12)&(hsv[:,:,1]>=70)&(hsv[:,:,2]>=65))*255).astype(np.uint8)


def colored_targets(frame):
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    white=cv2.inRange(hsv,(0,0,155),(179,100,255))
    contours, _ = cv2.findContours(white, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    found = []
    limit = min(frame.shape[:2]) * .18
    for c in contours:
        area = cv2.contourArea(c)
        perimeter = cv2.arcLength(c, True)
        if area < 90 or perimeter == 0 or 4*np.pi*area/perimeter**2 < .72:
            continue
        (x, y), r = cv2.minEnclosingCircle(c)
        if not 6 <= r <= limit:
            continue
        bx, by, bw, bh = cv2.boundingRect(c)
        if not .85 < bw / bh < 1.18 or area / (np.pi*r*r) < .8:
            continue
        # Inspect only the disk, rather than allocating a full-screen array
        # for every contour at desktop resolution.
        x0,x1=max(0,int(x-r)),min(frame.shape[1],int(x+r)+2)
        y0,y1=max(0,int(y-r)),min(frame.shape[0],int(y+r)+2)
        yy,xx=np.ogrid[y0:y1,x0:x1]
        inside=(xx-x)**2+(yy-y)**2 < (r*.75)**2
        pixels=hsv[y0:y1,x0:x1][inside]
        saturated=(pixels[:,1]>=70)&(pixels[:,2]>=65)
        if saturated.mean()<.65:
            continue
        hues=pixels[saturated,0]
        histogram=np.bincount(hues,minlength=180)
        hue=int(np.argmax(histogram))
        if np.mean(np.minimum(abs(hues.astype(int)-hue),180-abs(hues.astype(int)-hue))<=12)<.75:
            continue
        if not any(np.hypot(x-a, y-b) < r*.5 for a,b,_,_ in found):
            found.append((float(x),float(y),float(r),hue))
    return found,hsv


def targets(frame):
    circles,hsv=colored_targets(frame)
    mask=np.zeros(frame.shape[:2],np.uint8)
    for hue in {c[3] for c in circles}:
        mask=cv2.bitwise_or(mask,color_mask(hsv,hue))
    return [c[:3] for c in circles],mask


ANGLES = np.linspace(0, 2*np.pi, 120, endpoint=False)


def ring_radius(yellow, x, y, radius):
    """Find a nearly complete yellow annulus outside the white target border."""
    radii = np.arange(radius+1.5, radius*3.2, .5)
    if not len(radii):
        return None
    xx = np.rint(x+radii[:,None]*np.cos(ANGLES)).astype(int)
    yy = np.rint(y+radii[:,None]*np.sin(ANGLES)).astype(int)
    valid = (xx>=0)&(xx<yellow.shape[1])&(yy>=0)&(yy<yellow.shape[0])
    values = yellow[np.clip(yy,0,yellow.shape[0]-1),np.clip(xx,0,yellow.shape[1]-1)] > 0
    coverage = (values&valid).sum(axis=1)/np.maximum(valid.sum(axis=1),1)
    good = (coverage>.62)&(valid.mean(axis=1)>.72)
    groups = np.split(np.flatnonzero(good), np.flatnonzero(np.diff(np.flatnonzero(good))>1)+1)
    groups = [g for g in groups if len(g)>=2]
    if not groups:
        return None
    # Thin ring, high angular coverage; prefer outer ring over disk bleed.
    group = max(groups, key=lambda g: float(coverage[g].mean()) + radii[g].mean()*.0005)
    return float(np.average(radii[group], weights=coverage[group]))


@dataclass
class Track:
    x: float
    y: float
    radius: float
    born: float
    seen: float
    history: deque = field(default_factory=lambda: deque(maxlen=14))
    clicked: bool = False
    ring: float | None = None
    hue: float = 26.

    def observe(self, now, ring):
        self.ring = ring
        if ring is not None:
            self.history.append((now, ring))

    def remaining(self, now):
        points = [(t,r) for t,r in self.history if now-t < .55]
        if len(points)<4 or points[-1][0]-points[0][0]<.045:
            return None
        ts, rs = np.array(points).T
        ts = ts-ts[-1]
        slope, intercept = np.polyfit(ts, rs, 1)
        if slope >= -3 or np.std(rs-(slope*ts+intercept)) > max(1.8,self.radius*.08):
            return None
        # Recent samples must still support the predicted shrinking ring.
        if now-points[-1][0] > .12:
            return None
        return float((intercept-self.radius)/-slope - (now-points[-1][0]))


class Detector:
    def __init__(self):
        self.tracks = []
        self.hue=None
        self.last_color_seen=0.

    @property
    def color_status(self):
        return 'Checking colors…' if self.hue is None else f'Tracking {color_name(self.hue)}'

    @property
    def color_hex(self):
        if self.hue is None:
            return '#98a7bc'
        rgb=cv2.cvtColor(np.uint8([[[round(self.hue),220,245]]]),cv2.COLOR_HSV2RGB)[0,0]
        return '#'+''.join(f'{v:02x}' for v in rgb)

    def update(self, frame, now):
        circles,hsv=colored_targets(frame)
        self.tracks = [t for t in self.tracks if now-t.seen < .32 and now-t.born < 2.5]
        for x,y,r,hue in circles:
            t = next((t for t in self.tracks if np.hypot(t.x-x,t.y-y)<max(r,t.radius)*.65 and hue_distance(t.hue,hue)<=12),None)
            if t is None:
                t = Track(x,y,r,now,now)
                t.hue=hue
                self.tracks.append(t)
            else:
                t.x,t.y = x,y
                t.radius = .8*t.radius+.2*r
                t.seen = now
        masks_by_hue={}
        for t in self.tracks:
            key=round(t.hue)
            if key not in masks_by_hue:
                masks_by_hue[key]=color_mask(hsv,key)
            t.observe(now,ring_radius(masks_by_hue[key],t.x,t.y,t.radius))
        confirmed=[t for t in self.tracks if len(t.history)>=3 and now-t.seen<.12
                   and now-t.history[-1][0]<.12 and t.history[0][1]-t.history[-1][1]>.7]
        matching=[t for t in confirmed if self.hue is not None and hue_distance(t.hue,self.hue)<=12]
        if matching:
            self.last_color_seen=now
        elif confirmed:
            chosen=max(confirmed,key=lambda t:len(t.history))
            self.hue=chosen.hue
            self.last_color_seen=now
        return [t for t in self.tracks if self.hue is not None and hue_distance(t.hue,self.hue)<=12]


def parse_feedback(items):
    """Require an explicit signed decimal, or the complete word MISS."""
    for text, confidence in items:
        if confidence < .65:
            continue
        text = text.upper().replace(' ', '').replace(',', '.')
        if re.fullmatch(r'MISS[!.]?',text):
            return 'MISS'
        match = re.fullmatch(r'([+−-])([0-9]+\.[0-9]{1,3})', text)
        if match:
            value = float(match[2]) * (-1 if match[1] in '-−' else 1)
            if abs(value)<=1:
                return value
    return None


class Tuner:
    """Bounded score search. Score magnitude is never treated as timing error."""
    def __init__(self, lead_ms=12., step_ms=3.):
        self.lead_ms = lead_ms
        self.step_ms = step_ms
        self.direction = 1
        self.previous = None
        self.best = None
        self.probe = 0

    def feedback(self, value, threshold=.04):
        score = -1. if value == 'MISS' else float(value)
        if self.best is None or score > self.best[0]:
            self.best = (score,self.lead_ms)
            self.probe = 0
        if score >= threshold:
            self.previous = score
            return 'Target score reached; holding timing'
        # Explore both sides of the best timing. Equal MISS results must not
        # collapse the search to an ever-smaller interval around a bad setting.
        for _ in range(40):
            self.probe = self.probe % 20 + 1
            distance = ((self.probe+1)//2)*self.step_ms
            direction = 1 if self.probe%2 else -1
            candidate = float(np.clip(self.best[1]+direction*distance,-35,65))
            if abs(candidate-self.lead_ms)>.5:
                self.lead_ms = candidate
                break
        self.previous = score
        return f'Recalibrating: lead {self.lead_ms:+.1f} ms'


@dataclass
class ShuBar:
    left: float
    right: float
    top: float
    bottom: float
    zone_left: float
    zone_right: float
    marker: float
    focus: float | None = None


def detect_shu(frame):
    """Match the white indicator, rectangular target and long bar together."""
    height,width=frame.shape[:2]
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    white=cv2.inRange(hsv,(0,0,210),(179,65,255))
    white[:int(height*.40)]=0
    white[int(height*.85):]=0
    white[:,:int(width*.15)]=0
    white[:,int(width*.85):]=0
    contours,_=cv2.findContours(white,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    candidates=[]
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour)
        if not max(7,height*.012)<=h<=height*.075 or not 1<=w<=max(8,width*.012) or h<2.5*w:
            continue
        if cv2.contourArea(contour)<max(4,w*h*.45):
            continue
        # The HUD is centered; its translucent border can disappear against
        # the aura, so match the dark strip and both foreground controls.
        left,right=int(width*.30),int(width*.70)
        if not left<=x<=right:continue
        if np.mean(hsv[y:y+h,left:right,2]<105)<.45:continue
        strip=hsv[y:y+h,left:right+1]
        colored=(strip[:,:,0]>=12)&(strip[:,:,0]<=45)&(strip[:,:,1]>=65)&(strip[:,:,2]>=100)
        colored[:,max(0,x-left):min(colored.shape[1],x+w-left)]=True
        columns=np.flatnonzero(colored.mean(axis=0)>.75)
        groups=np.split(columns,np.flatnonzero(np.diff(columns)>1)+1)
        groups=[g for g in groups if width*.018<=len(g)<=width*.14]
        for group in groups:
            zl,zr=left+int(group[0]),left+int(group[-1])+1
            center=(left+right)/2
            focus=None
            # The focus meter is a separate slim green bar below the control.
            fy0=min(height,y+h+max(2,int(h*.25)))
            fy1=min(height,y+h+int(h*2.2))
            focus_mask=cv2.inRange(hsv[fy0:fy1],(40,130,90),(90,255,255))
            fc,_=cv2.findContours(focus_mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            for c in fc:
                fx,fy,fw,fh=cv2.boundingRect(c)
                if (right-left)*.07<fw<(right-left)*.9 and 1<=fh<=h*.8 and abs(fx-center)<(right-left)*.5:
                    full=2*(center-fx)
                    if full>fw*.95:focus=float(np.clip(fw/full,0,1));break
            if focus is None:
                # At reset there is no green fill. Verify the actual dark
                # meter interior instead of treating every missing fill as 0.
                mx0=max(0,round(center-(right-left)*.355))
                mx1=min(width,round(center+(right-left)*.355))
                my=round(y+h*1.9)
                meter=hsv[max(0,my-1):min(height,my+2),mx0:mx1]
                if meter.size:
                    green=(meter[:,:,0]>=40)&(meter[:,:,0]<=90)&(meter[:,:,1]>=130)&(meter[:,:,2]>=90)
                    neutral=(meter[:,:,1]<110)&(meter[:,:,2]>10)&(meter[:,:,2]<70)
                    if np.mean(green|neutral)>.95:
                        focus=float(np.mean(green.mean(axis=0)>.5))
            candidates.append((right-left,ShuBar(left,right,y,y+h,zl,zr,x+w/2,focus)))
    return max(candidates,key=lambda c:c[0])[1] if candidates else None


class ShuController:
    def __init__(self):
        self.previous=None
        self.velocity=0.
        self.holding=False
        self.cycles=0
        self.peak_focus=0.

    def update(self,bar,now):
        if bar is None:
            self.previous=None
            self.velocity=0.
            self.holding=False
            return False
        if self.previous:
            stamp,position=self.previous
            dt=now-stamp
            if .005<dt<.25:
                self.velocity=.6*self.velocity+.4*(bar.marker-position)/dt
        self.previous=(now,bar.marker)
        center=(bar.zone_left+bar.zone_right)/2
        deadband=max(1.5,(bar.zone_right-bar.zone_left)*.12)
        predicted=bar.marker+self.velocity*.070
        if predicted<center-deadband:self.holding=True
        elif predicted>center+deadband:self.holding=False
        if bar.focus is not None:
            if self.peak_focus>=.97 and bar.focus<.2:
                self.cycles+=1
                self.peak_focus=bar.focus
            else:self.peak_focus=max(self.peak_focus,bar.focus)
        return self.holding


@dataclass
class EnPrompt:
    rect: tuple
    image: np.ndarray
    signature: np.ndarray
    glyph: np.ndarray
    label: np.ndarray


def detect_en_prompt(frame):
    """Require a large light glyph, small label and red deadline strip together."""
    height,width=frame.shape[:2]
    hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
    white=cv2.inRange(hsv,(0,0,185),(179,90,255))
    white[:int(height*.15)]=0
    white[int(height*.78):]=0
    white[:,:int(width*.40)]=0
    contours,_=cv2.findContours(white,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    candidates=[]
    for c in contours:
        x,y,w,h=cv2.boundingRect(c)
        if not height*.035<=h<=height*.10 or not h*.12<=w<=h*1.5:continue
        cx=x+w/2
        x0=max(0,round(cx-h*1.05));x1=min(width,round(cx+h*1.05))
        y0=max(0,round(y-h*.18));y1=min(height,round(y+h*2.05))
        below=hsv[round(y+h*1.5):y1,x0:x1]
        if not below.size:continue
        red=((below[:,:,0]<8)|(below[:,:,0]>172))&(below[:,:,1]>150)&(below[:,:,2]>85)
        rc,_=cv2.findContours(red.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        if not any(rw>=h*.15 and 1<=rh<=h*.35 and rw>rh*1.5 for _,_,rw,rh in map(cv2.boundingRect,rc)):continue
        label=white[round(y+h*1.25):round(y+h*1.7),x0:x1]
        if np.count_nonzero(label)<h*.4:continue
        signature=cv2.resize(white[y:y+h,x:x+w],(24,32),interpolation=cv2.INTER_AREA)>100
        candidates.append(EnPrompt((x0,y0,x1,y1),frame[y0:y1,x0:x1].copy(),signature,
                                   frame[max(0,y-3):min(height,y+h+3),max(0,x-4):min(width,x+w+4)].copy(),
                                   frame[round(y+h*1.25):round(y+h*1.7),x0:x1].copy()))
    return candidates[0] if len(candidates)==1 else None


def parse_en_key(rows):
    """Only accept a single high-confidence letter above a verified PRESS label."""
    labels=[r for r in (rows or []) if str(r[1]).strip().upper()=='PRESS' and float(r[2])>=.90]
    if len(labels)!=1:return None
    label=labels[0]
    ly=float(np.mean(np.asarray(label[0])[:,1]))
    keys=[r for r in rows if re.fullmatch('[A-Z]',str(r[1]).strip()) and float(r[2])>=.94
          and float(np.max(np.asarray(r[0])[:,1]))<ly]
    return str(keys[0][1]).strip() if len(keys)==1 else None


def recognize_en(engine,images):
    """Recognition-only crops avoid full-scene text detection latency."""
    readings=[]
    for image in images:
        enlarged=cv2.resize(image,None,fx=2,fy=2,interpolation=cv2.INTER_CUBIC)
        rows,_=engine(enlarged,use_det=False,use_cls=False)
        if not rows or len(rows)!=1:return None
        readings.append((str(rows[0][0]).strip(),float(rows[0][1])))
    (key,score),(label,label_score)=readings
    if re.fullmatch('[A-Z]',key) and score>=.94 and label.upper()=='PRESS' and label_score>=.90:return key
    return None


class KoController:
    """Hold toward the zone; release once inside, then await the next attempt."""
    def __init__(self):
        self.attempts=0
        self.reset()

    def reset(self):
        self.previous=None
        self.velocity=0.
        self.holding=False
        self.released=False
        self.release_position=None
        self.missing_since=None
        self.phase='Waiting'

    def update(self,bar,now,active=True):
        if not active:
            self.reset();return False
        if bar is None:
            if self.missing_since is None:self.missing_since=now
            if now-self.missing_since>.12:self.reset();self.missing_since=now
            self.previous=None;self.holding=False;self.phase='Waiting'
            return False
        self.missing_since=None
        if self.released:
            # Re-arm when a new indicator starts back at the left edge.
            if (bar.marker<bar.left+(bar.right-bar.left)*.10 and self.release_position is not None
                    and self.release_position-bar.marker>(bar.right-bar.left)*.12):
                self.reset()
            else:
                self.phase='Released';return False
        if self.previous:
            stamp,position=self.previous;dt=now-stamp
            if .005<dt<.25:self.velocity=.5*self.velocity+.5*(bar.marker-position)/dt
        self.previous=(now,bar.marker)
        width=bar.zone_right-bar.zone_left
        goal=bar.zone_left+width*.45
        predicted=bar.marker+max(0,self.velocity)*.020
        if self.holding and bar.marker>=bar.zone_left and (predicted>=goal or bar.marker>=bar.zone_right-width*.20):
            self.holding=False;self.released=True;self.release_position=bar.marker
            self.attempts+=1;self.phase='Released'
            return False
        self.holding=True;self.phase='Moving'
        return True


def crop_preview(frame,rect):
    """Crop only the display image; detector/input coordinates remain unchanged."""
    height,width=frame.shape[:2]
    x0,y0,x1,y1=map(float,rect)
    margin_x=max(12,(x1-x0)*.08);margin_y=max(12,(y1-y0)*.12)
    x0=max(0,int(np.floor(x0-margin_x)));y0=max(0,int(np.floor(y0-margin_y)))
    x1=min(width,int(np.ceil(x1+margin_x)));y1=min(height,int(np.ceil(y1+margin_y)))
    return frame[y0:y1,x0:x1] if x1>x0 and y1>y0 else frame


def stable_preview_crop(frame,rect):
    """Keep a fixed display scale, including targets near the capture edges."""
    height,width=frame.shape[:2]
    x0,y0,x1,y1=map(float,rect)
    side=max(1,min(2048,round(max(x1-x0,y1-y0))))
    left=round((x0+x1-side)/2);top=round((y0+y1-side)/2)
    if width>=side:left=max(0,min(width-side,left))
    if height>=side:top=max(0,min(height-side,top))
    result=np.zeros((side,side)+frame.shape[2:],dtype=frame.dtype)
    sx0,sy0=max(0,left),max(0,top);sx1,sy1=min(width,left+side),min(height,top+side)
    if sx1>sx0 and sy1>sy0:
        result[sy0-top:sy1-top,sx0-left:sx1-left]=frame[sy0:sy1,sx0:sx1]
    return result


class BarActivityTracker:
    """Summarize repeated appearances; tolerate normal gaps without log spam."""
    def __init__(self,absence_seconds=7.):
        self.absence_seconds=absence_seconds
        self.mode=None;self.series=0;self.active=False;self.visible=False
        self.last_seen=0.;self.started_waiting=0.;self.reported_absence=False
        self.appearances=0;self.completed=0;self.previous_total=0;self.started_at=0.

    def event(self,phase,reason=None):
        count_label='zone releases' if self.mode=='Ko/RyuS/RyuD' else 'completed rounds'
        details=f'bar appearances: {self.appearances} | {count_label}: {self.completed}'
        text=f'{self.mode} training detected | {details}'
        if reason:text=f'{self.mode} {reason} | {details}'
        return {'type':'bar_activity','key':self.series,'phase':phase,'time':self.started_at,
                'mode':self.mode,'appearances':self.appearances,'completed':self.completed,'text':text}

    def finish(self,reason='tracking ended'):
        if not self.active:return []
        self.active=False;self.visible=False
        return [self.event('ended',reason)]

    def update(self,mode,present,now,total,enabled=False,wall_time=0.):
        events=[]
        if mode!=self.mode:
            events.extend(self.finish('tracking ended: training mode changed'))
            self.mode=mode;self.previous_total=total;self.started_waiting=now
            self.reported_absence=False
        delta=max(0,total-self.previous_total);self.previous_total=total
        if present:
            self.reported_absence=False
            if not self.active:
                self.series+=1;self.active=True;self.appearances=1;self.completed=0
                self.started_at=wall_time
                events.append(self.event('started'))
            else:
                changed=False
                if not self.visible and now-self.last_seen>.18:
                    self.appearances+=1;changed=True
                if delta:self.completed+=delta;changed=True
                if changed:events.append(self.event('updated'))
            self.last_seen=now;self.visible=True
        else:
            self.visible=False
            if self.active and now-self.last_seen>=self.absence_seconds:
                events.extend(self.finish(f'training interrupted: no minigame detected for {self.absence_seconds:g}s; input released'))
                self.reported_absence=True
            elif enabled and not self.active and not self.reported_absence and now-self.started_waiting>=self.absence_seconds:
                self.series+=1;self.started_at=wall_time;self.appearances=0;self.completed=0
                events.append(self.event('ended',f'training not visible: no minigame detected for {self.absence_seconds:g}s; check the game and capture area'))
                self.reported_absence=True
        return events
