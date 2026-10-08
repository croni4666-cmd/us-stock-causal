"""Release checks inspect actual candidate files and retain only redacted findings."""
from tools.quality_gate import inspect


def test_gate_rejects_sensitive_or_generated_candidates_without_echoing_values(tmp_path):
    token='ghp_'+'x'*30
    home='C:'+'/Users/'+'ExamplePerson'+'/cache'
    (tmp_path/'bad.py').write_text(f"credential={token!r}\npath={home!r}\n",encoding='utf-8')
    (tmp_path/'data/cache').mkdir(parents=True)
    (tmp_path/'data/cache/stale.json').write_text('{}',encoding='utf-8')
    result=inspect(tmp_path,['bad.py','data/cache/stale.json'])
    assert not result['passed']
    assert {f['rule'] for f in result['findings']}=={'credential_pattern','private_home_path','generated_file_tracked'}
    assert token not in str(result) and home not in str(result)


def test_gate_rejects_invalid_python_instead_of_running_it(tmp_path):
    (tmp_path/'broken.py').write_text('def invalid(\n',encoding='utf-8')
    result=inspect(tmp_path,['broken.py'])
    assert not result['passed'] and result['findings'][0]['rule']=='syntax_or_structure'
