"""Documented Windows input with checked delivery and a bounded button hold."""
import ctypes
import math
from ctypes import wintypes
import threading
import time


class DeadlineTask(threading.Thread):
    """Use Python's high-resolution sleep rather than Event.wait's timer tick."""
    def __init__(self,delay,callback,args=()):
        super().__init__(daemon=True)
        self.deadline=time.perf_counter()+max(0,delay)
        self.callback=callback
        self.callback_args=args
        self.cancelled=threading.Event()

    def cancel(self):
        self.cancelled.set()

    def run(self):
        remaining=self.deadline-time.perf_counter()
        if remaining>0:
            time.sleep(remaining)
        if not self.cancelled.is_set():
            self.callback(*self.callback_args)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx',wintypes.LONG),('dy',wintypes.LONG),
                ('mouseData',wintypes.DWORD),('dwFlags',wintypes.DWORD),
                ('time',wintypes.DWORD),('dwExtraInfo',ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk',wintypes.WORD),('wScan',wintypes.WORD),
                ('dwFlags',wintypes.DWORD),('time',wintypes.DWORD),
                ('dwExtraInfo',ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [('uMsg',wintypes.DWORD),('wParamL',wintypes.WORD),('wParamH',wintypes.WORD)]


class INPUTUNION(ctypes.Union):
    _fields_ = [('mi',MOUSEINPUT),('ki',KEYBDINPUT),('hi',HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ('u',)
    _fields_ = [('type',wintypes.DWORD),('u',INPUTUNION)]


class MouseInput:
    def __init__(self,hold_ms=35,api=None):
        self.api=api or ctypes.WinDLL('user32',use_last_error=True)
        if api is None:
            self.api.SendInput.argtypes=[wintypes.UINT,ctypes.POINTER(INPUT),ctypes.c_int]
            self.api.SendInput.restype=wintypes.UINT
        self.hold_ms=max(15,min(80,float(hold_ms)))
        self.lock=threading.RLock()
        self.pressed=False
        self.timer=None
        self.motion_timer=None
        self.motion=None
        self.motion_expected=None
        self.arrived_at=None
        self.movement_steps=0
        self.motion_started=None
        self.error=None
        self.generation=0
        self.retry_gap_ms=20.
        self.enabled=False
        self.last_delivery=None
        self.scheduled=None
        self.prepared=False
        self.last_cancellation=None
        self.retry_target=None
        self.hold_deadline=0.
        self.hold_guard=None
        if api is None:
            self.api.GetCursorPos.argtypes=[ctypes.POINTER(wintypes.POINT)]
            self.api.GetCursorPos.restype=wintypes.BOOL

    def schedule_click(self,x,y,when,count=None,guard=None,on_sent=None,tolerance=12):
        """Glide immediately, settle on the circle, and keep the ring deadline."""
        with self.lock:
            if self.error:raise self.error
            if not self.enabled or (guard is not None and not guard()):return False
            self.release()
            if count is None and guard is None:
                raise ValueError('Continuous retries require a target/focus guard')
            self._position(x,y)  # Validate desktop bounds without moving.
            point=wintypes.POINT()
            if not self.api.GetCursorPos(ctypes.byref(point)):
                raise OSError('Could not read the cursor before smooth movement')
            now=time.perf_counter()
            distance=math.hypot(x-point.x,y-point.y)
            available=when-now-.014
            if distance>2 and available<.035:
                self.last_cancellation=(now,'Target skipped: not enough ring time for smooth movement and settling.')
                return False
            count=None if count is None else max(1,int(count))
            self.retry_target=(x,y,tolerance)
            self.scheduled=(x,y,when,count,guard,on_sent,tolerance)
            self.motion_started=now
            self.movement_steps=0
            if distance<=2:
                self.arrived_at=now;self.prepared=True
            else:
                duration=min(.550,max(.320,distance/2600+.120),available)
                self.motion=(point.x,point.y,now,duration)
                self.motion_expected=(point.x,point.y)
                self._schedule_motion(.008,self.generation)
            self._schedule(max(0,when-now),self._dispatch,self.generation)
            return True

    def retime(self,when):
        """Update the click deadline while movement continues independently."""
        with self.lock:
            if not self.enabled or self.scheduled is None:return False
            x,y,old,count,guard,on_sent,tolerance=self.scheduled
            now=time.perf_counter()
            if old-now<.035 or when-now<.035 or not .002<abs(when-old)<.060:return False
            if self.motion and when<self.motion[2]+self.motion[3]+.014:return False
            if self.timer:self.timer.cancel()
            self.scheduled=(x,y,when,count,guard,on_sent,tolerance)
            self._schedule(max(0,when-now),self._dispatch,self.generation)
            return True

    def update_target(self,x,y):
        """Follow the same tracked circle; never switch to an unrelated target."""
        with self.lock:
            if self.scheduled is None or not self.enabled:return False
            oldx,oldy,when,count,guard,on_sent,tolerance=self.scheduled
            self._position(x,y)
            if math.hypot(x-oldx,y-oldy)<=max(4,tolerance*.5):return True
            self.scheduled=(x,y,when,count,guard,on_sent,tolerance)
            self.retry_target=(x,y,tolerance)
            if self.motion is None and math.hypot(x-oldx,y-oldy)>3:
                point=wintypes.POINT()
                if not self.api.GetCursorPos(ctypes.byref(point)):raise OSError('Could not read tracked cursor position')
                available=when-time.perf_counter()-.014
                if available<.035:
                    self.last_cancellation=(time.perf_counter(),'Target moved too late to follow smoothly; click cancelled.')
                    self.release();return False
                self.prepared=False;self.arrived_at=None
                self.motion=(point.x,point.y,time.perf_counter(),min(.070,available))
                self.motion_expected=(point.x,point.y)
                self._schedule_motion(.008,self.generation)
            return True

    def _schedule_motion(self,delay,generation):
        self.motion_timer=DeadlineTask(delay,self._motion_tick,args=(generation,))
        self.motion_timer.start()

    def _motion_tick(self,generation):
        with self.lock:
            if generation!=self.generation or not self.enabled or self.scheduled is None or self.motion is None:return
            try:
                x,y,when,count,guard,on_sent,tolerance=self.scheduled
                if guard is not None and not guard():
                    self.last_cancellation=(time.perf_counter(),'Smooth movement stopped: target, focus, or stop state changed.')
                    self.release();return
                point=wintypes.POINT()
                if not self.api.GetCursorPos(ctypes.byref(point)):raise OSError('Could not verify cursor during smooth movement')
                if self.motion_expected and math.hypot(point.x-self.motion_expected[0],point.y-self.motion_expected[1])>max(20,tolerance*2):
                    self.last_cancellation=(time.perf_counter(),'Smooth movement stopped: cursor was moved or constrained. Keep the mouse unlocked.')
                    self.release();return
                now=time.perf_counter()
                if now>when-.008:
                    self.last_cancellation=(now,'Click cancelled: smooth movement did not settle before the ring deadline.')
                    self.release();return
                sx,sy,began,duration=self.motion
                progress=min(1.,max(0.,(now-began)/max(.001,duration)))
                eased=progress*progress*(3-2*progress)
                nx,ny=sx+(x-sx)*eased,sy+(y-sy)*eased
                # Bound individual steps even when the OS delays a callback.
                dx,dy=nx-point.x,ny-point.y
                length=math.hypot(dx,dy)
                if length>48:nx=point.x+dx*48/length;ny=point.y+dy*48/length
                nx,ny=round(nx),round(ny)
                if (nx,ny)!=(point.x,point.y):
                    if not self.move(nx,ny):return
                    self.movement_steps+=1
                self.motion_expected=(nx,ny)
                if math.hypot(nx-x,ny-y)<=1:
                    self.motion=None;self.motion_timer=None
                    self.prepared=True;self.arrived_at=time.perf_counter()
                else:self._schedule_motion(.008,generation)
            except Exception as exc:
                self.error=exc;self.release()

    def _dispatch(self,generation):
        with self.lock:
            if generation!=self.generation or not self.enabled or self.scheduled is None:return
            try:
                x,y,when,count,guard,on_sent,tolerance=self.scheduled
                now=time.perf_counter()
                if now<when-.001:
                    self._schedule(when-now,self._dispatch,generation);return
                if guard is not None and not guard():
                    self.last_cancellation=(now,'Scheduled click cancelled: target, focus, or stop state changed before button press.')
                    self.release();return
                if self.arrived_at is None or now-self.arrived_at<.008:
                    self.last_cancellation=(now,'Click cancelled: cursor was not settled on the circle at the ring deadline.')
                    self.release();return
                point=wintypes.POINT()
                if not self.api.GetCursorPos(ctypes.byref(point)):raise OSError('Could not verify the cursor position')
                if abs(point.x-x)>tolerance or abs(point.y-y)>tolerance:
                    self.last_cancellation=(now,'Click cancelled: cursor left the tracked circle before the ring deadline.')
                    self.release();return
                before=time.perf_counter()
                if self._press(x,y,count,guard,generation,move=False):
                    self.scheduled=None
                    self.last_delivery={'planned':when,'sent':before,'lateness_ms':(before-when)*1000,
                                        'cursor':[point.x,point.y],'target':[x,y],
                                        'movement_steps':self.movement_steps,
                                        'travel_ms':(self.arrived_at-self.motion_started)*1000,
                                        'settled_ms':(before-self.arrived_at)*1000}
                    if on_sent is not None:on_sent(dict(self.last_delivery))
            except Exception as exc:
                self.error=exc;self.release()

    def set_enabled(self,enabled):
        with self.lock:
            self.enabled=bool(enabled)
            if not self.enabled:
                self.release()

    def set_hold(self,holding,guard=None):
        """Shu input: no cursor movement; release automatically if scans stop."""
        with self.lock:
            if not holding or not self.enabled or (guard is not None and not guard()):
                if self.pressed or self.timer:
                    self.release()
                return False
            if self.error:
                raise self.error
            self.hold_deadline=time.perf_counter()+.15
            self.hold_guard=guard
            if not self.pressed:
                self.release()
                if not self._send(self._event(0x0002)):return False
                self.pressed=True
                self.hold_deadline=time.perf_counter()+.15
                self.hold_guard=guard
                self._schedule(.15,self._hold_watchdog,self.generation)
            return True

    def _hold_watchdog(self,generation):
        with self.lock:
            if generation!=self.generation:return
            try:
                if not self.enabled or time.perf_counter()>=self.hold_deadline or (self.hold_guard is not None and not self.hold_guard()):
                    self.release()
                else:self._schedule(max(.005,self.hold_deadline-time.perf_counter()),self._hold_watchdog,generation)
            except Exception as exc:self.error=exc

    def _send(self,*events):
        with self.lock:
            # Releases are permitted while disarmed, but no movement or press.
            if not self.enabled and any(e.mi.dwFlags & 0x0003 for e in events):
                return False
            array=(INPUT*len(events))(*events)
            if self.api.SendInput(len(events),array,ctypes.sizeof(INPUT))!=len(events):
                raise OSError(ctypes.get_last_error(),
                              'Windows did not accept mouse input. Check that Roblox and the macro run at the same privilege level.')
            return True

    def _event(self,flags,x=0,y=0):
        return INPUT(type=0,mi=MOUSEINPUT(x,y,0,flags,0,0))

    def _position(self,x,y):
        left=self.api.GetSystemMetrics(76)
        top=self.api.GetSystemMetrics(77)
        width=self.api.GetSystemMetrics(78)
        height=self.api.GetSystemMetrics(79)
        if not left<=x<left+width or not top<=y<top+height:
            raise ValueError('Click is outside the desktop. Re-select the game area.')
        nx=round((x-left)*65535/max(1,width-1))
        ny=round((y-top)*65535/max(1,height-1))
        return self._event(0x0001|0x8000|0x4000,nx,ny)

    def move(self,x,y):
        return self._send(self._position(x,y))

    def click(self,x,y,count=None,guard=None):
        with self.lock:
            if self.error:
                raise self.error
            if not self.enabled:
                return False
            self.release()
            if count is None and guard is None:
                raise ValueError('Continuous retries require a target/focus guard')
            count=None if count is None else max(1,int(count))
            self.retry_target=(x,y,12)
            return self._press(x,y,count,guard,self.generation)

    def _schedule(self,delay,callback,*args):
        self.timer=DeadlineTask(delay,callback,args=args)
        self.timer.start()

    def _press(self,x,y,left,guard,generation,move=True):
        with self.lock:
            if generation!=self.generation or not self.enabled:
                return False
            if guard is not None and not guard():
                self.release()
                return False
            self.pressed=True
            try:
                if move:
                    accepted=self._send(self._position(x,y),self._event(0x0002))
                else:
                    # Retrying the button does not need another cursor warp.
                    accepted=self._send(self._event(0x0002))
                if not accepted:
                    self.pressed=False
                    return False
                self._schedule(self.hold_ms/1000,self._finish_press,x,y,left,guard,generation)
                return True
            except Exception as exc:
                self.error=exc
                self.release()
                raise

    def _finish_press(self,x,y,left,guard,generation):
        with self.lock:
            if generation!=self.generation:
                return
            try:
                if self.pressed:
                    self._send(self._event(0x0004))
                    self.pressed=False
                if left is None or left>1:
                    self._schedule(self.retry_gap_ms/1000,self._retry,x,y,None if left is None else left-1,guard,generation)
                else:
                    self.timer=None
            except Exception as exc:
                self.error=exc

    def _retry(self,x,y,left,guard,generation):
        try:
            with self.lock:
                if generation!=self.generation or not self.enabled:
                    return
                if self.retry_target:
                    tx,ty,tolerance=self.retry_target
                    point=wintypes.POINT()
                    if not self.api.GetCursorPos(ctypes.byref(point)):
                        raise OSError('Could not verify cursor before retry')
                    if abs(point.x-tx)>tolerance or abs(point.y-ty)>tolerance:
                        self.last_cancellation=(time.perf_counter(),'Click retries stopped: cursor left the target.')
                        self.release()
                        return
            self._press(x,y,left,guard,generation,move=False)
        except Exception as exc:
            self.error=exc

    def release(self):
        with self.lock:
            self.generation+=1
            self.scheduled=None
            self.prepared=False
            self.motion=None
            self.motion_expected=None
            self.arrived_at=None
            if self.motion_timer:
                self.motion_timer.cancel();self.motion_timer=None
            self.retry_target=None
            if self.timer:
                self.timer.cancel()
                self.timer=None
            if self.pressed:
                self._send(self._event(0x0004))
                self.pressed=False


class KeyboardInput:
    """Short scan-code taps; always release on pause, focus loss or timeout."""
    def __init__(self,api=None):
        self.api=api or ctypes.WinDLL('user32',use_last_error=True)
        if api is None:
            self.api.SendInput.argtypes=[wintypes.UINT,ctypes.POINTER(INPUT),ctypes.c_int]
            self.api.SendInput.restype=wintypes.UINT
        self.lock=threading.RLock()
        self.pressed=None
        self.timer=None
        self.suppressed_until={}
        self.error=None

    def _send(self,vk,up):
        scan=self.api.MapVirtualKeyW(vk,0)
        if not scan:raise OSError('Could not map prompt key')
        item=INPUT(type=1,ki=KEYBDINPUT(0,scan,8|(2 if up else 0),0,0))
        if self.api.SendInput(1,ctypes.byref(item),ctypes.sizeof(INPUT))!=1:
            raise OSError(ctypes.get_last_error(),'Windows did not accept the prompt key')

    def suppresses(self,binding):
        now=time.perf_counter()
        return any(self.suppressed_until.get(vk,0)>now for vk in binding)

    def tap(self,key,guard):
        with self.lock:
            if len(key)!=1 or not 'A'<=key<='Z':raise ValueError('Only letter prompts are supported')
            if self.pressed is not None or not guard():return False
            vk=ord(key)
            self.suppressed_until[vk]=time.perf_counter()+.18
            # Mark first so a failed delivery still attempts a matching release.
            self.pressed=vk
            try:self._send(vk,False)
            except Exception:
                self.release()
                raise
            def finish():
                try:self.release()
                except Exception as exc:self.error=exc
            self.timer=DeadlineTask(.035,finish)
            self.timer.start()
            return True

    def release(self):
        with self.lock:
            if self.timer:self.timer.cancel();self.timer=None
            if self.pressed is not None:
                vk=self.pressed
                self._send(vk,True)
                self.pressed=None
