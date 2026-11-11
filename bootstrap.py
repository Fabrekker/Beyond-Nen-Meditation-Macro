"""Apply updates before importing the app; prepare dependencies on first run."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import struct
import time
import traceback

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


def run_logged(command,event):
    lines=[]
    with subprocess.Popen(command,cwd=BASE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          text=True,encoding='utf-8',errors='replace') as process:
        for line in process.stdout:
            print(line,end='',flush=True)
            lines.append(line)
            lines=lines[-80:]
        code=process.wait()
    if code:record_error(event,''.join(lines) or f'Process exited with code {code}')
    return code


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
    update_only='--update-only' in sys.argv
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
            prepare_update_settings(BASE)
            settings=json.loads((BASE/'update-settings.json').read_text())
            if update_only and not settings.get('manifest_url'):
                print('Update hosting is not configured yet. Set manifest_url in update-settings.json to your GitHub Releases update.json link.')
                return 1
            if update_only or settings.get('automatic',True):
                release=updater.check(BASE)
                if release:
                    print('Installing update '+release['version'])
                    updater.stage(release,BASE)
                    updater.apply_pending(BASE)
                    print('Updated to '+release['version'])
                elif update_only:
                    print('Already up to date: '+updater.current(BASE))
        except Exception as exc:
            print('Update unavailable; continuing with the installed version:',exc)
            if update_only: return 1
        if update_only: return 0
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
        msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
    return run_logged([sys.executable,str(BASE/'macro.py')],'app_startup_failed')

if __name__=='__main__':
    try:
        code=main()
    except Exception:
        details=traceback.format_exc()
        print(details)
        print('Startup failed. Details are saved in LOGS.jsonl.')
        record_error('bootstrap_failed',details)
        code=1
    raise SystemExit(code)
