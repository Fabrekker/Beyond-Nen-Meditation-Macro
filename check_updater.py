"""Offline update integrity, rollback and settings-preservation checks."""
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import patch
import zipfile
import updater

ROOT=Path(__file__).parent/'.test-output'/'updater'
ROOT.mkdir(parents=True,exist_ok=True)

def package(extra=None):
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in updater.FILES:
            archive.writestr(name,json.dumps({'version':'1.0.1'}) if name=='version.json' else 'new '+name)
        if extra: archive.writestr(extra,'unauthorized')
    return output.getvalue()

def prepare(folder):
    folder.mkdir(parents=True,exist_ok=True)
    for name in updater.FILES: (folder/name).write_text('old '+name)
    (folder/'version.json').write_text('{"version":"1.0.0"}')
    (folder/'config.json').write_text('personal settings')
    (folder/'update-settings.json').write_text('personal update configuration')

data=package()
manifest={'version':'1.0.1','download_url':'https://example.com/release.zip','sha256':hashlib.sha256(data).hexdigest()}
base=ROOT/'successful'
prepare(base)
with patch.object(updater,'download',return_value=data): updater.stage(manifest,base)
assert updater.apply_pending(base)
assert updater.current(base)=='1.0.1'
assert (base/'macro.py').read_text()=='new macro.py'
assert (base/'config.json').read_text()=='personal settings'
assert (base/'update-settings.json').read_text()=='personal update configuration'

base=ROOT/'invalid'
prepare(base)
for bad in (b'broken download',package('../config.json')):
    tampered={**manifest,'sha256':hashlib.sha256(bad).hexdigest()} if bad.startswith(b'PK') else manifest
    with patch.object(updater,'download',return_value=bad):
        try: updater.stage(tampered,base)
        except ValueError: pass
        else: raise AssertionError('Invalid update was accepted')
assert updater.current(base)=='1.0.0'

base=ROOT/'rollback'
prepare(base)
with patch.object(updater,'download',return_value=data): updater.stage(manifest,base)
real_replace=Path.replace
def fail_one(path,target):
    if path.name=='vision.py': raise OSError('Simulated locked file')
    return real_replace(path,target)
with patch.object(Path,'replace',fail_one):
    try: updater.apply_pending(base)
    except OSError: pass
    else: raise AssertionError('Expected replacement failure')
assert updater.current(base)=='1.0.0'
assert (base/'macro.py').read_text()=='old macro.py'
assert (base/'config.json').read_text()=='personal settings'
assert updater.apply_pending(base)
assert updater.current(base)=='1.0.1'
print('PASS: checked installation, checksum rejection, path traversal rejection, rollback, retry, and personal settings preservation. No network used.')
