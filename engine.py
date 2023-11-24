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
import time
from datetime import datetime
from enum import IntEnum
from threading import Event

import chess
import chess.pgn
import chess.polyglot
from kivy.logger import Logger

from sturddle_chess_engine import *
from worker import Locking, WorkerThread



def format_move(board, move):
    if board.is_kingside_castling(move):
        return 'O-O'
    if board.is_queenside_castling(move):
        return 'O-O-O'
    uci = move.uci()
    if board.is_capture(move):
        return '{}x{}'.format(uci[:2], uci[2:])
    return uci


class BoardModel(chess.Board, Locking):

    def __init__(self, fen=chess.STARTING_FEN, *args):
        Locking.__init__(self)
        chess.Board.__init__(self, fen, *args)

        self._captures = [[], []]
        self._captures_stack = []


    @Locking.synchronized
    def base_copy(self):
        board = super().copy()
        board.__class__ = chess.Board
        return board


    @Locking.synchronized
    def copy(self):
        return super().copy()


    @Locking.synchronized
    def piece_count(self):
        return chess.popcount(self.occupied)


    @Locking.synchronized
    def piece_at(self, square):
        return super().piece_at(square)


    @Locking.synchronized
    def pop(self):
        if self._captures_stack:
            self._captures = self._captures_stack.pop()
        return super().pop()


    def push_with_format(self, move, notation):
        '''
        Format move to string and push to the board.

        Return formatted string representation of the move.

        No need for @synchronized: both push and san_and_push are decorated.
        '''
        assert self.is_legal(move)
        if notation == 'san':
            return self.san_and_push(move)

        move_str = format_move(self, move)
        self.push(move)
        return move_str


    @Locking.synchronized
    def push(self, move):
        self._captures_stack.append([self._captures[0].copy(), self._captures[1].copy()])
        super().push(move)


    # override
    def _push_capture(self, move, capture_square, piece_type, was_promoted):
        self._captures[self.turn].append(piece_type)


    @Locking.synchronized
    def san_and_push(self, move):
        return super().san_and_push(move)


class Timer:
    def __init__(self):
        self.start = datetime.now()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.info = Timer.format_time(int(self.seconds_elapsed()))

    @staticmethod
    def format_time(seconds):
        return f'{seconds//60:02d}:{seconds%60:02d}'

    def seconds_elapsed(self):
        return (datetime.now() - self.start).total_seconds()


SearchAlgorithm = [MTDf_i, Negamax_i, Negascout_i]



