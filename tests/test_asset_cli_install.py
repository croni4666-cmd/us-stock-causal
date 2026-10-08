"""The documented module command must work after install outside checkout."""
import subprocess
import sys


def test_asset_cli_importable_from_isolated_installed_environment(tmp_path):
    run = subprocess.run([sys.executable, '-X', 'utf8', '-I', '-m', 'examples.asset_report', '--help'],
                         cwd=tmp_path, capture_output=True, text=True, timeout=20)
    assert run.returncode == 0, run.stderr
    assert 'sync' in run.stdout and 'report' in run.stdout
