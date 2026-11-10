"""Apply updates before importing the app; prepare dependencies on first run."""
from pathlib import Path
import hashlib
import json
import msvcrt
import subprocess
import sys
import updater

BASE=Path(__file__).resolve().parent

def main():
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
        required=hashlib.sha256((BASE/'requirements.txt').read_bytes()).hexdigest()
        marker=BASE/'.dependencies.sha256'
        if not marker.exists() or marker.read_text()!=required:
            code="import sys; sys.path.insert(0,sys.argv[1]); import cv2,mss,rapidocr_onnxruntime"
            installed=subprocess.run([sys.executable,'-c',code,str(BASE/'packages')],capture_output=True).returncode==0
            if not installed or marker.exists():
                print('Installing macro dependencies. The first setup may take a few minutes.')
                result=subprocess.run([sys.executable,'-m','pip','install','--upgrade','--target',str(BASE/'packages'),'-r',str(BASE/'requirements.txt')])
                if result.returncode:
                    print('Dependency setup failed. Check your connection and Python installation.')
                    return result.returncode
            marker.write_text(required)
        msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
    return subprocess.run([sys.executable,str(BASE/'macro.py')],cwd=BASE).returncode

if __name__=='__main__':
    raise SystemExit(main())
