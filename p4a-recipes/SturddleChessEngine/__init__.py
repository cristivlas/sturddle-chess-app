"""
Sturddlefish Chess App (c) 2021, 2022 Cristian Vlasceanu
-------------------------------------------------------------------------

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
-------------------------------------------------------------------------

p4a recipe for compiling the C++ engine
"""

from pythonforandroid.recipe import CppCompiledComponentsPythonRecipe, CythonRecipe
from pythonforandroid.logger import shprint
from os import makedirs, path
import sh

setup = """from distutils.core import setup
from distutils.extension import Extension

setup(
    ext_modules=[Extension('sturddle_chess_engine',
        sources=['sturddle_chess_engine.cpp', 'captures.cpp', 'context.cpp', 'chess.cpp', 'search.cpp'],
        extra_compile_args=[
            '-O3',
            '-DCYTHON_WITHOUT_ASSERTIONS',
            '-DNO_ASSERT',
            '-Wno-error',
            '-DCALLBACK_PERIOD=512'
        ],
        extra_link_args=['-O3'],
        language='c++')]
)
"""

NAME = 'SturddleChessEngine'

class SturddleChessEngine(CythonRecipe, CppCompiledComponentsPythonRecipe):
    version = '1.2'
    name = NAME
    cython_args = ['--cplus']

    def get_project_dir(self):
        dir = self.ctx.root_dir
        return dir[:dir.index('.buildozer')]

    def get_recipe_env(self, arch):
        env = super().get_recipe_env(arch)
        env['LDFLAGS'] += ' -lc++_shared'
        env['CFLAGS'] += ' -Wno-unused-label -Wno-unused-variable -Wno-deprecated-declarations -std=c++17'
        return env

    def should_build(self, arch):
        return True

    def unpack(self, arch):
        dest_dir = path.join(self.get_build_container_dir(arch), NAME)
        shprint(sh.rm, '-r', '-f', dest_dir)
        makedirs (dest_dir)
        for src in [
            '__init__.pyx',
            'attacks.h',
            'captures.cpp',
            'common.h',
            'config.h',
            'chess.h',
            'chess.cpp',
            'context.h',
            'context.cpp',
            'intrusive.h',
            'shared_hash_table.h',
            'search.h',
            'search.cpp',
            'tables.h',
            'utility.h',
            'zobrist.h'
        ]:
            shprint(sh.cp, path.join(self.get_project_dir(), 'sturddle_chess_engine', src), dest_dir)

        # submodules:
        shprint(sh.cp, path.join(self.get_project_dir(), 'sturddle_chess_engine', 'libpopcnt', 'libpopcnt.h'), dest_dir)
        shprint(sh.cp, path.join(self.get_project_dir(), 'sturddle_chess_engine', 'magic-bits', 'include', 'magic_bits.hpp'), dest_dir)
        shprint(sh.cp, path.join(self.get_project_dir(), 'sturddle_chess_engine', 'thread-pool', 'thread_pool.hpp'), dest_dir)

        with open(path.join(dest_dir, 'setup.py'), 'w') as f:
            f.write(setup)

        shprint(sh.mv, path.join(dest_dir, '__init__.pyx'), path.join(dest_dir, 'sturddle_chess_engine.pyx'))

recipe = SturddleChessEngine()
