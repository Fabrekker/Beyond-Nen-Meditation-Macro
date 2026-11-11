"""Build a clean native-launcher preview from an explicit app-file allowlist."""
from pathlib import Path
import argparse,subprocess,shutil,os,sys,json,ast,base64,struct,hashlib
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
from updater import FILES

def build(destination,local_runtime=False):
    destination=Path(destination).resolve()
    destination.mkdir(parents=True,exist_ok=True)
    app=destination/'App';app.mkdir(exist_ok=True)
    if not local_runtime:
        private=['local-python.txt','config.json','LOGS.jsonl','packages','.test-output']
        if any((app/name).exists() for name in private):raise RuntimeError('Use a clean output folder for distributable builds; this folder contains private preview data')
    # Legacy update-source files are not user-facing desktop entry points.
    for name in sorted(FILES-{'Start Macro.cmd','Update Macro.cmd','README.md'}):
        shutil.copyfile(BASE/name,app/name)
    shutil.copyfile(BASE/'README.md',destination/'README.md')
    compiler=Path(os.environ.get('SystemRoot','C:/Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if not compiler.exists():raise RuntimeError('The build machine needs the .NET Framework C# compiler')
    tree=ast.parse((BASE/'macro.py').read_text(encoding='utf-8'))
    encoded=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='APP_ICON_PNG_BASE64' for target in node.targets))
    png=base64.b64decode(encoded,validate=True);width,height=struct.unpack('>II',png[16:24])
    icon=app/'app.ico'
    icon.write_bytes(struct.pack('<HHH',0,1,1)+struct.pack('<BBBBHHII',width%256,height%256,0,0,1,32,len(png),22)+png)
    for name,extra in [('Start Macro.exe',[]),('Update Macro.exe',['/define:UPDATE_LAUNCHER'])]:
        staged=destination/(name+'.building')
        command=[str(compiler),'/nologo','/target:winexe','/platform:x64','/optimize+','/debug-',
                 '/reference:System.Windows.Forms.dll','/win32icon:'+str(icon),
                 '/win32manifest:'+str(BASE/'native/launcher.manifest'),'/out:'+str(staged)]
        subprocess.run(command+extra+[str(BASE/'native/Launcher.cs')],check=True)
        staged.replace(destination/name)
    (app/'desktop-layout.json').write_text(json.dumps({'native_launchers':True,'version':1,'launcher_version':json.loads((BASE/'version.json').read_text())['version']}),encoding='utf-8')
    if local_runtime:
        # Private preview only. Neither this file nor the runtime junction is distributable.
        (app/'local-python.txt').write_text(sys.executable,encoding='utf-8')
        packages=app/'packages'
        if not packages.exists():
            command='$data=[Console]::In.ReadToEnd() | ConvertFrom-Json; New-Item -ItemType Junction -Path $data.path -Target $data.target | Out-Null'
            subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],input=json.dumps({'path':str(packages),'target':str(BASE/'packages')},ensure_ascii=True),text=True,capture_output=True,check=True)
        for name in ['config.json','update-settings.json']:
            if (BASE/name).exists():shutil.copyfile(BASE/name,app/name)
        code="import sys;sys.path.insert(0,sys.argv[1]);import cv2,mss,windows_capture,onnxruntime;from PIL import ImageTk;from rapidocr_onnxruntime import RapidOCR"
        probe=subprocess.run([sys.executable,'-I','-c',code,str(packages)],capture_output=True)
        if probe.returncode==0:(app/'.dependencies.sha256').write_text(hashlib.sha256((app/'requirements.txt').read_bytes()).hexdigest())
    assert not list(destination.glob('*.cmd')) and not list(app.glob('*.cmd'))
    print('Built a clean local desktop folder: native Start/Update launchers, App, and README.')
    return destination

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--local-runtime',action='store_true')
    args=parser.parse_args();build(args.output,args.local_runtime)
