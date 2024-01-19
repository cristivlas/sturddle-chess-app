"""
Sturddlefish Chess App (c) 2021, 2022, 2023, 2024 Cristian Vlasceanu
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
"""
import csv
import io
import os
import string

import chess
import chess.pgn

from functools import lru_cache
from os import path, walk
from annembed.search import Index


'''
Representation of a chess opening.
'''
class Opening:
    def __init__(self, row):
        '''
        Construct Opening object for ECO database row.
        '''
        self.row = row

    @property
    def name(self):
        return self.row['name']

    @property
    def eco(self):
        ''' ECO classificatio code '''
        return self.row['eco']

    @property
    def epd(self):
        '''
        Extended Position Description.
        https://www.chessprogramming.org/Extended_Position_Description
        '''
        return self.row['epd']

    @property
    def pgn(self):
        '''
        String containing the moves sequence in Portable Game Notation
        using Simplified Algebraic Notation.
        '''
        return self.row['pgn']

    @property
    def uci(self):
        '''
        String containing the opening moves sequence in UCI Notation
        '''
        return self.row['uci']

    def __repr__(self):
        return repr(self.row)


class ECO:
    '''
    Wrapper for: https://github.com/niklasf/eco

    Identify openings using entries from The Encyclopaedia of Chess Openings
    https://en.wikipedia.org/wiki/Encyclopaedia_of_Chess_Openings
    '''

    def __init__(self, index_dir=None):
        self.by_fen = {}
        self.data = []  # All openings
        for fname in self.tsv_files():
            self.read_tsv_file(fname)
        self.index = Index(index_dir) if index_dir else None

    def tsv_files(self):
        for dir, _subdirs, files in walk(f'{os.path.dirname(__file__)}/eco/dist'):
            for f in sorted(files):
                if f.endswith('.tsv'):
                    yield path.join(dir, f)

    def read_tsv_file(self, fname):
        with open(fname) as f:
            reader = csv.DictReader(f, dialect='excel-tab')
            for row in reader:
                self.by_fen[row['epd']] = row
                self.data.append(row)

    def lookup(self, board, transpose=False):
        ''' Lookup by board position (FEN). '''
        row = self.by_fen.get(board.epd(), None)
        if row is None and board._stack:
            prev = chess.Board()
            board._stack[-1].restore(prev)
            row = self.by_fen.get(prev.epd(), None)

        if row and not transpose:
            pgn = chess.pgn.read_game(io.StringIO(row['pgn']))
            for i, move in enumerate(pgn.mainline_moves()):
                if i >= len(board.move_stack) or move != board.move_stack[i]:
                    return None
        return row

    @staticmethod
    def get_codes(eco):
        codes = eco.lower().split('-')  # support ranges (e.g. B20-B99)
        if codes[0]:
            alpha = codes[0][0]
            if len(codes) == 2 and alpha == codes[1][0]:
                try:
                    start, end = int(codes[0][1:]), int(codes[1][1:])
                    codes = [f'{alpha}{i:02d}' for i in range(start, end + 1)]
                except:
                    pass

        return codes

    @lru_cache(maxsize=256)
    def query_by_name(self, query, *, max_distance=1.5, top_n=5):
        if self.index:
            idx = self.index.search(query, max_distance=max_distance, top_n=top_n)
            return [Opening(self.data[i]) for i,_ in idx]
        return []
