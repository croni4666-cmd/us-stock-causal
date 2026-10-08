"""Build a wheel and verify canonical defaults/source parity without network access."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
from zipfile import ZipFile
from setuptools.build_meta import build_wheel


def main():
    root=Path.cwd()
    required=['src/resources/__init__.py','data/static/__init__.py','data/static/etf_constituents.py']
    with tempfile.TemporaryDirectory(prefix='usc-wheel-gate-') as folder:
        with contextlib.redirect_stdout(io.StringIO()):
            wheel=Path(folder)/build_wheel(folder)
        with ZipFile(wheel) as archive:
            names=archive.namelist()
            if any(name not in names for name in required): raise ValueError('Missing runtime resource module')
            for name in names:
                if name.startswith(('output/','data/cache/','data/export/','.review/')) or '/.env' in name:
                    raise ValueError('Runtime/private artifact included in wheel')
                if name.endswith('.py'):
                    source=root/name
                    if not source.is_file() or source.read_bytes()!=archive.read(name):
                        raise ValueError('Stale or changed Python source included in wheel')
            assets=[]
            for folder in ('config','data/baseline'):
                for source in (root/folder).iterdir():
                    if source.suffix not in ('.json','.yaml'):continue
                    name='src/resources/'+str(source.relative_to(root)).replace('\\','/')
                    if name not in names or archive.read(name)!=source.read_bytes():
                        raise ValueError('Missing or changed default configuration resource')
                    assets.append(name)
            allowed_resources=set(assets)|{'src/resources/__init__.py'}
            if any(n.startswith('src/resources/') and n not in allowed_resources for n in names):
                raise ValueError('Unexpected stale or private packaged default resource')
            result={'passed':True,'verified_defaults':len(assets),
                    'wheel_sha256':hashlib.sha256(wheel.read_bytes()).hexdigest()}
    print(json.dumps(result));return 0


if __name__=='__main__':raise SystemExit(main())
