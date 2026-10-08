"""Read-only packaged defaults copied from canonical project assets at build time."""
from importlib.resources import files
from pathlib import Path


def default_asset(relative, project_root):
    parts=Path(relative).parts
    if Path(relative).is_absolute() or '..' in parts:
        raise ValueError('default asset must have a relative project path')
    candidate=Path(project_root)/relative
    if candidate.is_file(): return candidate
    packaged=files(__package__).joinpath(*parts)
    if not packaged.is_file(): raise FileNotFoundError(f'Missing packaged default: {relative}')
    # Supported pip installation is an unpacked wheel; do not use short-lived
    # as_file contexts to provide a cached path to later readers.
    return Path(str(packaged))
