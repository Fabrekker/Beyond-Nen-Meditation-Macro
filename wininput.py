"""Documented Windows input with checked delivery and a bounded button hold."""
import ctypes
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
        self.error=None
        self.generation=0
        self.retry_gap_ms=20.
        self.enabled=False
        self.last_delivery=None
        if api is None:
            self.api.GetCursorPos.argtypes=[ctypes.POINTER(wintypes.POINT)]
            self.api.GetCursorPos.restype=wintypes.BOOL

    def schedule_click(self,x,y,when,count=3,guard=None,on_sent=None,tolerance=12):
        """Prepare the pointer, then dispatch independently of frame capture."""
        with self.lock:
            if self.error:
                raise self.error
            if not self.enabled or (guard is not None and not guard()):
                return False
            self.release()
            generation=self.generation
            self._schedule(max(0,when-time.perf_counter()-.025),self._prepare,
                           x,y,when,count,guard,on_sent,tolerance,generation)
            return True

    def _prepare(self,x,y,when,count,guard,on_sent,tolerance,generation):
        with self.lock:
            if generation!=self.generation or not self.enabled:
                return
            if guard is not None and not guard():
                self.release()
                return
            try:
                if not self.move(x,y):
                    return
                self._schedule(max(0,when-time.perf_counter()),self._dispatch,
                               x,y,when,count,guard,on_sent,tolerance,generation)
            except Exception as exc:
                self.error=exc

    def _dispatch(self,x,y,when,count,guard,on_sent,tolerance,generation):
        with self.lock:
            if generation!=self.generation or not self.enabled:
                return
            try:
                if guard is not None and not guard():
                    self.release()
                    return
                point=wintypes.POINT()
                if not self.api.GetCursorPos(ctypes.byref(point)):
                    raise OSError('Could not verify the cursor position')
                if abs(point.x-x)>tolerance or abs(point.y-y)>tolerance:
                    raise OSError('Cursor did not stay on target. Disable Roblox shift lock / first-person mouse lock; keep the mouse free while running.')
                before=time.perf_counter()
                if self._press(x,y,count,guard,generation,move=False):
                    self.last_delivery={'planned':when,'sent':before,'lateness_ms':(before-when)*1000,
                                        'cursor':[point.x,point.y],'target':[x,y]}
                    if on_sent is not None:
                        on_sent(dict(self.last_delivery))
            except Exception as exc:
                self.error=exc
                self.release()

    def set_enabled(self,enabled):
        with self.lock:
            self.enabled=bool(enabled)
            if not self.enabled:
                self.release()

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

    def click(self,x,y,count=3,guard=None):
        with self.lock:
            if self.error:
                raise self.error
            self.release()
            return self._press(x,y,max(1,min(3,int(count))),guard,self.generation)

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
                if left>1:
                    self._schedule(self.retry_gap_ms/1000,self._retry,x,y,left-1,guard,generation)
                else:
                    self.timer=None
            except Exception as exc:
                self.error=exc

    def _retry(self,x,y,left,guard,generation):
        try:
            self._press(x,y,left,guard,generation,move=False)
        except Exception as exc:
            self.error=exc

    def release(self):
        with self.lock:
            self.generation+=1
            if self.timer:
                self.timer.cancel()
                self.timer=None
            if self.pressed:
                self._send(self._event(0x0004))
                self.pressed=False