class Engine:
    class Algorithm(IntEnum):
        MTDF = 0
        NEGAMAX = 1
        NEGASCOUT = 2

    def __init__(self, update_callback=None, update_move_callback=None, log=lambda _:None):
        self.board = BoardModel()
        self.search = None
        self.polyglot_file = 'book.bin'
        self.book = None
        self.opponent = chess.WHITE
        self.worker = WorkerThread()
        self.depth_callback = lambda *_: None
        self.promotion_callback = None
        self.search_complete_callback = lambda *_: None
        self.search_callback = None
        self.update_callback = update_callback
        self.update_move_callback = update_move_callback
        self.log = log
        self.redo_list = []
        self.use_opening_book(True)
        self.error = None
        self.bootstrap = Event()
        self.variable_strategy = True
        self.notation = 'san'
        self.pv = None
        self.time_limit = 10
        self.depth_limit = 100
        self.algorithm = Engine.Algorithm.MTDF
        self.hashfull = 0
        self.clear_hash_on_move = False
        self.node_count = 0


    def _apply(self, move):
        move_str = self.push_with_format(move) # san or uci
        if move_str:
            self.update(move, move_str)

        if self.clear_hash_on_move:
            clear_hashtable()


    def apply(self, move):
        if move and not self.busy:
            self._apply(move)
            return move


    @property
    def busy(self):
        return bool(self.search)


    def iteration_callback(self, search_instance, node, score, n_nodes, nps, ms):
        self.pv = node.get_pv()  # Hold on to PV from complete iteration (non timed out)
        depth = search_instance.current_depth
        knps = nps / 1000
        self.hashfull = get_hash_full()
        self.depth_callback()
        self.log(f'{chess.COLOR_NAMES[self.board.turn]} / {depth}: {score/100 :.2f} {knps:.2f} kNps {self.pv}')


    def cancel(self):
        while self.search:
            self.search.cancel()
            time.sleep(0.2)


    def can_auto_open(self):
        if not self.book or self.busy or self.is_game_over():
            return False
        try:
            return self.search_opening(self.board) != None
        except:
            return False


    def can_redo(self):
        return self._can_use(self.redo_list) and self.board.is_legal(self.redo_list[-1]) \
            and (not self.board.move_stack or self.board.move_stack[-1] == self.redo_list[-2])


    def can_undo(self):
        return len(self.board.move_stack) > [1, 0][self.opponent]


    def can_switch(self):
        return not self.busy


    def _can_use(self, moves_list):
        return len(moves_list) > 1 and not self.busy


    def check_redo(self):
        '''
        Check if last two (half) moves match the Redo list
        '''
        if self.redo_list:
            if self.redo_list[-2:] == self.last_moves():
                self.redo_list = self.redo_list[:-2]
            else:
                self.redo_list.clear()


    def current_depth(self):
        return 0 if self.search is None else self.search.current_depth



    def last_moves(self):
        return [ self.board.move_stack[-i] if i <= len(self.board.move_stack) else None for i in range(2,0,-1) ]


    def is_game_over(self):
        try:
            # Use a temporary board copy, because python-chess pops the stack
            # when checking for draw claims, and can thus cause race conditions.

            return self.board.base_copy().is_game_over(claim_draw=True)
        except:
            return False


    def is_opponents_turn(self):
        return self.board.turn == self.opponent


    """ Validate and convert UCI string to Move """
    def validate_from_uci(self, uci, promotion=None):
        if not self.is_game_over():
            try:
                move = chess.Move.from_uci(uci)
            except:
                return None
            if self.board.is_legal(move):
                return move
            try:
                return self._find_move(move, promotion)
            except ValueError:
                pass


    def is_promotion(self, move):
        return any((m.promotion for m in self.board.generate_legal_moves(
            chess.BB_SQUARES[move.from_square],
            chess.BB_SQUARES[move.to_square]))
        )


    def _find_move(self, move, promotion=None):

        def _get_promotion():
            if promotion is None and self.promotion_callback and self.is_promotion(move):
                # extra validation, in case pawn is pinned
                board = chess.Board(fen=self.board.fen())
                board.remove_piece_at(move.from_square)
                board.set_piece_at(move.to_square, chess.Piece(chess.QUEEN, board.turn), True)
                board.turn ^= True
                if board.is_valid():
                    self.promotion_callback(move)
                    return 0

            return promotion

        return self.board.find_move(move.from_square, move.to_square, _get_promotion())


    def input(self, move, promotion=None):
        move = self.validate_from_uci(move, promotion)
        self.update(move)
        if self.apply(move):
            return self.make_move()


    def output(self):
        try:
            if self.update_callback:
                self.update()
                self.bootstrap.wait(30)

            move = self.search_move()
            self.check_redo()

            return self.apply(move) if move else self.update()

        except Exception as e:
            if not self.update_callback:
                raise
            self.error = e
            self.update() # schedule update so that the UI picks up exception


    def make_move(self):
        if self.busy or self.is_game_over():
            return False

        self.start()
        if self.update_callback is None:
            return self.output() # search for move synchronously

        # wrap self.output to avoid filling up the worker thread's outgoing queue
        def output_machine_move():
            self.output()

        self.worker.send_message(output_machine_move) # use background thread
        return True


    @staticmethod
    def print_board(board):
        print_board(board)


    def push_with_format(self, move):
        if not self.board.is_legal(move):
            Logger.warning(f'push_with_format: {move} is not legal')
            self.update_callback()
        else:
            return self.board.push_with_format(move, self.notation)


    def update_last_moves(self):
        last = self.last_moves()
        for move in last:
            if move:
                self.board.pop()
        for move in last:
            if move:
                self.update_move(self.push_with_format(move))


    def update_move(self, move_str):
        if move_str and self.update_move_callback:
            self.update_move_callback(not self.board.turn, move_str)


    def update(self, move=None, move_str=None):
        self.update_move(move_str)

        if self.update_callback:
            move = move or self.last_moves()[-1]
            return self.update_callback(move)


    def update_prev_moves(self):
        # After undoing a move, temporarily pop the previous moves
        # then use push_with_format to pretty-print
        prev_moves = []
        for i in range(0, min(len(self.board.move_stack), 2)):
            prev_moves = [self.board.pop()] + prev_moves

        if self.update_move_callback:
            self.update_move_callback(chess.WHITE, None)
            for move in prev_moves:
                self.update_move_callback(self.board.turn, self.push_with_format(move))


    def undo(self):
        self.cancel()
        if self.board.move_stack:
            if self.is_opponents_turn():
                self.board.pop()
            self.redo_list += self.last_moves()
            if self.board.move_stack:
                self.board.pop()
            if self.update_move_callback:
                self.update_prev_moves()
            self.update()


    def redo(self):
        if self.is_opponents_turn() and self.redo_list:
            self.apply(self.redo_list[-1])
            self.make_move()


    """ Lookup move in the opening book """
    def search_opening(self, board):
        if self.variable_strategy:
            entry = self.book.weighted_choice(board)
        else:
            entry = self.book.find(board)
        return entry.move


    def search_move(self, analysis_mode=False):
        if self.book:
            try:
                if move := self.search_opening(self.board.base_copy()):
                    return move
            except:
                pass
        #
        # instantiate search algorithm
        #
        self.search = SearchAlgorithm[self.algorithm](
            self.board,
            depth = self.depth_limit,
            time_limit = self.time_limit,
            callback = self.search_callback,
            iteration_cb = self.iteration_callback,
            threads_report = self._update_node_count
            )
        self.search.set_analysis_mode(analysis_mode)

        with Timer() as timer:
            move, score = self.search.search()

        search = self.search

        assert score is not None
        self.search_complete_callback(search, self.board.turn, move, score)

        self.search = None

        # user has cancelled the search?
        if search.is_cancelled:
            return None

        return move


    def _update_node_count(self, algo, ctxts):
        main_context = algo.context
        self.node_count = main_context.stats()['nodes']

        for secondary_task_context in ctxts:
            if secondary_task_context:
                self.node_count += secondary_task_context.stats()['nodes']


    def setup(self, moves_list, starting_fen):
        assert not self.board.move_stack
        if starting_fen:
            self.board.set_fen(starting_fen)
            self.update_missing_pieces()
        if moves_list:
            for move in moves_list:
                self.update_move(self.push_with_format(move))
            self.update(move)


    """ Select which notation to use (SAN or coordinates) """
    def set_notation(self, notation):
        assert notation in ['san', 'uci']
        if self.notation != notation:
            self.notation = notation
            self.update_last_moves()


    def start(self):
        pass


    def stop(self):
        self.worker.stop()


    def pause(self, cancel=True):
        assert cancel or not self.busy
        self.worker.pause()
        if cancel:
            self.cancel()


    """ Start a new game. """
    def restart(self, auto_move=True):
        if not self.busy:
            self.board = BoardModel()
            self.redo_list.clear()

            clear_hashtable()
            self.hashfull = 0

            if self.update_callback:
                self.update()
            self.resume(auto_move)


    def resume(self, auto_move=True):
        self.worker.resume()
        if auto_move and not self.is_opponents_turn():
            return self.make_move()


    def result(self):
        return self.board.result(claim_draw=True)


    def set_fen(self, fen, castling_rights=None):
        self.board.set_fen(fen)
        self.update_missing_pieces()

        if castling_rights != None:
            self.board.castling_rights = castling_rights

        self.update()


    def starting_fen(self):
        board = self.board.base_copy()
        while board.move_stack:
            board.pop()
        return board.fen()


    """
    Search opening book and automatically play opening moves for both sides.
    """
    def auto_open(self, move_callback=lambda: None):
        assert self.book
        moves_count = 0

        while not self.is_game_over():
            try:
                move = self.search_opening(self.board)
                if not move:
                    break
                self._apply(move)
                move_callback()
                moves_count += 1
            except IndexError:
                break

        if not self.is_opponents_turn():
            self.make_move()

        return moves_count


    def transcript(self, eco=None, headers={}, engine=True, **kwargs):
        '''
        Generate transcript in PGN format.
        See https://en.wikipedia.org/wiki/Portable_Game_Notation
        '''

        game, title = chess.pgn.Game(), 'Game Transcript'

        fen = self.starting_fen()
        if fen != chess.STARTING_FEN:
            game.headers['FEN'] = fen

        if headers is not None:
            # remove some headers...
            for tag in ['White', 'Black', 'Date', 'Event', 'Round', 'Site']:
                game.headers.pop(tag)

            if not self.worker.is_paused():
                game.headers['Date'] = datetime.now().date().strftime('%Y.%m.%d')

                if engine:
                    # which side is the engine playing?
                    game.headers[['White', 'Black'][self.opponent]] = 'Sturddle ' + version()

        node, board = game, chess.Board(fen)
        for move in self.board.move_stack:
            node = node.add_variation(move)

            board.push(move)

            # Lookup Encyclopedia of Chess Openings
            if eco and headers is not None:
                if opening := eco.lookup(board):
                    title = opening['name']
                    game.headers['ECO'] = opening['eco']
                    name = opening['name'].split(':')
                    game.headers['Opening'] = name[0].strip()
                    if len(name) > 1:
                        game.headers['Variation'] = name[1].strip()

        if headers is not None:
            if self.is_game_over():
                game.headers['Result'] = self.result()
            else:
                game.headers.pop('Result', None)  # Do not include result for game in progress.

            for tag, val in headers.items():
                game.headers[tag] = val

        exporter = chess.pgn.StringExporter(headers=headers is not None, **kwargs)
        return title, game.accept(exporter)


    def update_missing_pieces(self):
        pos = self.board
        for color in (chess.WHITE, chess.BLACK):
            mask = pos.occupied_co[not color]
            for i in range(0, 8 - chess.popcount(pos.pawns & mask)):
                pos._captures[color].append(chess.PAWN)
            for i in range(0, 2 - chess.popcount(pos.knights & mask)):
                pos._captures[color].append(chess.KNIGHT)
            for i in range(0, 2 - chess.popcount(pos.bishops & mask)):
                pos._captures[color].append(chess.BISHOP)
            for i in range(0, 2 - chess.popcount(pos.rooks & mask)):
                pos._captures[color].append(chess.ROOK)
            for i in range(0, 1 - chess.popcount(pos.queens & mask)):
                pos._captures[color].append(chess.QUEEN)


    def use_opening_book(self, value):
        if value:
            try:
                self.book = chess.polyglot.MemoryMappedReader(self.polyglot_file)
                return self.book
            except FileNotFoundError:
                Logger.warning(f'engine: {self.polyglot_file} not found.')
        self.book = None


    @staticmethod
    def chess_ver():
        return chess.__version__
