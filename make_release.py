"""Owner tool: create small GitHub release assets without personal settings."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile
from updater import FILES,version

BASE=Path(__file__).resolve().parent

def build(release_version,repo=None):
    version(release_version)
    if repo and not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):
        raise ValueError('Repository must use OWNER/REPOSITORY format')
    (BASE/'version.json').write_text(json.dumps({'version':release_version}))
    settings={'manifest_url':f'https://github.com/{repo}/releases/latest/download/update.json' if repo else '', 'automatic':True}
    if repo: (BASE/'update-settings.json').write_text(json.dumps(settings,indent=2))
    dist=BASE/'releases'/release_version
    dist.mkdir(parents=True,exist_ok=True)
    package=dist/f'nen-macro-{release_version}-update.zip'
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(FILES): archive.write(BASE/name,name)
    manifest={'version':release_version,'download_url':f'https://github.com/{repo}/releases/download/v{release_version}/{package.name}' if repo else '',
              'sha256':hashlib.sha256(package.read_bytes()).hexdigest()}
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
