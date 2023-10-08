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
import re
from functools import partial, reduce

import chess
import pyparsing as pp
from kivy.logger import Logger


_rows = {
    '1': 'one', '2': 'two', '3': 'three', '4': 'four',
    '5': 'five', '6': 'six', '7': 'seven', '8': 'eight'
}

def _square_name(square, spell_digits=False):
    name = chess.square_name(square).upper()
    if spell_digits:
        for r in _rows:
            if r in name:
                name = name.replace(r, ' ' + _rows[r])
                break
    return name


def strip_determiner(func):
    def _filter(self, s, loc, tokens):
        func(self, s, loc, list(filter(lambda w: w != 'the', tokens)))
    return _filter


class NLP:
    '''
    Natural Language Processor
    '''

    keywords = (['capture', 'castle', 'promote', 'take',]
        + chess.PIECE_NAMES[1:]
        + [chess.square_name(s) for s in chess.SQUARES]
    )


    def __init__(self):
        keywords = 'yes yep yeah affirmative'.split()
        self.YES = reduce(lambda a, b: a | b, (pp.Keyword(k) for k in keywords))

        keywords = 'no nope negative'.split()
        self.NO = reduce(lambda a, b: a | b, (pp.Keyword(k) for k in keywords))

        self._init_grammar()
        self._moves = []
        self._board = None
        self.any = None
        self.command = None  # recognized command (other than a move)


    def _init_grammar(self):
        '''
        grammar :=
            ['the'] <piece> takes ['the'] <piece> [(at|on) <square>]
            | ['the'] <piece> takes (at|on) <square>
            | castle [king|queen side]
            | ['the'] <piece> [at <square>] to <square>
            | promote to <piece>
            | <square> [to] <square>
            | <square>
            | <check>
        '''
        AT = pp.Keyword('at') | pp.Keyword('on')
        CASTLE = pp.Keyword('castle')
        CHECK = pp.Keyword('check')
        FROM = pp.Keyword('at') | pp.Keyword('from')
        OPENING = pp.Keyword('opening')
        PROMOTE = pp.Keyword('promote') | pp.Keyword('promotes')
        PIECE = pp.one_of(' '.join(chess.PIECE_NAMES[1:]))
        SETUP = pp.Keyword('setup') | pp.Keyword('set') + pp.Keyword('up')
        SQUARE = pp.one_of(' '.join([chess.square_name(s) for s in chess.SQUARES]))
        TAKES = pp.Keyword('captures') | pp.Keyword('takes')
        THE = pp.Opt(pp.Keyword('the'))
        TO = pp.Keyword('to')

        # -----------------------------------------
        # Grammar rules for describing chess moves.
        # -----------------------------------------

        capture_piece = THE + PIECE + TAKES + THE + PIECE + pp.Opt(AT + SQUARE)
        capture_square = THE + PIECE + TAKES + AT + SQUARE
        capture = (
            capture_piece.set_parse_action(self._on_capture_piece) |
            capture_square.set_parse_action(self._on_capture_square)
        )

        castle_side = (pp.Keyword('king') | pp.Keyword('queen')) + pp.Keyword('side')
        castle = (CASTLE + pp.Opt(castle_side)).set_parse_action(self._on_castle)
        check = CHECK.set_parse_action(self._on_check)

        piece_move = THE + PIECE + pp.Opt(FROM + SQUARE) + TO + SQUARE
        uci_move = SQUARE + pp.Opt(TO) + SQUARE
        pawn_move = SQUARE.copy()

        move = (
            uci_move.set_parse_action(self._on_uci_move)    |
            piece_move.set_parse_action(self._on_piece_move)|
            pawn_move.set_parse_action(self._on_pawn_move)
        )
        promotion = (PROMOTE + TO + PIECE).set_parse_action(self._on_promo)

        # -----------------------------------------
        # Grammar rules for miscellaneous commands
        # -----------------------------------------

        analyze = pp.Keyword('analyze') | pp.Keyword('evaluate') + THE + pp.Opt(pp.Keyword('position'))
        edit = pp.Keyword('edit')
        exit = pp.Keyword('exit') | pp.Keyword('quit')
        new_game = pp.Opt('start') + pp.Opt('a') + pp.Keyword('new') + pp.Keyword('game')
        puzzle = pp.Keyword('puzzle') | pp.Keyword('show') + pp.Opt('me') + THE + pp.Keyword('puzzles')
        settings = pp.Opt('application') + pp.Keyword('settings')
        setup_opening = SETUP + pp.SkipTo(OPENING | pp.StringEnd()).set_parse_action(self._on_any) + pp.Opt(OPENING)
        switch = pp.Keyword('switch')  # flip the board around
        undo = (pp.Keyword('undo') |
            pp.Keyword('take') + (pp.Keyword('it') | pp.Keyword('that') | pp.Keyword('move')) + pp.Keyword('back') |
            pp.Keyword('take') + pp.Keyword('back') + pp.Keyword('move')
        )
        yes_no = self.YES | self.NO

        def assign_command(cmd, *_):
            self.command = cmd

        # -----------------------------------------
        # Put the grammar together and validate it.
        # -----------------------------------------
        commands = (
            analyze.set_parse_action(self._on_analyze) |
            edit.set_parse_action(partial(assign_command, 'edit')) |
            exit.set_parse_action(partial(assign_command, 'exit')) |
            new_game.set_parse_action(partial(assign_command, 'new')) |
            puzzle.set_parse_action(partial(assign_command, 'puzzle')) |
            setup_opening.set_parse_action(partial(assign_command, 'opening')) |
            settings.set_parse_action(partial(assign_command, 'settings')) |
            switch.set_parse_action(partial(assign_command, 'switch')) |
            undo.set_parse_action(partial(assign_command, 'undo')) |
            yes_no.set_parse_action(self._on_yes_no)
        )

        self.grammar = capture | castle | check | commands | move | promotion
        self.grammar.validate()


    def parse(self, fen, text, prev_moves=[]):
        '''
        Parse an English language description of a chess move.

        Return a list of legal moves that match the description, in
        the context of the board position specified by the given FEN.

        '''
        # set up the board context
        self._board = chess.Board(fen=fen)

        # previous moves serve as context for disambiguating promotions
        self._moves = [move for move in prev_moves if move.promotion]

        Logger.debug(f'nlp: text={text}, self._moves={self._moves}')

        # trigger parse actions
        parse_result = self.grammar.search_string(text)
        Logger.debug(f'nlp: parse_result={parse_result}')

        # validate results
        moves = [ move for move in self._moves if self._board.is_legal(move) ]

        Logger.debug(f'stt: moves={moves}')

        if not moves:
            moves = prev_moves

        # cleanup
        self._moves = []
        self._board = None

        return moves


    def run(self, fen, results, on_autocorrect=lambda text: text):
        moves = []
        parsed = set()
        self.any = None
        self.command = None

        for text in results:
            if not text:
                continue
            text = on_autocorrect(self._autocorrect(text))

            if text in parsed:
                # auto-correction may lead to duplicates
                Logger.debug(f'nlp: duplicate \'{text}\'')
                continue

            moves = self.parse(fen, text, moves)

            parsed.add(text)

        return moves


    @strip_determiner
    def _on_analyze(self, s, loc, tok):
        self.command = 'analyze'


    def _on_any(self, s, loc, tok):
        tok = [w for t in tok for w in t.split() if w != 'the']
        self.any = ' '.join(tok).strip()


    @strip_determiner
    def _on_capture_piece(self, s, loc, tok):
        '''
        parse action for: <piece> takes <piece> [(at|on) <square>]
        '''
        # victim type
        piece_type = chess.PIECE_NAMES.index(tok[2])

        victims_mask = self._board.pieces_mask(piece_type, not self._board.turn)

        if len(tok) >= 5:
            # optional 'at <square>'
            victims_mask &= chess.BB_SQUARES[chess.parse_square(tok[4])]

        self._on_capture(victims_mask, tok)


    @strip_determiner
    def _on_capture_square(self, s, loc, tok):
        '''
        parse action for: <piece> takes (at|on) <square>
        '''
        to_square = chess.parse_square(tok[3])
        self._on_capture(chess.BB_SQUARES[to_square], tok)


    def _on_capture(self, to_mask, tok):
        # capturer type
        piece_type = chess.PIECE_NAMES.index(tok[0])

        from_mask = self._board.pieces_mask(piece_type, self._board.turn)

        self._moves = self._board.generate_legal_captures(from_mask, to_mask)


    def _on_castle(self, s, loc, tok):

        castle = ['O-O', 'O-O-O']
        if len(tok) > 1:
            if tok[1].startswith('king'):
                castle = ['O-O']
            elif tok[1].startswith('queen'):
                castle = ['O-O-O']

        for san in castle:
            try:
                self._moves.append(self._board.parse_san(san))
            except:
                pass


    def _on_check(self, s, loc, tok):
        for move in self._board.generate_legal_moves():
            board = chess.Board(fen=self._board.fen())
            board.push(move)
            if board.is_check():
                self._moves.append(move)


    def _on_pawn_move(self, s, loc, tok):
        to_mask = chess.BB_SQUARES[chess.parse_square(tok[0])]
        self._moves = self._board.generate_legal_moves(self._board.pawns, to_mask)


    def _on_promo(self, s, loc, tok):
        '''
        parse action for: promote to <piece>
        '''
        promo_type = chess.PIECE_NAMES.index(tok[2])

        if not self._moves and not s[:loc]:
            mask = self._board.pieces_mask(chess.PAWN, self._board.turn)
            self._moves = self._board.generate_legal_moves(mask, chess.BB_BACKRANKS)

        self._moves = [move for move in self._moves if move.promotion == promo_type]


    @strip_determiner
    def _on_piece_move(self, s, loc, tok):
        '''
        parse action for: <piece> [at <square>] to <square>
        '''
        piece_type = chess.PIECE_NAMES.index(tok[0])

        from_mask = chess.BB_ALL

        if len(tok) == 3:
            to_square = chess.parse_square(tok[2])
        else:
            # optional [at <square>] case
            to_square = chess.parse_square(tok[4])
            from_mask = chess.BB_SQUARES[chess.parse_square(tok[2])]

        from_mask &= self._board.pieces_mask(piece_type, self._board.turn)
        self._moves = self._board.generate_legal_moves(from_mask, chess.BB_SQUARES[to_square])


    def _on_uci_move(self, s, loc, tok):
        from_mask = chess.BB_SQUARES[chess.parse_square(tok[0])]
        to_mask = chess.BB_SQUARES[chess.parse_square(tok[-1])]
        self._moves = self._board.generate_legal_moves(from_mask, to_mask)


    def _on_yes_no(self, s, loc, tok):
        self.command = 'yes' if self.YES.search_string(tok[0]) else 'no'


    '''
    Corrections for some common mistakes in speech recognition.
    '''
    corrections = {
        r'\b284\b' : 'to a4',
        r'\b288\b' : 'to h8',
        r'\bage\s*([1-8])' : r'h\1',
        r'\banyone\b' : 'e1',
        r'\bbakes\b' : 'takes',
        r'\bbe\s*([1-8])' : r'b\1',
        r'\bbe ate\b' : 'b8',
        r'\bbe to\b' : 'b2',
        r'\bbe too\b' : 'b2',
        r'\bbee\s*([1-8])' : r'b\1',
        r'\bbefore\b' : 'b4',
        r'\bborn\b' : 'pawn',
        r'\bbroke\b' : 'rook',
        r'\bbrooke\b' : 'rook',
        r'\bbrooks\b' : 'rook',
        r'\bc a\b' : 'c8',
        r'\bcakes\b' : 'takes',
        r'\bdefine\b' : 'e5',
        r'\beat\s*3\b' : 'e3',
        r'\bevery\b' : 'f3',
        r'\besex\b' : 'e6',
        r'\bfakes\b' : 'takes',
        r'\bjiwon\b' : 'g1',
        r'\bkingside\b' : 'king side',
        r'\bknights\b' : 'knight',
        r'\blook\b' : 'rook',
        r'\bmight\b' : 'knight',
        r'\bnight\b' : 'knight',
        r'\bnightstakes\b' : 'knight takes',
        r'\bnightsticks\b' : 'knight takes',
        r'\bpage\s*([1-8])' : r'h\1',
        r'\bpain\b' : 'pawn',
        r'\bpay for\b' : 'a4',
        r'\bpromote the\b' : 'promote to',
        r'\bpoem\b' : 'pawn',
        r'\bpoint\b' : 'pawn',
        r'\bporn\b' : 'pawn',
        r'\bpornsticks\b' : 'pawn takes',
        r'\bqueenside\b' : 'queen side',
        r'\bremote\b' : 'promote',
        r'\brock\b' : 'rook',
        r'\brocks\b' : 'rook',
        r'\brockstakes\b' : 'rook takes',
        r'\broute\b' : 'rook',
        r'\bruk\b' : 'rook',
        r'\bsee\s*([1-8])' : r'c\1',
        r'\bsee free\b' : 'c3',
        r'\bsee to\b' : 'c2',
        r'\bsee too\b' : 'c2',
        r'\bsite\b' : 'side',
        r'\bsize\b' : 'side',
        r'\bspawn\b' : 'pawn',
        r'\btake screen\b' : 'takes queen',
        r'\bthe ford\b' : 'd4',
        r'\bthe\s*([1-8])' : r'd\1',
        r'\bto eat\b' : 'to e2',
        r'\bv8\b' : 'b8',
    }

    rank_corrections = {
        r'([1-8])2\b' : r'\1 to',
        r'\s+one\b' : '1',
        r'\s+two\b' : '2',
        r'\s+too\b' : '2',
        r'\s+three\b' : '3',
        r'\s+for\b' : '4',
        r'\s+four\b' : '4',
        r'\s+five\b' : '5',
        r'\s+fine\b' : '5',
        r'\s+sex\b' : '6',
        r'\s+six\b' : '6',
        r'\s+seven\b' : '7',
        r'\s+ate\b' : '8',
        r'\s+eight\b' : '8'
    }

    def _autocorrect(self, text):
        '''
        Correct speech recognition results.
        '''
        # expect speech results as a list of non-empty strings
        assert text

        text = text.lower()

        for k in self.rank_corrections:
            text = re.sub(k, self.rank_corrections[k], text)

        for k in self.corrections:
            text = re.sub(k, self.corrections[k], text)

        return text


def describe_move(
        board,
        move,
        use_from_square=False,
        announce_check=False,
        announce_capture=False,
        spell_digits=False
    ):
    '''
    Return a description of the move in English.

    The description must satisfy the NLP grammar.
    '''

    if board.is_kingside_castling(move):
        return 'castle king side'

    elif board.is_queenside_castling(move):
        return 'castle queen side'

    if move.promotion:
        use_from_square = True # ... instead of piece type

    to_square = _square_name(move.to_square, spell_digits)
    target = board.piece_type_at(move.to_square) if announce_capture else None
    piece_type = board.piece_type_at(move.from_square)
    if use_from_square:
        prefix = _square_name(move.from_square, spell_digits)
    else:
        prefix = chess.piece_name(piece_type)

    if target:
        text = f'{prefix} takes {chess.piece_name(target)} on {to_square}'
    # elif use_from_square and piece_type == chess.PAWN:
    #     text = to_square
    else:
        text = f'{prefix} to {to_square}'

    if move.promotion:
        text += f', promote to {chess.piece_name(move.promotion)}'

    if announce_check:
        board = board.copy()
        board.push(move)
        if board.is_checkmate():
            text += '. Checkmate!'
        elif board.is_check():
            text += '. Check!'

    return text
