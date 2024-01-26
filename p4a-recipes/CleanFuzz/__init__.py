from pythonforandroid.recipe import PythonRecipe
from pythonforandroid.logger import logger

import sh


class RapidFuzzCleanupRecipe(PythonRecipe):
    """
    Fake recipe, to remove x64_64 .so files installed by rapidfuzz.
    Ideally we would build rapidfuzz from source, but that's a tall
    order: rapidfuzz uses skbuild and CMake.
    """

    depends = ['rapidfuzz']  # Ensure this runs after rapidfuzz is built
    call_hostpython_via_targetpython = False  # Not compiling anything

    def build_arch(self, arch):
        import os
        
        name = self.ctx.bootstrap.distribution.name
        dir = os.path.join(self.ctx.python_installs_dir, name, arch.arch, 'rapidfuzz')
        
        logger.info(f'Cleaning up {dir} ...')
      
        for root, dirs, files in os.walk(dir):
            for file in files:
                filepath = os.path.join(root, file)
                filetype = sh.file(filepath, '-b')
                if 'x86_64' in filetype:
                    os.remove(filepath)
                    logger.info(f'Removed: {filepath}')

    def unpack(self, arch):
        ...

recipe = RapidFuzzCleanupRecipe()

