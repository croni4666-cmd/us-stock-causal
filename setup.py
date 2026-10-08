"""Copy canonical read-only defaults into wheels without duplicate tracked assets."""
from pathlib import Path
import shutil
from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithDefaults(build_py):
    def run(self):
        super().run()
        source=Path(__file__).parent
        for folder in ('config','data/baseline'):
            for item in (source/folder).iterdir():
                if item.suffix not in ('.json','.yaml'): continue
                target=Path(self.build_lib)/'src/resources'/folder/item.name
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(item,target)


setup(cmdclass={'build_py':BuildWithDefaults})
