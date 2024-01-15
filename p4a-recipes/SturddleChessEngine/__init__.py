"""
Sturddlefish Chess App (c) 2021, 2022, 2023 Cristian Vlasceanu
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

from glob import glob
from os import makedirs, path
from pythonforandroid.recipe import CppCompiledComponentsPythonRecipe, CythonRecipe
from pythonforandroid.logger import shprint
import sh

setup = """from distutils.core import setup
from distutils.extension import Extension
from datetime import datetime

build_stamp = datetime.now().strftime('%m%d%y.%H%M')
inc_dirs = [
    '-I./json/include',
    '-I./libpopcnt',
    '-I./magic-bits/include',
    '-I./simde',
    '-I./version2',
]
setup(
    ext_modules=[Extension('sturddle_chess_engine',
        sources=[
            'sturddle_chess_engine.cpp',
            'captures.cpp',
            'context.cpp',
            'chess.cpp',
            'search.cpp',
            'uci_native.cpp',
        ],
        extra_compile_args=inc_dirs + [
            '-ffast-math',
            '-fvisibility=hidden',
            '-mfpu=neon-vfpv4',
            '-std=c++17',
            '-O3',
            '-Wno-bitwise-instead-of-logical',
            '-Wno-deprecated-declarations',
            '-Wno-unused-label',
            '-Wno-unused-variable',
            '-DCYTHON_WITHOUT_ASSERTIONS',
            '-DNO_ASSERT',
            '-DCALLBACK_PERIOD=512',
            '-DEVAL_FUZZ_ENABLED',
            '-DWITH_NNUE',
            '-DBUILD_STAMP=' + build_stamp,
            '-DUSE_MAGIC_BITS=true',
            '-DPyMODINIT_FUNC=__attribute__((visibility("default"))) extern "C" PyObject*',
        ],
        extra_link_args=['-O3', '-lc++_shared'],
        language='c++')]
)
"""

NAME = 'SturddleChessEngine'

class SturddleChessEngine(CythonRecipe, CppCompiledComponentsPythonRecipe):
    version = '2.0'
    name = NAME
    cython_args = ['--cplus']

    # Do not strip symbols, for debugging crashes
    # def strip_object_files(self, arch, env, build_dir=None):
    #    pass

    def get_project_dir(self):
        dir = self.ctx.root_dir
        return dir[:dir.index('.buildozer')]

    # def should_build(self, arch):
    #     return True

    def unpack(self, arch):
        dest_dir = path.join(self.get_build_container_dir(arch), NAME)
        shprint(sh.rm, '-r', '-f', dest_dir)
        makedirs (dest_dir)
        for src in [
            '__init__.pyx',
            'armvector.h',
            'attack_tables.h',
            'attacks.h',
            'backtrace.h',
            'captures.cpp',
            'common.h',
            'config.h',
            'chess.h',
            'chess.cpp',
            'context.h',
            'context.cpp',
            'nnue.h',
            'primes.hpp',
            'shared_hash_table.h',
            'search.h',
            'search.cpp',
            'tables.h',
            'thread_pool.hpp',
            'uci_native.cpp',
            'utility.h',
            'weights.h',
            'zobrist.h',
        ]:
            shprint(sh.cp, path.join(self.get_project_dir(), 'sturddle_chess_engine', src), dest_dir)

        # submodules:
        shprint(sh.cp, path.join(self.get_project_dir(), 'sturddle_chess_engine', 'libpopcnt', 'libpopcnt.h'), dest_dir)
        shprint(sh.cp, path.join(self.get_project_dir(), 'sturddle_chess_engine', 'magic-bits', 'include', 'magic_bits.hpp'), dest_dir)
        shprint(sh.cp, '-r', path.join(self.get_project_dir(), 'sturddle_chess_engine', 'json'), dest_dir)
        shprint(sh.cp, '-r', path.join(self.get_project_dir(), 'sturddle_chess_engine', 'simde'), dest_dir)
        shprint(sh.cp, '-r', path.join(self.get_project_dir(), 'sturddle_chess_engine', 'version2'), dest_dir)

        with open(path.join(dest_dir, 'setup.py'), 'w') as f:
            f.write(setup)

        shprint(sh.mv, path.join(dest_dir, '__init__.pyx'), path.join(dest_dir, 'sturddle_chess_engine.pyx'))

recipe = SturddleChessEngine()
