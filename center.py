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
import chess

class Controller:
    def __init__(self, piece, square):
        self.piece = piece  # The piece object
        self.square = square  # The square where the piece is located
        self.controlled_squares = []  # Squares controlled by this piece
        self.pinned = False  # Is the piece pinned?
        self.undefended = False  # Is the piece undefended?
        self.contribution_value = 0  # Numeric value of contribution to center control

    def add_controlled_square(self, square):
        if square not in self.controlled_squares:
            self.controlled_squares.append(square)

    def set_pinned(self, pinned_status):
        self.pinned = pinned_status

    def set_undefended(self, undefended_status):
        self.undefended = undefended_status

    def update_contribution(self, value):
        self.contribution_value += value


class CenterControl:
    # Constants for scoring
    OCCUPANCY_SCORE = 1.5
    ATTACK_SCORE = 1
    UNDEFENDED_MULTIPLIER = 0.5
    PINNED_MULTIPLIER = 0.25
    CHECK_PENALTY = -2

    center_squares = [chess.D4, chess.D5, chess.E4, chess.E5]

    def __init__(self, board):
        self.controllers = [[], []]  # 0: black, 1: white
        self.status = None  # Can be None, 'white', or 'black'
        self.score = {chess.WHITE: 0, chess.BLACK: 0}
        self.populate_controllers(board)

    def add_controller(self, piece, square, color):
        controller = Controller(piece, square)
        self.controllers[color].append(controller)

    def populate_controllers(self, board):
        for color in [chess.WHITE, chess.BLACK]:
            if color == board.turn and board.is_check():
                self.score[color] += self.CHECK_PENALTY

            for square in self.center_squares:
                if piece := board.piece_at(square):
                    piece_score = self.OCCUPANCY_SCORE
                    is_pinned = board.is_pinned(color, square)
                    is_undefended = self.undefended(board, color, square)

                    if is_pinned:
                        piece_score *= self.PINNED_MULTIPLIER
                    if is_undefended:
                        piece_score *= self.UNDEFENDED_MULTIPLIER

                    controller = self.find_or_create_controller(piece, square, color)
                    controller.set_pinned(is_pinned)
                    controller.set_undefended(is_undefended)
                    controller.add_controlled_square(square)
                    controller.update_contribution(piece_score)
                    self.score[piece.color] += piece_score

                attackers = board.attackers(color, square)
                for attacker_square in attackers:
                    attacker = board.piece_at(attacker_square)
                    attack_score = self.ATTACK_SCORE
                    is_pinned = board.is_pinned(color, attacker_square)
                    is_undefended = self.undefended(board, color, attacker_square)

                    if is_pinned:
                        attack_score *= self.PINNED_MULTIPLIER
                    if is_undefended:
                        attack_score *= self.UNDEFENDED_MULTIPLIER

                    controller = self.find_or_create_controller(attacker, attacker_square, color)
                    controller.set_pinned(is_pinned)
                    controller.set_undefended(is_undefended)
                    controller.add_controlled_square(square)
                    controller.update_contribution(attack_score)
                    self.score[color] += attack_score

        # Set control status based on score
        if self.score[chess.WHITE] != self.score[chess.BLACK]:
            self.status = chess.COLOR_NAMES[self.score[chess.WHITE] > self.score[chess.BLACK]]

    @staticmethod
    def undefended(board, color, square):
        return not board.is_attacked_by(color, square) and board.is_attacked_by(not color, square)

    def find_or_create_controller(self, piece, square, color):
        existing_controller = next((c for c in self.controllers[color] if c.piece == piece and c.square == square), None)
        if existing_controller:
            return existing_controller
        else:
            self.add_controller(piece, square, color)
            return self.controllers[color][-1]  # Return the newly added controller
