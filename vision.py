"""Pure image processing and timing; importing this module never clicks."""
from dataclasses import dataclass, field
from collections import deque
import re
import cv2
import numpy as np


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
        points = [(t,r) for t,r in self.history if now-t < .40]
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
        elif now-self.last_color_seen>8:
            self.hue=None
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
