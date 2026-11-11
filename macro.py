"""Windows screen-only macro. Starts paused; no game memory access."""
import sys
from pathlib import Path
BASE = Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'packages'))
import ctypes
from ctypes import wintypes
import json
import queue
import threading
import time
import traceback
import tkinter as tk
from tkinter import messagebox, ttk
import cv2
import mss
# Layered-window GDI copying can flicker the physical cursor during capture.
try:
    from mss.windows import gdi as _mss_gdi
    _mss_gdi.CAPTUREBLT=0
except ImportError:
    try:
        import mss.windows as _mss_gdi
        _mss_gdi.CAPTUREBLT=0
    except ImportError:
        pass
import numpy as np
from PIL import Image, ImageTk
from vision import Detector, Tuner, parse_feedback, feedback_search_rect, detect_shu, ShuController, detect_en_prompt, recognize_en
from wininput import MouseInput, KeyboardInput

LOG_LOCK=threading.RLock()


def write_local_log(record):
    with LOG_LOCK:
        with (BASE/'LOGS.jsonl').open('a',encoding='utf-8') as handle:
            handle.write(json.dumps(record,ensure_ascii=True)+'\n')


class ActivityQueue(queue.Queue):
    def put(self,value,*args,**kwargs):
        try:
            write_local_log({'time':time.time(),'event':'activity','message':str(value)})
        except OSError:
            pass
        return super().put(value,*args,**kwargs)


def migrate_logs():
    legacy=BASE/'events.jsonl'
    target=BASE/'LOGS.jsonl'
    with LOG_LOCK:
        if not legacy.exists():
            target.touch(exist_ok=True)
            return
        existing=target.read_text(encoding='utf-8',errors='replace') if target.exists() else ''
        known=set(existing.splitlines())
        with target.open('a',encoding='utf-8') as handle:
            for line in legacy.read_text(encoding='utf-8',errors='replace').splitlines():
                if line not in known:
                    handle.write(line+'\n')
                    known.add(line)
        try:
            legacy.unlink()
        except OSError:
            pass  # An older running copy may still hold the legacy file open.

APP_ICON_PNG_BASE64 = (
    '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'
)

USER = ctypes.windll.user32
USER.GetForegroundWindow.restype = wintypes.HWND
USER.GetAsyncKeyState.argtypes = [ctypes.c_int]
USER.GetAsyncKeyState.restype = ctypes.c_short
USER.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
USER.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
USER.ClientToScreen.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.POINT)]
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    USER.SetProcessDPIAware()


def foreground_is_roblox():
    hwnd = USER.GetForegroundWindow()
    title = ctypes.create_unicode_buffer(512)
    USER.GetWindowTextW(hwnd,title,512)
    return 'roblox' in title.value.lower()


def roblox_client_region():
    if not foreground_is_roblox():
        return None
    hwnd=USER.GetForegroundWindow()
    rect=wintypes.RECT()
    point=wintypes.POINT()
    if not USER.GetClientRect(hwnd,ctypes.byref(rect)) or not USER.ClientToScreen(hwnd,ctypes.byref(point)):
        return None
    return {'left':point.x,'top':point.y,'width':rect.right,'height':rect.bottom}


class RobloxWindowCapture:
    """Capture Roblox independently of the foreground window and input state."""
    def __init__(self,events):
        self.events=events
        self.lock=threading.Lock()
        self.control=None
        self.capture=None
        self.hwnd=None
        self.frame=None
        self.stamp=0.
        self.sequence=0
        self.connecting=False
        self.closed=False
        self.attempt=0.
        self.last_error=None
        self.status='Desktop capture'
        USER.FindWindowW.argtypes=[wintypes.LPCWSTR,wintypes.LPCWSTR]
        USER.FindWindowW.restype=wintypes.HWND
        USER.IsIconic.argtypes=[wintypes.HWND]
        USER.IsWindow.argtypes=[wintypes.HWND]
        USER.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]

    def _connect(self,hwnd):
        try:
            from windows_capture import WindowsCapture
            capture=WindowsCapture(window_hwnd=int(hwnd),cursor_capture=False,draw_border=False,minimum_update_interval=16)
            @capture.event
            def on_frame_arrived(frame,control):
                if self.closed:
                    control.stop();return
                pixels=frame.frame_buffer[:,:,:3].copy()
                with self.lock:
                    self.frame=pixels;self.stamp=time.perf_counter();self.sequence+=1
            @capture.event
            def on_closed():
                with self.lock:self.frame=None;self.hwnd=None;self.control=None
            control=capture.start_free_threaded()
            with self.lock:
                stopped=self.closed
                if not stopped:self.capture=capture;self.control=control;self.hwnd=hwnd
            if stopped:
                control.stop();return
            self.last_error=None
            self.events.put('Live Roblox window capture ready; detection continues when the macro panel is in front.')
        except Exception as exc:
            message=str(exc)
            if message!=self.last_error:
                self.events.put('Window capture unavailable; using cursor-safe desktop capture: '+message)
                self.last_error=message
        finally:self.connecting=False

    def read(self,region):
        now=time.perf_counter()
        if not self.closed and self.control is None and not self.connecting and now-self.attempt>3:
            self.attempt=now
            hwnd=USER.FindWindowW(None,'Roblox')
            if hwnd:
                self.connecting=True
                threading.Thread(target=self._connect,args=(hwnd,),daemon=True).start()
        with self.lock:
            pixels=self.frame
            stamp=self.stamp;sequence=self.sequence;hwnd=self.hwnd
        if hwnd and USER.IsIconic(hwnd):
            self.status='Roblox minimized - restore it for live frames'
            return np.zeros((region['height'],region['width'],3),np.uint8)
        if pixels is None or not hwnd:
            self.status='Starting window capture' if self.connecting else 'Desktop capture'
            return None
        age=now-stamp
        if age>.6:
            self.status='Waiting for a new Roblox frame - keep the game restored'
            return np.zeros((region['height'],region['width'],3),np.uint8)
        rect=wintypes.RECT();point=wintypes.POINT()
        if not USER.GetClientRect(hwnd,ctypes.byref(rect)) or not USER.ClientToScreen(hwnd,ctypes.byref(point)):return None
        cw,ch=rect.right,rect.bottom
        if cw<=0 or ch<=0:return None
        height,width=pixels.shape[:2]
        cx=cy=0
        if (width,height)!=(cw,ch):
            outer=wintypes.RECT()
            try:
                dwm=ctypes.windll.dwmapi
                dwm.DwmGetWindowAttribute.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
                if dwm.DwmGetWindowAttribute(hwnd,9,ctypes.byref(outer),ctypes.sizeof(outer))!=0:raise OSError('No visible frame bounds')
            except OSError:USER.GetWindowRect(hwnd,ctypes.byref(outer))
            cx=max(0,point.x-outer.left);cy=max(0,point.y-outer.top)
        client=pixels[cy:min(height,cy+ch),cx:min(width,cx+cw)]
        if client.shape[:2]!=(ch,cw):
            self.status='Window geometry changed - waiting for matching frame'
            return None
        canvas=np.zeros((region['height'],region['width'],3),np.uint8)
        x0=max(point.x,region['left']);y0=max(point.y,region['top'])
        x1=min(point.x+cw,region['left']+region['width']);y1=min(point.y+ch,region['top']+region['height'])
        if x1>x0 and y1>y0:
            canvas[y0-region['top']:y1-region['top'],x0-region['left']:x1-region['left']]=client[y0-point.y:y1-point.y,x0-point.x:x1-point.x]
        self.status=f'Live Roblox window - frame {sequence} - {age*1000:.0f} ms old'
        return canvas

    def close(self):
        self.closed=True
        with self.lock:control=self.control;self.control=None
        if control:
            try:control.stop()
            except Exception:pass


