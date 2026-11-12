"""Owner tool: create small GitHub release assets without personal settings."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile
import tempfile
from updater import FILES,DESKTOP_FILES,version,display_version
from build_desktop import build as build_desktop

BASE=Path(__file__).resolve().parent

def add_file(archive,path,name):
    # Fixed metadata avoids publishing the source machine's file timestamps.
    entry=zipfile.ZipInfo(name,date_time=(2020,1,1,0,0,0))
    entry.compress_type=zipfile.ZIP_DEFLATED
    entry.external_attr=0o100644<<16
    archive.writestr(entry,path.read_bytes())

def build(release_version,repo=None):
    version(release_version)
    label=display_version(release_version)
    if repo and not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):
        raise ValueError('Repository must use OWNER/REPOSITORY format')
    (BASE/'version.json').write_text(json.dumps({'version':release_version}))
    settings={'manifest_url':f'https://github.com/{repo}/releases/latest/download/update.json' if repo else '', 'automatic':True}
    if repo: (BASE/'update-settings.json').write_text(json.dumps(settings,indent=2))
    dist=BASE/'releases'/release_version
    dist.mkdir(parents=True,exist_ok=True)
    package=dist/f'app-files-{label}.pkg'
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(FILES): add_file(archive,BASE/name,name)
    manifest={'version':release_version,'display_version':label,'download_url':f'https://github.com/{repo}/releases/download/v{label}/{package.name}' if repo else '',
              'sha256':hashlib.sha256(package.read_bytes()).hexdigest()}
    desktop=dist/f'nen-macro-{label}.zip'
    with tempfile.TemporaryDirectory(prefix='build-',dir=dist) as temporary:
        folder=build_desktop(Path(temporary)/'desktop')
        actual={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
        if actual!=DESKTOP_FILES:raise ValueError('Desktop build contains unexpected files')
        with zipfile.ZipFile(desktop,'w',zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(DESKTOP_FILES):add_file(archive,folder/name,name)
    manifest.update(desktop_download_url=f'https://github.com/{repo}/releases/download/v{label}/{desktop.name}' if repo else '',desktop_sha256=hashlib.sha256(desktop.read_bytes()).hexdigest())
    (dist/'update.json').write_text(json.dumps(manifest,indent=2))
    print('Release assets:',dist)
    if not repo: print('Hosting not connected: rerun with --repo OWNER/REPOSITORY before sharing or publishing.')
    return dist

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--version',required=True)
    parser.add_argument('--repo')
    args=parser.parse_args()
    build(args.version,args.repo)
