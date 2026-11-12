"""HTTPS release downloads; strict source-file allowlist; settings preserved."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
import zipfile
import io
import time

BASE=Path(__file__).resolve().parent
FILES={'macro.py','vision.py','wininput.py','updater.py','bootstrap.py','version.json',
       'requirements.txt','Start Macro.cmd','Update Macro.cmd','README.md'}
MAX_DOWNLOAD=5*1024*1024
DESKTOP_FILES={'Start Macro.exe','Update Macro.exe','README.md','App/app.ico','App/desktop-layout.json'}|{'App/'+name for name in FILES-{'Start Macro.cmd','Update Macro.cmd','README.md'}}

def version(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d+\.\d+\.\d+',value):
        raise ValueError('Version must use three numbers, for example 1.0.1')
    return tuple(map(int,value.split('.')))

def display_version(value):
    major,minor,patch=version(value)
    return f'{major}.{minor}' if patch==0 else value


def https_url(url):
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Update URLs must use HTTPS without embedded credentials')
    return url

def download(url,limit):
    request=urllib.request.Request(https_url(url),headers={'User-Agent':'BeyondNenUpdater/1.0'})
    with urllib.request.urlopen(request,timeout=20) as response:
        https_url(response.url)
        data=response.read(limit+1)
    if len(data)>limit:
        raise ValueError('Update download is larger than allowed')
    return data

def current(base=BASE):
    return json.loads((Path(base)/'version.json').read_text())['version']

def read_manifest(base=BASE):
    base=Path(base)
    settings=json.loads((base/'update-settings.json').read_text())
    if not settings.get('manifest_url'):
        return None
    manifest=json.loads(download(settings['manifest_url'],64000))
    version(manifest['version'])
    https_url(manifest['download_url'])
    if not re.fullmatch(r'[a-fA-F0-9]{64}',manifest['sha256']):
        raise ValueError('Release manifest has no valid SHA-256 checksum')
    return manifest

def check(base=BASE):
    manifest=read_manifest(base)
    return manifest if manifest and version(manifest['version'])>version(current(base)) else None

def ensure_desktop(base=BASE):
    """Refresh only managed launchers from the checksum-verified desktop package."""
    base=Path(base).resolve()
    marker=base/'desktop-layout.json'
    root=base.parent if base.name=='App' and (base.parent/'Start Macro.exe').exists() else base
    installed=current(base)
    if marker.exists():
        state=json.loads(marker.read_text())
        if state.get('launcher_version')==installed and all((root/n).is_file() for n in ('Start Macro.exe','Update Macro.exe')) and (base/'app.ico').is_file():
            return
    manifest=read_manifest(base)
    if not manifest or manifest['version']!=installed or 'desktop_download_url' not in manifest:return
    checksum=manifest.get('desktop_sha256','')
    if not re.fullmatch(r'[a-fA-F0-9]{64}',checksum):raise ValueError('Desktop checksum is invalid')
    data=download(https_url(manifest['desktop_download_url']),MAX_DOWNLOAD)
    if hashlib.sha256(data).hexdigest().lower()!=checksum.lower():raise ValueError('Desktop checksum mismatch')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)) or set(names)!=DESKTOP_FILES:raise ValueError('Unexpected desktop package files')
        if sum(i.file_size for i in archive.infolist())>20*1024*1024:raise ValueError('Expanded desktop package is too large')
        for info in archive.infolist():
            if info.is_dir() or (info.external_attr>>16)&0o170000==0o120000:raise ValueError('Invalid desktop package entry')
        state=json.loads(archive.read('App/desktop-layout.json'))
        if state.get('launcher_version')!=installed or json.loads(archive.read('App/version.json'))['version']!=installed:raise ValueError('Desktop version mismatch')
        # Stage all resources before replacing any; a failed replacement is retried next start.
        staged=[]
        try:
            for source,target in [('Start Macro.exe',root/'Start Macro.exe'),('Update Macro.exe',root/'Update Macro.exe'),('App/app.ico',base/'app.ico'),('App/desktop-layout.json',marker)]:
                temporary=target.with_name(target.name+'.new')
                temporary.write_bytes(archive.read(source));staged.append((temporary,target))
            for temporary,target in staged:
                for attempt in range(20):
                    try:temporary.replace(target);break
                    except PermissionError:
                        if attempt==19:raise
                        time.sleep(.1)
        finally:
            for temporary,_ in staged:temporary.unlink(missing_ok=True)

def validate_archive(path,expected_version):
    with zipfile.ZipFile(path) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)) or set(names)!=FILES:
            raise ValueError('Update must contain exactly the approved application files')
        if sum(i.file_size for i in archive.infolist())>20*1024*1024:
            raise ValueError('Expanded update is too large')
        packaged=json.loads(archive.read('version.json'))['version']
        if packaged!=expected_version:
            raise ValueError('Package version does not match its manifest')
        for info in archive.infolist():
            if info.is_dir() or (info.external_attr>>16)&0o170000==0o120000:
                raise ValueError('Directories and symbolic links are not allowed in updates')

def stage(manifest,base=BASE):
    base=Path(base)
    data=download(manifest['download_url'],MAX_DOWNLOAD)
    if hashlib.sha256(data).hexdigest().lower()!=manifest['sha256'].lower():
        raise ValueError('Update checksum mismatch; download was not installed')
    folder=base/'.updates'
    folder.mkdir(exist_ok=True)
    temporary=folder/'download.tmp'
    temporary.write_bytes(data)
    try:
        validate_archive(temporary,manifest['version'])
        temporary.replace(folder/'pending.zip')
        (folder/'pending.json').write_text(json.dumps(manifest))
    finally:
        temporary.unlink(missing_ok=True)

def apply_pending(base=BASE):
    base=Path(base)
    folder=base/'.updates'
    pending=folder/'pending.zip'
    if not pending.exists():
        return False
    manifest=json.loads((folder/'pending.json').read_text())
    if version(manifest['version'])<=version(current(base)):
        pending.unlink()
        (folder/'pending.json').unlink()
        return False
    if hashlib.sha256(pending.read_bytes()).hexdigest().lower()!=manifest['sha256'].lower():
        raise ValueError('Staged update checksum mismatch')
    validate_archive(pending,manifest['version'])
    # Only the source allowlist is replaced. config.json, logs, update server
    # settings and installed dependencies are never extracted from a release.
    work=Path(tempfile.mkdtemp(prefix='apply-',dir=folder))
    backup=work/'backup'
    backup.mkdir()
    replaced=[]
    try:
        with zipfile.ZipFile(pending) as archive:
            for name in sorted(FILES-{'version.json'})+['version.json']:
                target=base/name
                if target.exists(): shutil.copy2(target,backup/name)
                new=work/name
                new.write_bytes(archive.read(name))
                new.replace(target)
                replaced.append(name)
    except Exception:
        for name in reversed(replaced):
            if (backup/name).exists(): shutil.copy2(backup/name,base/name)
            else: (base/name).unlink(missing_ok=True)
        raise
    pending.unlink()
    (folder/'pending.json').unlink()
    return True