KEY_CODES={**{f'F{i}':0x6f+i for i in range(1,25)},**{c:ord(c) for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'},
           **{f'Numpad{i}':0x60+i for i in range(10)},
           'Space':0x20,'Home':0x24,'End':0x23,'Insert':0x2d,'Delete':0x2e,'Pause':0x13,
           'PageUp':0x21,'PageDown':0x22,'Left':0x25,'Up':0x26,'Right':0x27,'Down':0x28,
           'Tab':0x09,'Enter':0x0d,'Escape':0x1b,'Backspace':0x08,'CapsLock':0x14,
           'Multiply':0x6a,'Add':0x6b,'Subtract':0x6d,'Decimal':0x6e,'Divide':0x6f}
MODIFIER_CODES={'Ctrl':0x11,'Alt':0x12,'Shift':0x10,'Win':0x5b}


def binding_codes(text):
    parts=text.split('+')
    if parts[-1].startswith('Key') and parts[-1][3:].isdigit() and 8<=int(parts[-1][3:])<=254:
        KEY_CODES[parts[-1]]=int(parts[-1][3:])
    if not parts or parts[-1] not in KEY_CODES or any(p not in MODIFIER_CODES for p in parts[:-1]):
        raise ValueError('Press a supported key, optionally with Ctrl, Alt, Shift or Win.')
    if len(set(parts))!=len(parts):
        raise ValueError('A modifier cannot appear twice.')
    return tuple(code for label,code in MODIFIER_CODES.items() if label in parts[:-1])+(KEY_CODES[parts[-1]],)


def binding_down(codes):
    return all((USER.GetAsyncKeyState(key)&0x8000) or (key==0x5b and USER.GetAsyncKeyState(0x5c)&0x8000) for key in codes)


class Tooltip:
    def __init__(self,widget,text):
        self.widget,self.text,self.job,self.window=widget,text,None,None
        widget.bind('<Enter>',self.enter,add='+')
        widget.bind('<Leave>',self.hide,add='+')
        widget.bind('<ButtonPress>',self.hide,add='+')
        widget.bind('<Destroy>',self.hide,add='+')
    def enter(self,event=None):
        self.hide()
        self.job=self.widget.after(450,self.show)
    def show(self):
        self.job=None
        self.window=tk.Toplevel(self.widget)
        self.window.overrideredirect(True)
        self.window.attributes('-topmost',True)
        tk.Label(self.window,text=self.text,wraplength=320,justify='left',bg='#28364b',fg='#eef3fa',
                 font=('Segoe UI',10),padx=12,pady=9).pack()
        self.window.update_idletasks()
        x=min(self.widget.winfo_pointerx()+12,self.widget.winfo_screenwidth()-self.window.winfo_width()-8)
        y=min(self.widget.winfo_pointery()+18,self.widget.winfo_screenheight()-self.window.winfo_height()-8)
        self.window.geometry(f'+{max(0,x)}+{max(0,y)}')
    def hide(self,event=None):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job=None
        if self.window:
            self.window.destroy()
            self.window=None


class App:
    def __init__(self):
        migrate_logs()
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('BeyondNen.MeditationMacro')
        except OSError:
            pass
        self.root = tk.Tk()
        self.app_icon=tk.PhotoImage(data=APP_ICON_PNG_BASE64)
        self.root.iconphoto(True,self.app_icon)
        self.root.title('Beyond Nen | Training Assistant')
        self.root.geometry('790x950')
        self.root.minsize(710,920)
        self.running = threading.Event()
        self.closed = threading.Event()
        self.frames = queue.Queue(maxsize=1)
        self.ocr_frames = queue.Queue(maxsize=1)
        self.results = queue.Queue()
        self.en_results=queue.Queue()
        self.en_frames=queue.Queue(maxsize=1)
        self.en_ready=False
        self.keyboard=KeyboardInput()
        self.deliveries = queue.Queue()
        self.events = ActivityQueue()
        self.window_capture=RobloxWindowCapture(self.events)
        self.ocr_ready = False
        self.config = {'game':None,'feedback':None,'lead_ms':12.,'click_hold_ms':35.,'auto_feedback':True,'capture_mode':'custom'}
        if (BASE/'config.json').exists():
            self.config.update(json.loads((BASE/'config.json').read_text()))
        self.config['click_hold_ms']=min(25,max(15,float(self.config['click_hold_ms'])))
        self.config.setdefault('start_key','F1')
        self.config.setdefault('pause_key','F2')
        if self.config.get('cursor_motion_revision')!=1:
            self.config.update(cursor_motion_revision=1,lead_ms=12.)
            self.save()
            self.events.put('Smooth cursor travel enabled; previous click timing reset for recalibration.')
        self.training=self.config.get('training_mode','Ren/Ten')
        if self.training not in ('Ren/Ten','Shu','En'):self.training='Ren/Ten'
        try:
            configured=(binding_codes(self.config['start_key']),binding_codes(self.config['pause_key']))
            assert not(set(configured[0])<=set(configured[1]) or set(configured[1])<=set(configured[0]))
        except (ValueError,AssertionError):
            self.config.update(start_key='F1',pause_key='F2')
            configured=((KEY_CODES['F1'],),(KEY_CODES['F2'],))
        self.hotkeys=configured
        self.mouse=MouseInput(self.config['click_hold_ms'])
        self.status = tk.StringVar(value=f"Paused. Select a game area or full screen, then press {self.config['start_key']} in Roblox.")
        self.auto_feedback=tk.BooleanVar(value=self.config['auto_feedback'])
        self.feedback_info=tk.StringVar(value='Automatic feedback: waiting for a result')
        self.keys = {binding:binding_down(binding) for binding in self.hotkeys}
        self.start_key=tk.StringVar(value=self.config['start_key'])
        self.pause_key=tk.StringVar(value=self.config['pause_key'])
        self.key_hint=tk.StringVar()
        self.capture_error=None
        self.recording=False
        self.session = 0
        self.sent_count=0
        self.latest_feedback='—'
        self.metrics=queue.Queue()
        self.scan_info=tk.StringVar(value='Waiting for a capture area')
        self.capture_info=tk.StringVar(value='Live capture starts after choosing a game area')
        self.color_info=tk.StringVar(value='Checking colors…')
        self.panel_bounds=None
        self.live_tracks=()
        self.build_ui()
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.root.report_callback_exception=self.report_ui_error
        threading.Thread(target=self.capture_loop,daemon=True).start()
        threading.Thread(target=self.ocr_loop,daemon=True).start()
        threading.Thread(target=lambda:self.ocr_loop(en_only=True),daemon=True).start()
        self.root.after(30,self.pump)

    def report_ui_error(self,error_type,value,tb):
        self.pause()
        self.capture_error=str(value)
        write_local_log({'time':time.time(),'event':'ui_error','error':str(value),
                         'traceback':''.join(traceback.format_exception(error_type,value,tb))})
        self.events.put(f'ERROR — {value}. Details saved in LOGS.jsonl.')

    def build_ui(self):
        bg,card,ink,muted,accent='#10151f','#1a2230','#eef3fa','#98a7bc','#63e5bf'
        self.colors=(bg,card,ink,muted,accent)
        self.root.configure(bg=bg)
        style=ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('TButton',font=('Segoe UI',10),padding=(14,9),background='#29364a',foreground=ink,borderwidth=0)
        style.map('TButton',background=[('active','#35465f')])
        style.configure('TCheckbutton',font=('Segoe UI',10),background=card,foreground=ink,padding=4)
        style.map('TCheckbutton',background=[('active',card)],indicatorcolor=[('selected',accent),('!selected','#35465f')])
        outer=tk.Frame(self.root,bg=bg)
        outer.pack(fill='both',expand=True,padx=24,pady=16)
        header=tk.Frame(outer,bg=bg)
        header.pack(fill='x')
        tk.Label(header,text='BEYOND NEN',font=('Segoe UI',22,'bold'),fg=ink,bg=bg).pack(side='left')
        self.badge=tk.Label(header,text='  PAUSED  ',font=('Segoe UI',9,'bold'),fg=muted,bg=card,padx=8,pady=7)
        self.badge.pack(side='right')
        tk.Label(outer,text='Training Assistant',font=('Segoe UI',10),fg=muted,bg=bg).pack(anchor='w',pady=(2,10))
        style.configure('TNotebook',background=bg,borderwidth=0)
        style.configure('TNotebook.Tab',font=('Segoe UI',11,'bold'),padding=(20,8),background=card,foreground=ink)
        style.map('TNotebook.Tab',background=[('selected','#29364a')],foreground=[('selected',accent)])
        self.tabs=ttk.Notebook(outer)
        self.tabs.pack(fill='x',pady=(0,10))
        for name,description in (('Ren/Ten','Track shrinking rings and time clicks on the circles.'),('Shu','The macro holds and releases left-click to keep the indicator inside the target zone.'),('En','The macro reads each letter prompt and presses the matching key before the timer runs out.')):
            panel=tk.Frame(self.tabs,bg=card)
            tk.Label(panel,text=description,font=('Segoe UI',9),bg=card,fg=muted,padx=12,pady=8).pack(anchor='w')
            if name=='Ren/Ten':
                tk.Label(panel,text='Meditation aura and other effects can interfere with circle detection. Aim your camera at a clearer area and set Roblox graphics to Manual, quality 1.',
                         font=('Segoe UI',9),bg=card,fg='#e7c779',wraplength=680,justify='left',padx=12,pady=6).pack(anchor='w',fill='x')
            self.tabs.add(panel,text=name)
        self.tabs.select(('Ren/Ten','Shu','En').index(self.training))
        setup=tk.Frame(outer,bg=card,padx=16,pady=14)
        setup.pack(fill='x')
        tk.Label(setup,text='CAPTURE AREAS',font=('Segoe UI',9,'bold'),fg=muted,bg=card).pack(anchor='w')
        row=tk.Frame(setup,bg=card)
        row.pack(fill='x',pady=(10,7))
        for title,command,help_text in (
            ('Select game',lambda:self.select('game'),'Drag a rectangle around Roblox. Only this area is scanned for targets.'),
            ('Use full screen',self.use_full_screen,'Scan your entire primary display. Keep Roblox on that display; the start key is still required to enable clicks.'),
            ('Select feedback',lambda:self.select('feedback'),'Feedback means the MISS or signed decimal result after a click. Select that text area manually if automatic reading fails. This switches to manual feedback.')):
            button=ttk.Button(row,text=title,command=command)
            button.pack(side='left',padx=(0,8))
            if title=='Select feedback':self.feedback_select_button=button
            Tooltip(button,help_text)
        feedback_row=tk.Frame(setup,bg=card)
        feedback_row.pack(fill='x',pady=(0,5))
        auto_check=ttk.Checkbutton(feedback_row,text='Automatic feedback',variable=self.auto_feedback,command=self.set_feedback_mode)
        auto_check.pack(side='left')
        self.auto_feedback_check=auto_check
        Tooltip(auto_check,'Automatically read MISS and signed decimal results on the game’s right side. Confirmed results adjust timing toward +0.04 or higher. Unclear text does not change timing.')
        tk.Label(feedback_row,textvariable=self.feedback_info,font=('Segoe UI',9),fg=muted,bg=card).pack(side='right')
        bindings=tk.Frame(setup,bg=card)
        bindings.pack(fill='x',pady=(0,5))
        for title,variable in (('Start / pause',self.start_key),('Pause',self.pause_key)):
            tk.Label(bindings,text=title,font=('Segoe UI',9),fg=muted,bg=card).pack(side='left',padx=(0,5))
            choice=ttk.Combobox(bindings,textvariable=variable,values=tuple(KEY_CODES),state='readonly',width=8)
            choice.pack(side='left',padx=(0,4))
            choice.bind('<<ComboboxSelected>>',self.set_keybinds)
            Tooltip(choice,'Choose a preset key, or use Record to detect your own key combination. Changing a binding pauses the macro.')
            record=ttk.Button(bindings,text='Record',command=lambda v=variable:self.record_keybind(v))
            record.pack(side='left',padx=(0,14))
            Tooltip(record,'Press your desired keyboard key, with optional Ctrl, Alt, Shift or Win modifiers. Click Cancel to leave the binding unchanged.')
        self.menu_hint=tk.StringVar()
        tk.Label(setup,textvariable=self.menu_hint,font=('Segoe UI',9),fg=accent,bg=card,anchor='w').pack(fill='x',pady=(2,4))
        self.area_label=tk.Label(setup,text='',font=('Segoe UI',9),fg=muted,bg=card,anchor='w')
        self.area_label.pack(fill='x')
        self.update_area_label()
        stats=tk.Frame(outer,bg=bg)
        stats.pack(fill='x',pady=12)
        self.stat_labels=[]
        self.stat_titles=[]
        for index,(title,value) in enumerate((('TARGETS CLICKED','0'),('LAST RESULT','—'),('CLICK PATTERN','Until resolved'))):
            stats.columnconfigure(index,weight=1,uniform='stat')
            box=tk.Frame(stats,bg=card,padx=14,pady=10)
            box.grid(row=0,column=index,sticky='ew',padx=(0,8) if index<2 else 0)
            stat_title=tk.Label(box,text=title,font=('Segoe UI',8,'bold'),fg=muted,bg=card)
            stat_title.pack(anchor='w')
            self.stat_titles.append(stat_title)
            label=tk.Label(box,text=value,font=('Segoe UI',15,'bold'),fg=accent,bg=card)
            label.pack(anchor='w',pady=(3,0))
            self.stat_labels.append(label)
        live=tk.Frame(outer,bg=card,padx=12,pady=10)
        live.pack(fill='both',expand=True)
        live_header=tk.Frame(live,bg=card)
        live_header.pack(fill='x',pady=(0,8))
        tk.Label(live_header,text='LIVE TRACKING',font=('Segoe UI',9,'bold'),fg=muted,bg=card).pack(side='left')
        tk.Label(live_header,textvariable=self.scan_info,font=('Segoe UI',9),fg=accent,bg=card).pack(side='right')
        self.preview=tk.Canvas(live,bg='#0c1119',height=110,highlightthickness=0)
        self.preview.pack(fill='both',expand=True)
        self.preview.create_text(350,110,text='Your game preview will appear here',fill=muted,font=('Segoe UI',12),tags='placeholder')
        self.preview.bind('<Configure>',lambda e:self.preview.coords('placeholder',e.width/2,e.height/2))
        tk.Label(live,textvariable=self.capture_info,font=('Segoe UI',8),fg=muted,bg=card,anchor='w').pack(fill='x',pady=(4,0))
        legend=tk.Frame(live,bg=card)
        legend.pack(fill='x',pady=(7,0))
        self.legend_label=tk.Label(legend,text='',font=('Segoe UI',9),fg=muted,bg=card)
        self.legend_label.pack(side='left')
        self.color_label=tk.Label(legend,textvariable=self.color_info,font=('Segoe UI',9,'bold'),fg=muted,bg=card)
        self.color_label.pack(side='right')
        tk.Label(outer,textvariable=self.status,font=('Segoe UI',9),fg=ink,bg=bg,wraplength=720,anchor='w',justify='left').pack(fill='x',pady=(12,8))
        activity=tk.Frame(outer,bg=card,padx=10,pady=8)
        activity.pack(fill='x')
        tk.Label(activity,text='ACTIVITY',font=('Segoe UI',8,'bold'),fg=muted,bg=card).pack(anchor='w',pady=(0,5))
        scroll=ttk.Scrollbar(activity)
        scroll.pack(side='right',fill='y')
        self.log=tk.Text(activity,height=4,bg=card,fg=muted,insertbackground=ink,font=('Consolas',9),relief='flat',state='disabled',wrap='word',yscrollcommand=scroll.set)
        self.log.pack(fill='x')
        scroll.configure(command=self.log.yview)
        footer=tk.Frame(outer,bg=bg)
        footer.pack(fill='x',pady=(12,0))
        tk.Label(footer,textvariable=self.key_hint,font=('Segoe UI',10,'bold'),fg=accent,bg=bg).pack(side='left')
        self.update_key_hint()
        pause_button=ttk.Button(footer,text='Pause',command=self.stop_button)
        pause_button.pack(side='right')
        Tooltip(pause_button,'Pause controls and cancel pending mouse or key input. Live tracking continues while paused.')
        self.refresh_training_ui()
        self.tabs.bind('<<NotebookTabChanged>>',self.change_training)

    def refresh_training_ui(self):
        shu=self.training=='Shu'
        en=self.training=='En'
        self.update_area_label()
        for label,text in zip(self.stat_titles,('KEYS SENT','LAST RESULT','PROMPT') if en else ('FOCUS','CYCLES','MOUSE CONTROL') if shu else ('TARGETS CLICKED','LAST RESULT','CLICK PATTERN')):
            label.configure(text=text)
        for label,text in zip(self.stat_labels,('0','—','Waiting') if en else ('—','0','Released') if shu else (str(self.sent_count),'—','Until resolved')):
            label.configure(text=text)
        self.legend_label.configure(text='Cyan: verified prompt area; unclear letters are skipped' if en else 'Gold: target zone   •   Cyan: indicator' if shu else 'Green: target    •    Magenta: shrinking ring')
        self.feedback_select_button.state(['disabled'] if shu else ['!disabled'])
        self.auto_feedback_check.state(['disabled'] if shu else ['!disabled'])
        if shu:self.feedback_info.set('Shu reads its focus bar directly')
        else:self.feedback_info.set('Automatic feedback: waiting for a result' if self.config.get('auto_feedback',True) else 'Manual feedback selected')
        self.color_info.set('Waiting for En prompt' if en else 'Waiting for Shu bar' if shu else 'Checking colors…')

    def change_training(self,event=None):
        selected=self.tabs.tab(self.tabs.select(),'text')
        if selected==self.training:return
        self.pause()
        self.training=selected
        self.config['training_mode']=selected
        self.save()
        self.refresh_training_ui()
        self.status.set(f'{selected} selected. Input PAUSED; press your start key in Roblox to begin.')
        self.events.put(f'Training selected: {selected}; input released.')

    def update_key_hint(self):
        self.key_hint.set(f"{self.config['start_key']}  Start / pause     {self.config['pause_key']}  Pause")
        self.menu_hint.set(f"Stay in meditation: open Roblox menu (Esc) → press {self.config['start_key']} → close menu.")

    def set_keybinds(self,event=None):
        self.pause()
        start,pause=self.start_key.get(),self.pause_key.get()
        try:
            codes=(binding_codes(start),binding_codes(pause))
            if set(codes[0])<=set(codes[1]) or set(codes[1])<=set(codes[0]):
                raise ValueError('Start and pause bindings must not overlap.')
        except ValueError as exc:
            self.start_key.set(self.config['start_key'])
            self.pause_key.set(self.config['pause_key'])
            self.status.set(str(exc))
            return
        self.config.update(start_key=start,pause_key=pause)
        self.hotkeys=codes
        self.keys={binding:binding_down(binding) for binding in self.hotkeys}
        self.update_key_hint()
        self.save()
        self.status.set(f'Keys saved. Clicks PAUSED. Focus Roblox and press {start} to start.')

    def record_keybind(self,variable):
        self.pause()
        self.recording=True
        dialog=tk.Toplevel(self.root)
        dialog.title('Record keybind')
        dialog.configure(bg='#1a2230')
        dialog.resizable(False,False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.bind('<Destroy>',lambda e:setattr(self,'recording',False) if e.widget is dialog else None)
        text=tk.StringVar(value='Press a key or combination.\nYou can hold Ctrl, Alt, Shift or Win.')
        tk.Label(dialog,textvariable=text,bg='#1a2230',fg='#eef3fa',font=('Segoe UI',11),padx=25,pady=20).pack()
        ttk.Button(dialog,text='Cancel',command=dialog.destroy).pack(pady=(0,14))
        def pressed(event):
            key=int(event.keycode)
            if key in (0x10,0x11,0x12,0x5b,0x5c,0xa0,0xa1,0xa2,0xa3,0xa4,0xa5):
                return 'break'
            name=next((name for name,code in KEY_CODES.items() if code==key),None)
            if name is None:
                name='Key'+str(key)
                KEY_CODES[name]=key
            modifiers=[]
            for label,code in MODIFIER_CODES.items():
                held=bool(USER.GetAsyncKeyState(code)&0x8000)
                if label=='Win': held=held or bool(USER.GetAsyncKeyState(0x5c)&0x8000)
                if held: modifiers.append(label)
            variable.set('+'.join(modifiers+[name]))
            dialog.destroy()
            self.set_keybinds()
            return 'break'
        dialog.bind('<KeyPress>',pressed)
        dialog.after_idle(dialog.focus_force)

    def update_area_label(self):
        parts=[]
        for key in ('game','feedback'):
            region=self.config.get(key)
            if key=='feedback' and self.training=='Shu':
                parts.append('Feedback: Shu focus meter')
            elif key=='feedback' and self.config.get('auto_feedback',True):
                parts.append('Feedback: automatic'+(' (manual saved)' if region else ''))
            else:
                prefix='Full screen: ' if key=='game' and self.config.get('capture_mode')=='full_screen' else key.capitalize()+': '
                parts.append(prefix+(f"{region['width']} × {region['height']} saved" if region else 'not selected'))
        self.area_label.configure(text='     •     '.join(parts))

    def use_full_screen(self):
        self.pause()
        try:
            with mss.mss() as sct:
                screen=sct.monitors[1]
                self.config['game']={k:int(screen[k]) for k in ('left','top','width','height')}
            self.config['capture_mode']='full_screen'
            self.save()
            self.update_area_label()
            self.status.set(f"Full screen selected (primary display). Focus Roblox and press {self.config['start_key']} to start.")
        except Exception as exc:
            messagebox.showerror('Full-screen capture',str(exc))

    def set_feedback_mode(self):
        self.pause()
        self.config['auto_feedback']=bool(self.auto_feedback.get())
        self.save()
        self.update_area_label()
        self.feedback_info.set('Automatic feedback: waiting for a result' if self.config['auto_feedback'] else 'Manual feedback selected')
        self.status.set(f"Feedback mode changed; clicks paused. {self.config['start_key']} in Roblox resumes.")

    def stop_button(self):
        self.pause()
        self.status.set('Input PAUSED. Live tracking continues. Focus Roblox and press the start key to resume.')

    def save(self):
        (BASE/'config.json').write_text(json.dumps(self.config,indent=2))

    def pause(self):
        self.running.clear()
        self.session += 1
        try:self.keyboard.release()
        except OSError as exc:self.events.put(f'Keyboard release failed: {exc}')
        try:
            self.mouse.set_enabled(False)
        except OSError as exc:
            self.events.put(f'Mouse release failed: {exc}')

    def select(self,key):
        self.pause()
        self.root.withdraw()
        self.root.update()
        time.sleep(.25)
        try:
            with mss.mss() as sct:
                monitor=sct.monitors[0]
                image=np.asarray(sct.grab(monitor))[:,:,:3].copy()
            title='Drag rectangle, then ENTER. ESC cancels.'
            cv2.namedWindow(title,cv2.WINDOW_NORMAL)
            cv2.resizeWindow(title,min(1400,image.shape[1]),min(850,image.shape[0]))
            x,y,w,h=cv2.selectROI(title,image,False,False)
            cv2.destroyAllWindows()
            if w and h:
                self.config[key]={'left':int(x+monitor['left']),'top':int(y+monitor['top']),'width':int(w),'height':int(h)}
                if key=='game':
                    self.config['capture_mode']='custom'
                else:
                    self.config['auto_feedback']=False
                    self.auto_feedback.set(False)
                    self.feedback_info.set('Manual feedback selected')
                self.save()
                self.update_area_label()
                self.status.set(f"{key.capitalize()} area saved. {self.config['start_key']} starts with Roblox focused.")
        except Exception as exc:
            messagebox.showerror('Selection failed',str(exc))
        finally:
            self.root.deiconify()

    def ocr_loop(self,en_only=False):
        try:
            from rapidocr_onnxruntime import RapidOCR
            engine=RapidOCR(intra_op_num_threads=1,inter_op_num_threads=1)
            if en_only:self.en_ready=True
            else:self.ocr_ready=True
            self.events.put('En letter reader ready' if en_only else 'Feedback OCR ready')
        except Exception as exc:
            self.events.put(f'OCR failed; click mode unavailable: {exc}')
            return
        while not self.closed.is_set():
            try:
                job=(self.en_frames if en_only else self.ocr_frames).get(timeout=.2)
                session,stamp,image=job[:3]
                automatic=bool(job[3]) if len(job)>3 else False
            except queue.Empty:
                continue
            try:
                if len(job)>4 and job[4]=='en':
                    token=job[5]
                    key=recognize_en(engine,image)
                    self.en_results.put((session,stamp,token,key))
                    continue
                # Upscaling makes the small game font readable without slowing the tracking thread.
                scale=max(2., min(4.,80/image.shape[0]))
                enlarged=cv2.resize(image,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
                result,_=engine(enlarged)
                items=[(r[1],float(r[2])) for r in (result or [])]
                if automatic:
                    items=[item for item in items if item[1]>=.90]
                self.results.put((session,stamp,parse_feedback(items),items))
            except Exception as exc:
                self.events.put(f'OCR error: {exc}')

    @staticmethod
    def latest(q,value):
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        try:
            q.put_nowait(value)
        except queue.Full:
            pass

    def capture_loop(self):
        detector=Detector()
        en_token=0
        en_signature=None
        en_last_seen=0.
        en_session=-1
        en_sent=False
        en_count=0
        en_key=None
        en_last_job=0.
        en_unknown=False
        en_last_feedback=None
        en_last_feedback_job=0.
        en_missing_reported=False
        shu=ShuController()
        last_shu_session=-1
        shu_visible=False
        shu_last_seen=time.perf_counter()
        shu_missing_reported=False
        shu_cycles=0
        tuner=Tuner(self.config['lead_ms'])
        previous_session=-1
        pending=None
        feedback_last=None
        feedback_count=0
        last_blank=0.
        last_click=-10.
        last_ocr=last_preview=0.
        frame_interval=.016
        last_stamp=time.perf_counter()
        last_color_status=None
        last_region=None
        last_target_seen=time.perf_counter()
        no_target_reported=False
        previous_tracks=()
        last_cancellation=None
        try:
            with mss.mss() as sct, (BASE/'LOGS.jsonl').open('a',buffering=1) as log:
                while not self.closed.is_set():
                    if not self.config.get('game'):
                        self.closed.wait(.025)
                        continue
                    if self.running.is_set() and not foreground_is_roblox():
                        self.pause()
                        self.events.put('Input PAUSED: Roblox lost focus. Focus Roblox and press the start key to resume.')
                    session=self.session
                    if self.keyboard.error:raise self.keyboard.error
                    if self.mouse.error:
                        raise self.mouse.error
                    cancellation=getattr(self.mouse,'last_cancellation',None)
                    if cancellation and cancellation!=last_cancellation:
                        self.events.put(cancellation[1])
                        log.write(json.dumps({'time':time.time(),'event':'click_cancelled','reason':cancellation[1]})+'\n')
                        last_cancellation=cancellation
                    if session!=previous_session:
                        for track in detector.tracks:
                            track.clicked=False
                            track.scheduled=False
                        pending=None
                        feedback_last=None
                        feedback_count=0
                        previous_session=session
                        last_stamp=time.perf_counter()
                        frame_interval=.016
                        last_target_seen=time.perf_counter()
                        no_target_reported=False
                    region=self.config['game']
                    region_key=tuple(region[k] for k in ('left','top','width','height'))
                    if region_key!=last_region:
                        known_hue=detector.hue
                        detector=Detector()
                        detector.hue=known_hue
                        previous_tracks=()
                        last_region=region_key
                    start=time.perf_counter()
                    frame=self.window_capture.read(region)
                    window_frame=frame is not None
                    if frame is None:frame=np.asarray(sct.grab(region))[:,:,:3].copy()
                    self.metrics.put(('capture_status',self.window_capture.status))
                    # When inspecting the panel, do not detect circles inside
                    # its own scaled preview. Bounds are cached by the UI thread.
                    bounds=self.panel_bounds
                    if bounds and not window_frame and not foreground_is_roblox():
                        px,py,pw,ph=bounds
                        x0=max(0,px-region['left']); y0=max(0,py-region['top'])
                        x1=min(frame.shape[1],px+pw-region['left']); y1=min(frame.shape[0],py+ph-region['top'])
                        if x1>x0 and y1>y0:
                            frame[y0:y1,x0:x1]=0
                    stamp=self.window_capture.stamp if window_frame and self.window_capture.stamp else (start+time.perf_counter())/2
                    processed_at=time.perf_counter()
                    frame_interval=.85*frame_interval+.15*min(.1,max(.001,processed_at-last_stamp))
                    last_stamp=processed_at
                    detection_scale=min(1.,960/frame.shape[1])
                    detection_frame=cv2.resize(frame,None,fx=detection_scale,fy=detection_scale,interpolation=cv2.INTER_AREA) if detection_scale<1 else frame
                    if self.training=='En':
                        now=time.perf_counter()
                        if en_session!=session:
                            en_token+=1;en_signature=None;en_sent=False;en_key=None;en_unknown=False
                            en_last_seen=now;en_session=session;en_missing_reported=False
                        prompt=detect_en_prompt(detection_frame)
                        if prompt is not None:
                            changed=en_signature is None or np.mean(prompt.signature!=en_signature)>.22
                            if changed:
                                en_token+=1;en_sent=False;en_key=None;en_unknown=False
                                en_signature=prompt.signature.copy()
                            en_last_seen=now
                            en_missing_reported=False
                            if not en_sent and now-en_last_job>.12:
                                self.latest(self.en_frames,(session,now,(prompt.glyph.copy(),prompt.label.copy()),False,'en',en_token))
                                en_last_job=now
                        elif now-en_last_seen>.10 and en_signature is not None:
                            en_token+=1;en_signature=None;en_sent=False;en_key=None;en_unknown=False
                        if self.running.is_set() and now-en_last_seen>6 and not en_missing_reported:
                            self.events.put('No En prompt detected. Check the capture area and keep the minigame visible; no keys sent.')
                            en_missing_reported=True
                        while True:
                            try:sid,ts,token,key=self.en_results.get_nowait()
                            except queue.Empty:break
                            if sid!=session or token!=en_token or now-ts>.40 or prompt is None or en_sent:continue
                            if key is None:
                                if not en_unknown:
                                    self.events.put('En prompt unclear or unsupported; no key sent. Checking again.')
                                    en_unknown=True
                                continue
                            en_key=key
                            def key_allowed(sid=session):
                                return (self.running.is_set() and self.session==sid and not self.closed.is_set()
                                        and self.training=='En' and foreground_is_roblox()
                                        and not any(binding_down(b) for b in self.hotkeys if not self.keyboard.suppresses(b))
                                        and not any(ctypes.windll.user32.GetAsyncKeyState(v)&0x8000 for v in (0x10,0x11,0x12,0x5B,0x5C)))
                            if not self.running.is_set():
                                en_sent=True
                                self.events.put(f'En recognized {key}; input disabled while paused.')
                            elif self.keyboard.tap(key,key_allowed):
                                en_sent=True;en_count+=1
                                self.events.put(f'En prompt {key}: key sent.')
                        # Use the existing right-side/manual result reader between prompt jobs.
                        if self.running.is_set() and (prompt is None or en_sent) and now-en_last_feedback_job>.35:
                            automatic=self.config.get('auto_feedback',True)
                            if automatic:
                                search=feedback_search_rect(region,roblox_client_region())
                                feedback_image=np.asarray(sct.grab(search))[:,:,:3].copy() if search else None
                            else:
                                feedback_region=self.config.get('feedback')
                                feedback_image=np.asarray(sct.grab(feedback_region))[:,:,:3].copy() if feedback_region else None
                            if feedback_image is not None and feedback_image.size:
                                self.latest(self.ocr_frames,(session,now,feedback_image,automatic))
                            en_last_feedback_job=now
                        while True:
                            try:sid,ts,value,items=self.results.get_nowait()
                            except queue.Empty:break
                            if sid==session and now-ts<1 and value is not None and value!=en_last_feedback:
                                en_last_feedback=value
                                self.events.put('En result: '+(value if value=='MISS' else f'{value:+.2f}'))
                        if now-last_preview>.05:
                            if prompt:
                                x0,y0,x1,y1=[round(v/detection_scale) for v in prompt.rect]
                                cv2.rectangle(frame,(x0,y0),(x1,y1),(255,240,40),2)
                            self.latest(self.frames,frame)
                            self.metrics.put(('en',{'count':en_count,'key':en_key,'result':en_last_feedback,'tracked':prompt is not None,'fps':1/max(.001,frame_interval)}))
                            last_preview=now
                        self.closed.wait(.005 if self.running.is_set() else .045)
                        continue
                    if self.training=='Shu':
                        if last_shu_session!=session:
                            shu.previous=None
                            shu.velocity=0.
                            shu.holding=False
                            last_shu_session=session
                            shu_last_seen=time.perf_counter()
                            shu_missing_reported=False
                        bar=detect_shu(detection_frame)
                        now=time.perf_counter()
                        holding=shu.update(bar,now)
                        def hold_allowed(sid=session):
                            return (self.running.is_set() and not self.closed.is_set() and self.session==sid
                                    and self.training=='Shu' and foreground_is_roblox()
                                    and not any(binding_down(binding) for binding in self.hotkeys))
                        active=self.running.is_set()
                        self.mouse.set_hold(bool(bar and holding and active),guard=hold_allowed)
                        if bar:
                            shu_last_seen=now
                            shu_missing_reported=False
                            if not shu_visible:
                                self.events.put('Shu bar detected: white indicator and gold zone tracked.')
                            shu_visible=True
                        else:
                            if shu_visible:self.events.put('Shu bar disappeared; mouse released. Waiting for the next round.')
                            shu_visible=False
                            if self.running.is_set() and now-shu_last_seen>6 and not shu_missing_reported:
                                self.events.put('No Shu bar detected. Check the capture area and keep the minigame visible; mouse is released.')
                                shu_missing_reported=True
                        if shu.cycles!=shu_cycles:
                            self.events.put('Shu focus reached full and reset; continuing the next cycle.')
                            shu_cycles=shu.cycles
                        if now-last_preview>.05:
                            if bar:
                                x0,x1=round(bar.zone_left/detection_scale),round(bar.zone_right/detection_scale)
                                y0,y1=round(bar.top/detection_scale),round(bar.bottom/detection_scale)
                                marker=round(bar.marker/detection_scale)
                                cv2.rectangle(frame,(x0,y0),(x1,y1),(40,200,245),2)
                                cv2.line(frame,(marker,y0-3),(marker,y1+3),(255,240,40),2)
                            self.latest(self.frames,frame)
                            action='Paused' if not self.running.is_set() else 'Holding' if self.mouse.pressed else 'Released'
                            self.metrics.put(('shu',{'focus':bar.focus if bar else None,'cycles':shu.cycles,'action':action,'tracked':bar is not None,'fps':1/max(.001,frame_interval)}))
                            last_preview=now
                        self.closed.wait(.003 if self.running.is_set() else .045)
                        continue
                    tracks=detector.update(detection_frame,stamp)
                    self.live_tracks=tuple(tracks)
                    if detector.hue is not None and detector.color_status!=last_color_status:
                        self.events.put(detector.color_status)
                        last_color_status=detector.color_status
                    now=time.perf_counter()
                    if tracks:
                        last_target_seen=now
                        no_target_reported=False
                    elif self.running.is_set() and now-last_target_seen>6 and not no_target_reported:
                        self.events.put('No targets detected: check the capture area and keep the game visible. Still scanning.')
                        no_target_reported=True
                    active_ids={id(t) for t in tracks}
                    if self.running.is_set():
                        for old in previous_tracks:
                            if id(old) not in active_ids and not old.clicked and not getattr(old,'scheduled',False):
                                self.events.put('Target detected, but its shrinking ring could not be timed. No click was sent.')
                    previous_tracks=tuple(tracks)
                    while True:
                        try:
                            delivered_session,details=self.deliveries.get_nowait()
                        except queue.Empty:
                            break
                        log.write(json.dumps({'time':time.time(),'event':'mouse_delivered',**details})+'\n')
                        if delivered_session==session:
                            pending={'time':details['sent'],'baseline':feedback_last,'armed':feedback_last is None,'raw':None,'fallback':False}
                    # Apply only feedback captured after the most recent real click.
                    while True:
                        try:
                            sid,ts,value,items=self.results.get_nowait()
                        except queue.Empty:
                            break
                        if sid!=session:
                            continue
                        if pending and ts>pending['time'] and items and items!=pending.get('raw'):
                            pending['raw']=items
                            log.write(json.dumps({'time':time.time(),'event':'feedback_read','recognized':value,'text':items})+'\n')
                        if value is None:
                            if pending and ts>pending['time']+.04:
                                pending['armed']=True
                            if ts-last_blank>.25:
                                feedback_last=None
                                feedback_count=0
                            continue
                        last_blank=ts
                        feedback_count=feedback_count+1 if value==feedback_last else 1
                        feedback_last=value
                        confident=any(conf>=.90 and parse_feedback([(text,conf)])==value for text,conf in items)
                        if pending and pending['time']+.06 < ts < pending['time']+2.3 and (feedback_count>=2 or confident) and (pending['armed'] or value!=pending['baseline']):
                            msg=tuner.feedback(value)
                            self.config['lead_ms']=tuner.lead_ms
                            self.save()
                            log.write(json.dumps({'time':time.time(),'feedback':value,'lead_ms':tuner.lead_ms})+'\n')
                            self.events.put(f'{value}: {msg}')
                            self.metrics.put(('feedback',value))
                            self.mouse.release()
                            pending=None
                        elif pending and value!=pending['baseline']:
                            pending['armed']=True
                        elif not pending and value=='MISS' and feedback_count==2 and not self.config.get('auto_feedback',True):
                            msg=tuner.feedback(value)
                            self.config['lead_ms']=tuner.lead_ms
                            self.save()
                            log.write(json.dumps({'time':time.time(),'feedback':value,'unmatched_click':True,'lead_ms':tuner.lead_ms})+'\n')
                            self.events.put(f'MISS without a matching click: {msg}')
                            self.metrics.put(('feedback',value))
                    if pending and now-pending['time']>2.5:
                        self.events.put('No confirmed feedback; timing unchanged. Select feedback manually if needed.')
                        if self.config.get('auto_feedback',True):
                            self.metrics.put(('feedback_status','No result found — Select feedback to override'))
                        pending=None
                    for t in tracks:
                        if not self.running.is_set():
                            break
                        now=time.perf_counter()
                        remaining=t.remaining(now)
                        if remaining is None or t.clicked:
                            continue
                        if getattr(t,'scheduled',False):
                            self.mouse.update_target(round(region['left']+t.x/detection_scale),round(region['top']+t.y/detection_scale))
                            self.mouse.retime(now+remaining-tuner.lead_ms/1000)
                            continue
                        if now-last_click<.35:
                            continue
                        # Reserve the target well before contact. The mouse
                        # timer, not the next screen frame, dispatches input.
                        if now-t.seen>.14 or remaining>.85:
                            continue
                        if remaining<0:
                            t.scheduled=True
                            self.events.put('Target acquired too late for a timed click; no input sent')
                            log.write(json.dumps({'time':time.time(),'event':'late_target','remaining_ms':remaining*1000})+'\n')
                            continue
                        x=round(region['left']+t.x/detection_scale)
                        y=round(region['top']+t.y/detection_scale)
                        if self.running.is_set() and session==self.session and foreground_is_roblox():
                            # Check stop key immediately before sending mouse input, independently of the UI timer.
                            if any(binding_down(binding) for binding in self.hotkeys):
                                for key in self.hotkeys:
                                    if binding_down(key):
                                        self.keys[key]=True
                                self.pause()
                                self.events.put('Paused by stop key')
                                break
                            planned=now+remaining-tuner.lead_ms/1000
                            def burst_allowed(sid=session,target=t):
                                return (self.running.is_set() and not self.closed.is_set()
                                        and self.session==sid
                                        and time.perf_counter()-target.seen<.20
                                        and (not target.clicked or not any(other is not target and other.born>target.born+.10
                                                    and other.ring is not None and len(other.history)>=3 for other in self.live_tracks))
                                        and foreground_is_roblox()
                                        and not any(binding_down(binding) for binding in self.hotkeys))
                            def on_sent(details,target=t,sid=session):
                                target.clicked=True
                                self.deliveries.put((sid,details))
                                self.metrics.put(('sent',1))
                                self.events.put(f"Mouse delivered at {details['cursor']} • timer error {details['lateness_ms']:+.1f} ms")
                            if not self.mouse.schedule_click(x,y,planned,count=None,guard=burst_allowed,on_sent=on_sent,
                                                             tolerance=max(8,round(t.radius/detection_scale*.35))):
                                t.scheduled=True
                                self.events.put('Timed click skipped: target changed or there was insufficient smooth travel time.')
                                continue
                            t.scheduled=True
                            last_click=planned
                            log.write(json.dumps({'time':time.time(),'event':'click_scheduled','click':[x,y],'planned':planned,'remaining_ms':remaining*1000,'lead_ms':tuner.lead_ms})+'\n')
                            self.events.put(f'Click scheduled → ({x}, {y}) • contact in {remaining*1000:.0f} ms')
                    feedback=self.config.get('feedback')
                    automatic=self.config.get('auto_feedback',True)
                    if self.running.is_set() and (automatic or feedback) and now-last_ocr>.10 and (pending or not automatic):
                        if automatic:
                            search=feedback_search_rect(region,roblox_client_region())
                            if not search:
                                continue
                            feedback_image=np.asarray(sct.grab(search))[:,:,:3].copy()
                            if not pending['fallback']:
                                pending['fallback']=True
                                self.events.put('Checking game feedback automatically')
                                self.metrics.put(('feedback_status','Automatic feedback: checking result'))
                        else:
                            feedback_image=np.asarray(sct.grab(feedback))[:,:,:3].copy()
                        self.latest(self.ocr_frames,(session,now,feedback_image,automatic))
                        last_ocr=now
                    if now-last_preview>.05:
                        for t in tracks:
                            cv2.circle(frame,(round(t.x/detection_scale),round(t.y/detection_scale)),round(t.radius/detection_scale),(0,255,0),2)
                            if t.ring:
                                cv2.circle(frame,(round(t.x/detection_scale),round(t.y/detection_scale)),round(t.ring/detection_scale),(255,0,255),2)
                        self.latest(self.frames,frame)
                        self.metrics.put(('scan',(len(tracks),1/max(.001,frame_interval))))
                        self.metrics.put(('color',(detector.color_status,detector.color_hex)))
                        last_preview=now
                    self.closed.wait(.002 if self.running.is_set() else .045)
        except Exception as exc:
            self.capture_error=str(exc)
            self.pause()
            self.events.put(f'ERROR — capture stopped: {exc}. Restart the app after correcting the problem.')
            try:
                with (BASE/'LOGS.jsonl').open('a') as error_log:
                    error_log.write(json.dumps({'time':time.time(),'event':'capture_error','error':str(exc)})+'\n')
            except OSError:
                pass

    def toggle(self):
        if self.capture_error:
            self.status.set('ERROR: '+self.capture_error+'. Restart the macro after correcting this.')
            return
        if self.running.is_set():
            self.pause()
            self.status.set('Input PAUSED. Live tracking continues. Focus Roblox and press the start key to resume.')
            return
        if not self.config.get('game'):
            self.status.set('Select game or Use full screen first.')
            return
        if self.training=='Ren/Ten' and not self.config.get('auto_feedback',True) and not self.config.get('feedback'):
            self.status.set('Select feedback manually or enable Automatic feedback.')
            return
        if (self.training=='Ren/Ten' and not self.ocr_ready) or (self.training=='En' and not self.en_ready):
            self.status.set('Wait for feedback OCR to load before enabling clicks.')
            return
        if not foreground_is_roblox():
            self.status.set(f"Focus the Roblox game, then press {self.config['start_key']}.")
            return
        self.session+=1
        self.running.set()
        self.mouse.set_enabled(True)
        self.events.put(f'Started {self.training}: '+('LETTER KEY CONTROL' if self.training=='En' else 'HOLD / RELEASE CONTROL' if self.training=='Shu' else 'LIVE CLICKS — target-aware click retries'))
        with (BASE/'LOGS.jsonl').open('a') as log:
            log.write(json.dumps({'time':time.time(),'event':'started','training':self.training})+'\n')
        # Keep the panel out of the captured playfield while input is active.
        self.root.iconify()
        self.status.set(f"Running {self.training} — {self.config['pause_key']} pauses")

    def pump(self):
        if self.root.state()=='normal':
            self.panel_bounds=(self.root.winfo_rootx()-8,self.root.winfo_rooty()-32,self.root.winfo_width()+16,self.root.winfo_height()+40)
        else:
            self.panel_bounds=None
        for index,key in enumerate(self.hotkeys):
            down=binding_down(key)
            if not self.recording and not self.keyboard.suppresses(key) and down and not self.keys.get(key,False):
                if index==0:
                    self.toggle()
                else:
                    self.pause()
                    self.status.set(f"Clicks PAUSED — press {self.config['start_key']} in Roblox to resume")
            self.keys[key]=down
        try:
            frame=self.frames.get_nowait()
            image=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
            width=max(100,self.preview.winfo_width())
            height=max(100,self.preview.winfo_height())
            image.thumbnail((width,height))
            self.photo=ImageTk.PhotoImage(image)
            self.preview.delete('all')
            self.preview.create_image(width/2,height/2,image=self.photo)
        except queue.Empty:
            pass
        while True:
            try:
                kind,value=self.metrics.get_nowait()
            except queue.Empty:
                break
            if kind=='capture_status':
                self.capture_info.set(value)
            elif kind=='en':
                if self.training!='En':continue
                self.stat_labels[0].configure(text=str(value['count']))
                result=value['result']
                self.stat_labels[1].configure(text='—' if result is None else result if result=='MISS' else f'{result:+.2f}')
                self.stat_labels[2].configure(text=value['key'] or ('Reading' if value['tracked'] else 'Waiting'))
                self.scan_info.set(f"En {'reading' if value['tracked'] else 'searching'}  •  {value['fps']:.0f} fps")
                self.color_info.set('Prompt tracked' if value['tracked'] else 'Waiting for En prompt')
            elif kind=='shu':
                if self.training!='Shu':continue
                self.stat_labels[0].configure(text='—' if value['focus'] is None else f"{value['focus']*100:.0f}%")
                self.stat_labels[1].configure(text=str(value['cycles']))
                self.stat_labels[2].configure(text=value['action'])
                self.scan_info.set(f"Shu {'tracking' if value['tracked'] else 'searching'}  •  {value['fps']:.0f} fps")
                self.color_info.set('Indicator tracked' if value['tracked'] else 'Waiting for Shu bar')
                self.color_label.configure(fg='#63e5bf' if value['tracked'] else '#98a7bc')
            elif self.training in ('Shu','En'):
                continue
            elif kind=='feedback_status':
                self.feedback_info.set(value)
            elif kind=='color':
                text,color=value
                self.color_info.set(text)
                self.color_label.configure(fg=color)
            elif kind=='scan':
                count,fps=value
                self.scan_info.set(f'Scanning  •  {count} target'+('s' if count!=1 else '')+f'  •  {fps:.0f} fps')
            elif kind=='sent':
                self.sent_count+=value
                self.stat_labels[0].configure(text=str(self.sent_count))
            else:
                text=value if value=='MISS' else f'{value:+.2f}'
                self.stat_labels[1].configure(text=text,fg='#ffaf8a' if value=='MISS' or value<.04 else '#63e5bf')
                self.feedback_info.set(('Automatic feedback: ' if self.config.get('auto_feedback',True) else 'Manual feedback: ')+text)
        active=self.running.is_set()
        mode_name=self.training
        self.badge.configure(text=f'  {mode_name} / '+('RUNNING  ' if active else 'PAUSED  '),fg='#63e5bf' if active else '#98a7bc')
        if self.capture_error:
            self.badge.configure(text='  ERROR / INPUT STOPPED  ',fg='#ffaf8a')
            self.status.set('ERROR: '+self.capture_error+'. Restart the macro after correcting this.')
            self.scan_info.set('Stopped — see Activity')
        if not active and self.status.get().startswith('Running'):
            self.status.set('Input PAUSED. Live tracking continues. Focus Roblox and press the start key to resume.')
        while True:
            try:
                event=self.events.get_nowait()
            except queue.Empty:
                break
            self.log.configure(state='normal')
            self.log.insert('end',time.strftime('%H:%M:%S ')+event+'\n')
            self.log.see('end')
            self.log.configure(state='disabled')
        self.root.after(20,self.pump)

    def close(self):
        self.pause()
        self.closed.set()
        self.window_capture.close()
        self.root.destroy()


if __name__=='__main__':
    def uncaught_error(error_type,value,tb):
        try:
            write_local_log({'time':time.time(),'event':'uncaught_error','error':str(value),
                             'traceback':''.join(traceback.format_exception(error_type,value,tb))})
        finally:
            sys.__excepthook__(error_type,value,tb)
    sys.excepthook=uncaught_error
    threading.excepthook=lambda args:uncaught_error(args.exc_type,args.exc_value,args.exc_traceback)
    # Keep the lock handle alive for the entire UI lifetime. Windows releases
    # it automatically on exit, including after a crash.
    import msvcrt
    instance_lock=(BASE/'instance.lock').open('a+b')
    instance_lock.seek(0,2)
    if instance_lock.tell()==0:
        instance_lock.write(b'0')
        instance_lock.flush()
    instance_lock.seek(0)
    try:
        msvcrt.locking(instance_lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        messagebox.showinfo('Beyond Nen','The macro is already open. Use the existing panel instead of starting another copy.')
        sys.exit(0)
    app=App()
    app.root.mainloop()
