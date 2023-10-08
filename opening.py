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
"""
import csv
import io
from os import path, walk

import chess
import chess.pgn


class ECO:
    '''
    Wrapper for: https://github.com/niklasf/eco

    Identify openings using entries from The Encyclopaedia of Chess Openings
    https://en.wikipedia.org/wiki/Encyclopaedia_of_Chess_Openings
    '''

    def __init__(self):
        '''
        Read TSV files and index by FEN and name.
        '''
        self.by_fen = {}
        self.by_name = {}

        for fname in self.tsv_files():
            self.read_tsv_file(fname)


    def tsv_files(self):
        for dir, _subdirs, files in walk('eco/dist'):
            for f in sorted(files):
                if f.endswith('.tsv'):
                    yield path.join(dir, f)


    def read_tsv_file(self, fname):
        with open(fname) as f:
            reader = csv.DictReader(f, dialect='excel-tab')
            for row in reader:
                self.by_fen[row['epd']] = row
                self.by_name[row['name']] = row


    def lookup(self, board, transpose=False):
        '''
        Lookup by board position (FEN)
        '''
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


    def openings(self):
        for _, v in self.by_fen.items():
            yield v
