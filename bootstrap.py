"""Apply updates before importing the app; prepare dependencies on first run."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import struct
import time
import traceback
import ast
import base64
import queue
import threading

BASE=Path(__file__).resolve().parent

def prepare_update_settings(base=BASE):
    """Initialize fresh installs; keep existing update preferences untouched."""
    path=Path(base)/'update-settings.json'
    if not path.exists():
        path.write_text(json.dumps({
            'manifest_url':'https://github.com/Fabrekker/Beyond-Nen-Meditation-Macro/releases/latest/download/update.json',
            'automatic':True},indent=2),encoding='utf-8')


def record_error(event,details):
    try:
        with (BASE/'LOGS.jsonl').open('a',encoding='utf-8') as log:
            log.write(json.dumps({'time':time.time(),'event':event,'error':details})+'\n')
    except OSError:
        pass


def run_logged(command,event,hidden=False):
    lines=[]
    with subprocess.Popen(command,cwd=BASE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          text=True,encoding='utf-8',errors='replace',
                          creationflags=subprocess.CREATE_NO_WINDOW if hidden and sys.platform=='win32' else 0) as process:
        for line in process.stdout:
            if sys.stdout is not None:print(line,end='',flush=True)
            lines.append(line)
            lines=lines[-80:]
        code=process.wait()
    if code:record_error(event,''.join(lines) or f'Process exited with code {code}')
    return code


def launch_bootstrap(quiet):
    python=Path(sys.executable).with_name('pythonw.exe' if quiet else 'python.exe')
    if not python.exists():python=Path(sys.executable)
    flag='--quiet-launch' if quiet else '--setup-visible'
    creation=subprocess.CREATE_NO_WINDOW if quiet else subprocess.CREATE_NEW_CONSOLE
    subprocess.Popen([str(python),str(BASE/'bootstrap.py'),flag],cwd=BASE,creationflags=creation)
    return 0


def show_startup_error():
    import ctypes
    ctypes.windll.user32.MessageBoxW(None,
        'The macro could not start. Details were saved in LOGS.jsonl in the macro folder. '
        'Check the setup instructions in the README.', 'Beyond Nen - Startup error',0x10)


def create_app_shortcuts():
    """Install managed native launchers without device-specific shortcuts."""
    import updater
    updater.ensure_desktop(BASE)
    clean_desktop_legacy_files()



def clean_desktop_legacy_files():
    """Remove only legacy launcher files managed by this desktop installation."""
    if not (BASE/'desktop-layout.json').exists():return
    if not all(any((folder/name).is_file() for folder in (BASE,BASE.parent)) for name in ('Start Macro.exe','Update Macro.exe')):return
    for name in ('Start Macro.cmd','Update Macro.cmd'):
        target=BASE/name
        if target.is_file() and target.resolve().parent==BASE.resolve():target.unlink()


def graphical_update():
    """Check and install updates with a small GUI, preserving the app lock."""
    import tkinter as tk
    from tkinter import ttk
    import msvcrt
    import updater
    import ctypes
    try:ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('BeyondNen.TrainingAssistant.Updates')
    except OSError:pass
    root=tk.Tk()
    root.title('Beyond Nen | Updates')
    root.geometry('500x260');root.resizable(False,False)
    bg='#101620';card='#1b2534';ink='#edf3fa';muted='#a4b3c8';accent='#63e5bf'
    root.configure(bg=bg)
    style=ttk.Style(root);style.theme_use('clam')
    style.configure('Update.TButton',background='#29364a',foreground=ink,padding=(14,6),borderwidth=0)
    style.configure('Update.Horizontal.TProgressbar',background=accent,troughcolor=card,borderwidth=0)
    icon=BASE/'app.ico'
    if not icon.exists():icon=BASE/'.launcher/macro.ico'
    if icon.exists():root.iconbitmap(str(icon))
    panel=tk.Frame(root,bg=bg,padx=24,pady=20);panel.pack(fill='both',expand=True)
    tk.Label(panel,text='BEYOND NEN',font=('Segoe UI',18,'bold'),fg=ink,bg=bg).pack(anchor='w')
    tk.Label(panel,text='Application updates',font=('Segoe UI',10),fg=muted,bg=bg).pack(anchor='w',pady=(2,18))
    status=tk.StringVar(value='Checking for updates...')
    status_label=tk.Label(panel,textvariable=status,font=('Segoe UI',11),fg=accent,bg=bg,wraplength=450,justify='left');status_label.pack(anchor='w')
    progress=ttk.Progressbar(panel,mode='indeterminate',style='Update.Horizontal.TProgressbar');progress.pack(fill='x',pady=(14,10));progress.start(12)
    detail=tk.StringVar(value='Your saved settings stay on this computer.')
    tk.Label(panel,textvariable=detail,font=('Segoe UI',9),fg=muted,bg=bg,wraplength=450,justify='left').pack(anchor='w')
    close=ttk.Button(panel,text='Close',command=root.destroy,state='disabled',style='Update.TButton');close.pack(anchor='e',pady=(12,0))
    events=queue.Queue();busy=[True];timer=[None]
    def worker():
        try:
            with (BASE/'instance.lock').open('a+b') as lock:
                lock.seek(0,2)
                if not lock.tell():lock.write(b'0');lock.flush()
                lock.seek(0)
                try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
                except OSError:
                    events.put(('error','Close the macro before checking for updates.','Your current installation has not been changed.'));return
                updater.apply_pending(BASE);clean_desktop_legacy_files();prepare_update_settings(BASE)
                release=updater.check(BASE)
                if release is None:
                    create_app_shortcuts()
                    events.put(('done',"You're up to date.",'Installed version: '+updater.current(BASE)));return
                events.put(('status','Downloading version '+release['version']+'...','The download will be checked before installation.'))
                updater.stage(release,BASE)
                events.put(('status','Installing update...','Please keep this window open.'))
                updater.apply_pending(BASE)
                clean_desktop_legacy_files()
                try:create_app_shortcuts()
                except Exception:record_error('shortcut_creation_failed',traceback.format_exc())
                events.put(('done','Updated to version '+updater.current(BASE)+'.','Open Start Macro to use the updated application.'))
        except Exception:
            record_error('graphical_update_failed',traceback.format_exc())
            events.put(('error','The update could not be completed.','Details are saved locally in LOGS.jsonl. You can try again later.'))
    def pump():
        try:
            while True:
                kind,message,description=events.get_nowait()
                status.set(message);detail.set(description)
                if kind in ('done','error'):
                    busy[0]=False;progress.stop();progress.pack_forget();close.state(['!disabled'])
                    status_label.configure(fg='#ffba8a' if kind=='error' else accent)
        except queue.Empty:pass
        timer[0]=root.after(60,pump)
    def on_close():
        if not busy[0]:root.destroy()
        else:detail.set('Please wait for the update check to finish.');root.bell()
    root.protocol('WM_DELETE_WINDOW',on_close)
    threading.Thread(target=worker,daemon=True).start();timer[0]=root.after(60,pump)
    try:root.mainloop()
    finally:
        if timer[0]:
            try:root.after_cancel(timer[0])
            except tk.TclError:pass
    return 0


def probe_dependencies():
    code="import sys; sys.path.insert(0,sys.argv[1]); import tkinter; import cv2,mss,numpy,onnxruntime,windows_capture; from PIL import Image,ImageTk; from rapidocr_onnxruntime import RapidOCR"
    return subprocess.run([sys.executable,'-I','-c',code,str(BASE/'packages')],capture_output=True,text=True,encoding='utf-8',errors='replace')


def main():
    if sys.platform!='win32' or sys.version_info[:2]!=(3,12) or struct.calcsize('P')!=8:
        message='Install Python 3.12 (64-bit) for Windows, including pip and Tcl/Tk.'
        print(message);record_error('python_setup_failed',message)
        return 1
    import msvcrt
    import updater
    if '--gui-update' in sys.argv:return graphical_update()
    update_only='--update-only' in sys.argv
    quiet='--quiet-launch' in sys.argv
    with (BASE/'instance.lock').open('a+b') as lock:
        lock.seek(0,2)
        if not lock.tell(): lock.write(b'0'); lock.flush()
        lock.seek(0)
        try: msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            print('The macro is already open. Close it before restarting or updating.')
            return 0
        try:
            updater.apply_pending(BASE)
            clean_desktop_legacy_files()
            prepare_update_settings(BASE)
            settings=json.loads((BASE/'update-settings.json').read_text())
            if update_only and not settings.get('manifest_url'):
                print('Update hosting is not configured yet. Set manifest_url in update-settings.json to your GitHub Releases update.json link.')
                return 1
            if update_only or settings.get('automatic',True):
                release=updater.check(BASE)
                if release:
                    if quiet:return launch_bootstrap(quiet=False)
                    print('Installing update '+release['version'])
                    updater.stage(release,BASE)
                    updater.apply_pending(BASE)
                    print('Updated to '+release['version'])
                elif update_only:
                    print('Already up to date: '+updater.current(BASE))
        except Exception as exc:
            print('Update unavailable; continuing with the installed version:',exc)
            if update_only: return 1
        if update_only:
            create_app_shortcuts()
            return 0
        # Tcl/Tk comes from the Python installer, not pip.
        tk_probe=subprocess.run([sys.executable,'-I','-c','import tkinter'],capture_output=True,text=True)
        if tk_probe.returncode:
            print('Python is missing Tcl/Tk. Modify or repair Python 3.12 and enable Tcl/Tk and IDLE.')
            record_error('tkinter_setup_failed',tk_probe.stderr)
            return 1
        required=hashlib.sha256((BASE/'requirements.txt').read_bytes()).hexdigest()
        marker=BASE/'.dependencies.sha256'
        probe=probe_dependencies()
        if not marker.exists() or marker.read_text()!=required or probe.returncode:
            if quiet:return launch_bootstrap(quiet=False)
            print('Installing macro dependencies automatically. Keep this window open; the first setup may take a few minutes.')
            pip_ok=subprocess.run([sys.executable,'-m','pip','--version'],capture_output=True).returncode==0
            if not pip_ok and run_logged([sys.executable,'-m','ensurepip','--upgrade'],'pip_setup_failed'):
                print('Python pip setup failed. Repair Python with pip enabled; see LOGS.jsonl.')
                return 1
            result=run_logged([sys.executable,'-m','pip','install','--disable-pip-version-check','--upgrade',
                               '--only-binary=:all:','--target',str(BASE/'packages'),'-r',str(BASE/'requirements.txt')],
                              'dependency_install_failed')
            if result:
                print('Dependency installation failed. Read the error above; details are saved in LOGS.jsonl.')
                return result
            probe=probe_dependencies()
            if probe.returncode:
                print(probe.stderr)
                print('Installed dependencies could not load. See LOGS.jsonl. A DLL error may require the Microsoft Visual C++ x64 runtime.')
                record_error('dependency_import_failed',probe.stderr)
                return 1
            marker.write_text(required)
        try:create_app_shortcuts()
        except Exception:
            record_error('shortcut_creation_failed',traceback.format_exc())
            if not quiet:print('Could not refresh the desktop launchers; the installed application remains available.')
        msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
    if not quiet:return launch_bootstrap(quiet=True)
    python=Path(sys.executable).with_name('python.exe')
    if not python.exists():python=Path(sys.executable)
    return run_logged([str(python),str(BASE/'macro.py')],'app_startup_failed',hidden=True)

if __name__=='__main__':
    try:
        code=main()
    except Exception:
        details=traceback.format_exc()
        print(details)
        print('Startup failed. Details are saved in LOGS.jsonl.')
        record_error('bootstrap_failed',details)
        code=1
    if code and any(flag in sys.argv for flag in ('--quiet-launch','--gui-update')):
        show_startup_error()
    elif code and '--setup-visible' in sys.argv:
        input('Press Enter to close this setup window...')
    raise SystemExit(code)
