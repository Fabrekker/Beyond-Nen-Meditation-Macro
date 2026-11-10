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
import tkinter as tk
from tkinter import messagebox, ttk
import cv2
import mss
import numpy as np
from PIL import Image, ImageTk
from vision import Detector, Tuner, parse_feedback
from wininput import MouseInput

USER = ctypes.windll.user32
USER.GetForegroundWindow.restype = wintypes.HWND
USER.GetAsyncKeyState.argtypes = [ctypes.c_int]
USER.GetAsyncKeyState.restype = ctypes.c_short
USER.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    USER.SetProcessDPIAware()


def foreground_is_roblox():
    hwnd = USER.GetForegroundWindow()
    title = ctypes.create_unicode_buffer(512)
    USER.GetWindowTextW(hwnd,title,512)
    return 'roblox' in title.value.lower()


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Beyond Nen | Circle Assistant')
        self.root.geometry('790x830')
        self.root.minsize(710,800)
        self.running = threading.Event()
        self.closed = threading.Event()
        self.preview_only = False
        self.frames = queue.Queue(maxsize=1)
        self.ocr_frames = queue.Queue(maxsize=1)
        self.results = queue.Queue()
        self.deliveries = queue.Queue()
        self.events = queue.Queue()
        self.ocr_ready = False
        self.config = {'game':None,'feedback':None,'lead_ms':12.,'click_hold_ms':35.}
        if (BASE/'config.json').exists():
            self.config.update(json.loads((BASE/'config.json').read_text()))
        self.mouse=MouseInput(self.config['click_hold_ms'])
        self.status = tk.StringVar(value='Paused. Select game area and feedback area, then press F1 in Roblox.')
        self.mode = tk.BooleanVar(value=False)
        self.keys = {key:bool(USER.GetAsyncKeyState(key)&0x8000) for key in (0x70,0x71)}
        self.session = 0
        self.sent_count=0
        self.latest_feedback='—'
        self.metrics=queue.Queue()
        self.scan_info=tk.StringVar(value='Waiting for a capture area')
        self.color_info=tk.StringVar(value='Checking colors…')
        self.panel_bounds=None
        self.build_ui()
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        threading.Thread(target=self.capture_loop,daemon=True).start()
        threading.Thread(target=self.ocr_loop,daemon=True).start()
        self.root.after(30,self.pump)

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
        tk.Label(outer,text='Circle Assistant  /  Automatic timing & click bursts',font=('Segoe UI',10),fg=muted,bg=bg).pack(anchor='w',pady=(2,18))
        setup=tk.Frame(outer,bg=card,padx=16,pady=14)
        setup.pack(fill='x')
        tk.Label(setup,text='CAPTURE AREAS',font=('Segoe UI',9,'bold'),fg=muted,bg=card).pack(anchor='w')
        row=tk.Frame(setup,bg=card)
        row.pack(fill='x',pady=(10,7))
        ttk.Button(row,text='Select game',command=lambda:self.select('game')).pack(side='left',padx=(0,8))
        ttk.Button(row,text='Select feedback',command=lambda:self.select('feedback')).pack(side='left')
        ttk.Checkbutton(row,text='Preview mode',variable=self.mode,command=self.set_mode).pack(side='right')
        self.area_label=tk.Label(setup,text='',font=('Segoe UI',9),fg=muted,bg=card,anchor='w')
        self.area_label.pack(fill='x')
        self.update_area_label()
        stats=tk.Frame(outer,bg=bg)
        stats.pack(fill='x',pady=12)
        self.stat_labels=[]
        for index,(title,value) in enumerate((('TARGETS CLICKED','0'),('LAST RESULT','—'),('CLICK PATTERN','3 × automatic'))):
            stats.columnconfigure(index,weight=1,uniform='stat')
            box=tk.Frame(stats,bg=card,padx=14,pady=10)
            box.grid(row=0,column=index,sticky='ew',padx=(0,8) if index<2 else 0)
            tk.Label(box,text=title,font=('Segoe UI',8,'bold'),fg=muted,bg=card).pack(anchor='w')
            label=tk.Label(box,text=value,font=('Segoe UI',15,'bold'),fg=accent,bg=card)
            label.pack(anchor='w',pady=(3,0))
            self.stat_labels.append(label)
        live=tk.Frame(outer,bg=card,padx=12,pady=10)
        live.pack(fill='both',expand=True)
        live_header=tk.Frame(live,bg=card)
        live_header.pack(fill='x',pady=(0,8))
        tk.Label(live_header,text='LIVE TRACKING',font=('Segoe UI',9,'bold'),fg=muted,bg=card).pack(side='left')
        tk.Label(live_header,textvariable=self.scan_info,font=('Segoe UI',9),fg=accent,bg=card).pack(side='right')
        self.preview=tk.Canvas(live,bg='#0c1119',height=200,highlightthickness=0)
        self.preview.pack(fill='both',expand=True)
        self.preview.create_text(350,110,text='Your game preview will appear here',fill=muted,font=('Segoe UI',12),tags='placeholder')
        self.preview.bind('<Configure>',lambda e:self.preview.coords('placeholder',e.width/2,e.height/2))
        legend=tk.Frame(live,bg=card)
        legend.pack(fill='x',pady=(7,0))
        tk.Label(legend,text='Green: target    •    Magenta: shrinking ring',font=('Segoe UI',9),fg=muted,bg=card).pack(side='left')
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
        tk.Label(footer,text='F1  Start / pause     F2  Stop',font=('Segoe UI',10,'bold'),fg=accent,bg=bg).pack(side='left')
        ttk.Button(footer,text='Pause',command=self.stop_button).pack(side='right')

    def update_area_label(self):
        parts=[]
        for key in ('game','feedback'):
            region=self.config.get(key)
            parts.append(f'{key.capitalize()}: '+(f"{region['width']} × {region['height']} saved" if region else 'not selected'))
        self.area_label.configure(text='     •     '.join(parts))

    def stop_button(self):
        self.pause()
        self.status.set('Clicks paused; preview stays live. Focus Roblox and press F1 to resume.')

    def save(self):
        (BASE/'config.json').write_text(json.dumps(self.config,indent=2))

    def pause(self):
        self.running.clear()
        self.session += 1
        try:
            self.mouse.set_enabled(False)
        except OSError as exc:
            self.events.put(f'Mouse release failed: {exc}')

    def set_mode(self):
        self.pause()
        self.preview_only = self.mode.get()
        name='PREVIEW MODE' if self.preview_only else 'LIVE CLICKS'
        self.status.set(f'{name} selected · PAUSED. Focus Roblox and press F1 to start.')
        self.events.put(f'Mode selected: {name}. F1 in Roblox starts; changing mode pauses.')

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
                self.save()
                self.update_area_label()
                self.status.set(f'{key.capitalize()} area saved. F1 starts with Roblox focused.')
        except Exception as exc:
            messagebox.showerror('Selection failed',str(exc))
        finally:
            self.root.deiconify()

    def ocr_loop(self):
        try:
            from rapidocr_onnxruntime import RapidOCR
            engine=RapidOCR(intra_op_num_threads=1,inter_op_num_threads=1)
            self.ocr_ready=True
            self.events.put('Feedback OCR ready')
        except Exception as exc:
            self.events.put(f'OCR failed; click mode unavailable: {exc}')
            return
        while not self.closed.is_set():
            try:
                session,stamp,image=self.ocr_frames.get(timeout=.2)
            except queue.Empty:
                continue
            try:
                # Upscaling makes the small game font readable without slowing the tracking thread.
                scale=max(2., min(4.,80/image.shape[0]))
                enlarged=cv2.resize(image,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
                result,_=engine(enlarged)
                items=[(r[1],float(r[2])) for r in (result or [])]
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
        try:
            with mss.mss() as sct, (BASE/'events.jsonl').open('a',buffering=1) as log:
                while not self.closed.is_set():
                    if not self.config.get('game'):
                        self.closed.wait(.025)
                        continue
                    if self.running.is_set() and not foreground_is_roblox():
                        self.pause()
                        self.events.put('Clicks paused: Roblox lost focus. Preview stays live. Focus Roblox and press F1 to resume.')
                    session=self.session
                    if self.mouse.error:
                        raise self.mouse.error
                    if session!=previous_session:
                        detector=Detector()
                        pending=None
                        feedback_last=None
                        feedback_count=0
                        previous_session=session
                        last_stamp=time.perf_counter()
                        frame_interval=.016
                    region=self.config['game']
                    start=time.perf_counter()
                    frame=np.asarray(sct.grab(region))[:,:,:3].copy()
                    # When inspecting the panel, do not detect circles inside
                    # its own scaled preview. Bounds are cached by the UI thread.
                    bounds=self.panel_bounds
                    if bounds and not foreground_is_roblox():
                        px,py,pw,ph=bounds
                        x0=max(0,px-region['left']); y0=max(0,py-region['top'])
                        x1=min(frame.shape[1],px+pw-region['left']); y1=min(frame.shape[0],py+ph-region['top'])
                        if x1>x0 and y1>y0:
                            frame[y0:y1,x0:x1]=0
                    stamp=(start+time.perf_counter())/2
                    frame_interval=.85*frame_interval+.15*min(.1,stamp-last_stamp)
                    last_stamp=stamp
                    tracks=detector.update(frame,stamp)
                    if detector.color_status!=last_color_status:
                        self.events.put(detector.color_status)
                        last_color_status=detector.color_status
                    now=time.perf_counter()
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
                        if pending and pending['time']+.06 < ts < pending['time']+2.3 and (feedback_count>=2 or confident) and pending['armed']:
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
                        elif not pending and value=='MISS' and feedback_count==2 and not self.preview_only:
                            msg=tuner.feedback(value)
                            self.config['lead_ms']=tuner.lead_ms
                            self.save()
                            log.write(json.dumps({'time':time.time(),'feedback':value,'unmatched_click':True,'lead_ms':tuner.lead_ms})+'\n')
                            self.events.put(f'MISS without a matching click: {msg}')
                            self.metrics.put(('feedback',value))
                    if pending and now-pending['time']>2.5:
                        self.events.put('No confirmed feedback for last click; timing unchanged')
                        pending=None
                    for t in tracks:
                        if not self.running.is_set():
                            break
                        now=time.perf_counter()
                        remaining=t.remaining(now)
                        if remaining is None or t.clicked or getattr(t,'scheduled',False) or now-last_click<.35:
                            continue
                        # Reserve the target well before contact. The mouse
                        # timer, not the next screen frame, dispatches input.
                        if now-t.seen>.14 or remaining>.18:
                            continue
                        if remaining<0:
                            t.scheduled=True
                            self.events.put('Target acquired too late for a timed click; no input sent')
                            log.write(json.dumps({'time':time.time(),'event':'late_target','remaining_ms':remaining*1000})+'\n')
                            continue
                        x=round(region['left']+t.x)
                        y=round(region['top']+t.y)
                        if self.preview_only:
                            t.clicked=True
                            last_click=now
                            self.events.put(f'Preview: would click ({x}, {y}); predicted match in {remaining*1000:.1f} ms')
                        elif self.running.is_set() and session==self.session and foreground_is_roblox():
                            # Check stop key immediately before sending mouse input, independently of the UI timer.
                            if USER.GetAsyncKeyState(0x70)&0x8000 or USER.GetAsyncKeyState(0x71)&0x8000:
                                for key in (0x70,0x71):
                                    if USER.GetAsyncKeyState(key)&0x8000:
                                        self.keys[key]=True
                                self.pause()
                                self.events.put('Paused by stop key')
                                break
                            planned=max(now+.026,now+remaining-tuner.lead_ms/1000)
                            def burst_allowed(sid=session,deadline=planned+.22):
                                return (self.running.is_set() and not self.closed.is_set()
                                        and self.session==sid and time.perf_counter()<deadline
                                        and foreground_is_roblox()
                                        and not USER.GetAsyncKeyState(0x70)&0x8000
                                        and not USER.GetAsyncKeyState(0x71)&0x8000)
                            def on_sent(details,target=t,sid=session):
                                target.clicked=True
                                self.deliveries.put((sid,details))
                                self.metrics.put(('sent',1))
                                self.events.put(f"Mouse delivered at {details['cursor']} • timer error {details['lateness_ms']:+.1f} ms")
                            if not self.mouse.schedule_click(x,y,planned,count=3,guard=burst_allowed,on_sent=on_sent,
                                                             tolerance=max(8,round(t.radius*.35))):
                                self.events.put('Click cancelled: focus or stop state changed')
                                continue
                            t.scheduled=True
                            last_click=planned
                            log.write(json.dumps({'time':time.time(),'event':'click_scheduled','click':[x,y],'planned':planned,'remaining_ms':remaining*1000,'lead_ms':tuner.lead_ms})+'\n')
                            self.events.put(f'Click scheduled → ({x}, {y}) • contact in {remaining*1000:.0f} ms')
                    feedback=self.config.get('feedback')
                    if self.running.is_set() and feedback and now-last_ocr>.10:
                        if pending and now-pending['time']>.25:
                            # A slightly misplaced manual region must not
                            # disable all feedback-driven timing adjustments.
                            h,w=frame.shape[:2]
                            feedback_image=frame[int(h*.25):int(h*.85),int(w*.65):].copy()
                            if not pending['fallback']:
                                pending['fallback']=True
                                self.events.put('Checking right-side feedback automatically')
                        else:
                            feedback_image=np.asarray(sct.grab(feedback))[:,:,:3].copy()
                        self.latest(self.ocr_frames,(session,now,feedback_image))
                        last_ocr=now
                    if now-last_preview>.10:
                        for t in tracks:
                            cv2.circle(frame,(round(t.x),round(t.y)),round(t.radius),(0,255,0),2)
                            if t.ring:
                                cv2.circle(frame,(round(t.x),round(t.y)),round(t.ring),(255,0,255),2)
                        self.latest(self.frames,frame)
                        self.metrics.put(('scan',(len(tracks),1/max(.001,frame_interval))))
                        self.metrics.put(('color',(detector.color_status,detector.color_hex)))
                        last_preview=now
                    self.closed.wait(.002 if self.running.is_set() else .045)
        except Exception as exc:
            self.pause()
            self.events.put(f'Capture stopped: {exc}. Restart the app after correcting the problem.')

    def toggle(self):
        if self.running.is_set():
            self.pause()
            self.status.set('Clicks paused; preview stays live. Focus Roblox and press F1 to resume.')
            return
        # Synchronize directly with the visible checkbox at every start.
        self.preview_only=bool(self.mode.get())
        if not self.config.get('game') or not self.config.get('feedback'):
            self.status.set('Select both the game area and the feedback area first.')
            return
        if not self.preview_only and not self.ocr_ready:
            self.status.set('Wait for feedback OCR to load before enabling clicks.')
            return
        if not foreground_is_roblox():
            self.status.set('Focus the Roblox game, then press F1.')
            return
        self.session+=1
        self.running.set()
        self.mouse.set_enabled(not self.preview_only)
        self.events.put('Started: '+('PREVIEW MODE — mouse disabled' if self.preview_only else 'LIVE CLICKS — automatic 3-click bursts'))
        with (BASE/'events.jsonl').open('a') as log:
            log.write(json.dumps({'time':time.time(),'event':'started','preview_only':self.preview_only})+'\n')
        # Keep the panel out of the captured playfield while input is active.
        self.root.iconify()
        self.status.set('Running — '+('PREVIEW ONLY' if self.preview_only else 'CLICKS ENABLED')+' — F1 / F2 pauses')

    def pump(self):
        if self.root.state()=='normal':
            self.panel_bounds=(self.root.winfo_rootx()-8,self.root.winfo_rooty()-32,self.root.winfo_width()+16,self.root.winfo_height()+40)
        else:
            self.panel_bounds=None
        for key in (0x70,0x71):
            down=bool(USER.GetAsyncKeyState(key)&0x8000)
            if down and not self.keys.get(key,False):
                if key==0x70:
                    self.toggle()
                else:
                    self.pause()
                    self.status.set('Emergency pause — press F1 to resume')
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
            if kind=='color':
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
        active=self.running.is_set()
        mode_name='PREVIEW MODE' if self.preview_only else 'LIVE CLICKS'
        self.badge.configure(text=f'  {mode_name} / '+('RUNNING  ' if active else 'PAUSED  '),fg='#63e5bf' if active else '#98a7bc')
        if not active and self.status.get().startswith('Running'):
            self.status.set('Clicks paused; preview stays live. Focus Roblox and press F1 to resume.')
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
        self.root.destroy()


if __name__=='__main__':
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
