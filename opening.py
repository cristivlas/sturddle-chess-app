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
import string

import chess
import chess.pgn
import rapidfuzz

from collections import defaultdict
from functools import lru_cache
from kivy.logger import Logger
from os import path, walk
from metaphone import doublemetaphone


def _strip_punctuation(input):
    return ''.join(char for char in input if char not in string.punctuation)


def _preprocess(input):
    return doublemetaphone(_strip_punctuation(input))[0]


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

    def __init__(self):
        '''
        Read TSV files and index by ECO, FEN and phonetic name.
        '''
        self.by_eco = defaultdict(list)
        self.by_fen = {}
        self.by_phonetic_name = {}
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
                self.by_eco[row['eco'].lower()].append(row)
                self.by_fen[row['epd']] = row
                name = row['name']
                self.by_name[name.lower()] = row
                self.by_phonetic_name[_preprocess(name)] = row


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


    def phonetical_lookup(self, name, *, confidence=65):
        openings = self.by_phonetic_name
        phonetic_name = doublemetaphone(name)[0]

        result = rapidfuzz.process.extractOne(phonetic_name, openings.keys())
        Logger.debug(f'phonetical: name="{name}" phonetic_name={phonetic_name} result={result}')

        if result:
            match, score, _ = result
            if score >= confidence:
                row = openings[match]
                matched_name = row['name']
                # reverse match for verification
                result = rapidfuzz.process.extractOne(name, [matched_name])

                Logger.debug(f'phonetical: matched_name="{matched_name}" result={result}')
                if result and result[1] >= confidence:
                    return Opening(row)


    @staticmethod
    def get_codes(eco):
        codes = eco.lower().split('-')  # support ranges (e.g. B20-B99)

        alpha = codes[0][0]
        if len(codes) == 2 and alpha == codes[1][0]:
            try:
                start, end = int(codes[0][1:]), int(codes[1][1:])
                codes = [f'{alpha}{i:02d}' for i in range(start, end + 1)]
            except:
                pass

        return codes


    @lru_cache(maxsize=256)
    def name_lookup(self, name, eco=None, *, confidence=90):
        '''
        Lookup chess opening by name and classification code using fuzzy name matching.

        '''
        if eco is not None:
            keys = set()
            for eco in self.get_codes(eco):
                keys.update({r['name'].lower() for r in self.by_eco.get(eco, [])})
        else:
            keys = self.by_name.keys()

        return self.fuzzy_lookup(
            self.by_name,
            keys,
            name,
            min_confidence_level=confidence
        )


    @staticmethod
    def fuzzy_lookup(dict, keys, name, *, min_confidence_level):
        '''
        Lookup the given name by fuzzy matching against a subset of dictionary keys.

        Params:
            dict: a dictionary-like collection of opening "data rows", indexed by lowercase name;
            keys: a subset of keys (can be same as dict.keys());
            name: the name to lookup by;
            min_confidence_level: the minimum acceptable fuzzy matching score.

        Return on Opening object if successful, otherwise return None

        '''
        corrections = {
            "opening": "attack",
            "opening": "",
            "'s": "",
            None: None,
        }
        best_match = None
        best_score = 0

        name = name.lower()

        for k, v in corrections.items():
            if k:
                query = name.replace(k, v).strip()
                if query == name:
                    continue
            else:
                query = name

            result = rapidfuzz.process.extractOne(query, keys)

            Logger.debug(f'fuzzy_lookup: query="{query}" result={result} mcl={min_confidence_level}')

            if result:
                match, score, _ = result

                if score >= min_confidence_level:
                    if score > best_score:
                        best_match, best_score = match, score

        if best_match:
            return Opening(dict[best_match])


    def openings(self):
        for _, v in self.by_fen.items():
            yield v
