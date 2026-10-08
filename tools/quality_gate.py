"""Offline tracked-file release checks. Never print credential values or file bodies."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
import yaml


def inspect(root,paths):
    findings=[]; inventory=[]
    secret=re.compile(r'-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----|\b(?:ghp_|github_pat_|sk-(?:proj-)?)[A-Za-z0-9_\-]{20,}')
    private_home=re.compile(r'(?:[A-Za-z]:[\\/]+Users[\\/]+)(?!<|user(?:name)?[\\/]|Public[\\/])[^\\/\s<>\[{}]+[\\/]',re.I)
    for relative in paths:
        path=root/relative
        if not path.is_file(): findings.append({'path':relative,'rule':'missing_tracked_file'}); continue
        raw=path.read_bytes(); inventory.append({'path':relative,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
        parts=Path(relative).parts
        if relative.startswith(('data/cache/','data/export/')) or Path(relative).name.startswith('commit_msg_'):
            findings.append({'path':relative,'rule':'generated_file_tracked'})
        if any(p in ('.review','.venv','.venv311','__pycache__') for p in parts) or path.name in ('.env','.env.local') or path.suffix in ('.pem','.key'):
            findings.append({'path':relative,'rule':'private_or_local_artifact_tracked'})
        if path.suffix not in ('.py','.md','.txt','.json','.yaml','.yml','.toml','.ipynb','.cmd','.ps1','.svg','.html','.in'):
            continue
        try: content=raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            findings.append({'path':relative,'rule':'not_utf8'});continue
        if secret.search(content): findings.append({'path':relative,'rule':'credential_pattern'})
        if private_home.search(content): findings.append({'path':relative,'rule':'private_home_path'})
        if re.search(r'^(?:<{7}|={7}|>{7})(?:\s|$)',content,re.M):
            # Decorative separators inside scripts/docs are not merge conflicts.
            if re.search(r'^<{7}\s+\S',content,re.M): findings.append({'path':relative,'rule':'merge_conflict'})
        try:
            if path.suffix=='.py': compile(content,relative,'exec')
            elif path.suffix in ('.json','.ipynb'): json.loads(content)
            elif path.suffix in ('.yaml','.yml'): yaml.safe_load(content)
            elif path.suffix=='.toml': tomllib.loads(content)
        except (ValueError,SyntaxError,yaml.YAMLError) as exc:
            findings.append({'path':relative,'rule':'syntax_or_structure','error_type':type(exc).__name__})
    return {'schema_version':1,'python':sys.version.split()[0],'files_checked':len(inventory),
            'passed':not findings,'findings':findings,'inventory':inventory}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv);root=args.root.resolve()
    command=['git','-c','safe.directory='+str(root).replace('\\','/'),'-C',str(root),'ls-files','--cached','--others','--exclude-standard','-z']
    paths=subprocess.check_output(command).decode('utf-8').rstrip('\0').split('\0')
    result=inspect(root,[p for p in paths if p])
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='inventory'},ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__=='__main__': raise SystemExit(main())
