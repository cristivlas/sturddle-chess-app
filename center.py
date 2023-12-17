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
    def __init__(self, piece_type, square):
        self.piece_type = piece_type
        self.square = square  # The square where the piece is located
        self.controlled_squares = []  # Squares controlled by this piece
        self.pinned = False  # Is the piece pinned?
        self.threatened = False  # Is the piece threatened?
        self.value = 0  # Numeric value of contribution to center control

    def add_controlled_square(self, square):
        if square not in self.controlled_squares:
            self.controlled_squares.append(square)

    def update_contribution(self, value):
        self.value += value

    def update_threatened(self, board, color):
        if not self.threatened:
            attacked = False
            attackers = board.attackers(not color, self.square)

            for attacking_square in attackers:
                if board.is_pinned(not color, attacking_square):
                    continue

                if board.piece_type_at(attacking_square) < self.piece_type:
                    self.threatened = True
                    return

                attacked = True

            # Piece is threatened with capture if not defended by pieces of own color.
            self.threatened = attacked and not board.is_attacked_by(color, self.square)


class CenterControl:
    # Constants for scoring
    OCCUPANCY_SCORE = 1
    ATTACK_SCORE = 0.75
    THREATENDED_MULTIPLIER = 0.25
    PINNED_MULTIPLIER = 0.25
    CHECK_PENALTY = -2

    center_squares = [chess.D4, chess.D5, chess.E4, chess.E5]

    def __init__(self, board):
        self.controllers = [[], []]  # 0: black, 1: white
        self.status = None  # Can be None, 'white', or 'black'
        self.score = {chess.WHITE: 0, chess.BLACK: 0}
        self.populate_controllers(board)

    def populate_controllers(self, board):
        for color in [chess.WHITE, chess.BLACK]:
            if color == board.turn and board.is_check():
                self.score[color] += self.CHECK_PENALTY

            for square in self.center_squares:
                if piece := board.piece_at(square):
                    if piece.piece_type == chess.KING:
                        continue  # Exclude kings from analysis.
                    if piece.color == color:
                        controller = self.find_or_create_controller(piece.piece_type, square, color)
                        controller.pinned = board.is_pinned(color, square)
                        controller.update_threatened(board, color)
                        controller.add_controlled_square(square)
                        controller.update_contribution(self.OCCUPANCY_SCORE)

                attackers = board.attackers(color, square)
                for attacker_square in attackers:
                    attacker = board.piece_at(attacker_square)
                    controller = self.find_or_create_controller(attacker.piece_type, attacker_square, color)
                    controller.pinned = board.is_pinned(color, attacker_square)
                    controller.update_threatened(board, color)
                    controller.add_controlled_square(square)
                    controller.update_contribution(self.ATTACK_SCORE)

            for controller in self.controllers[color]:
                if controller.pinned:
                    controller.value *= self.PINNED_MULTIPLIER
                if controller.threatened:
                    controller.value *= self.THREATENDED_MULTIPLIER / (1 + (board.turn != color))
                self.score[color] += controller.value

        # Set control status based on score
        if self.score[chess.WHITE] != self.score[chess.BLACK]:
            self.status = chess.COLOR_NAMES[self.score[chess.WHITE] > self.score[chess.BLACK]]

    def find_or_create_controller(self, piece_type, square, color):
        for c in self.controllers[color]:
            if c.piece_type == piece_type and c.square == square:
                return c

        controller = Controller(piece_type, square)
        self.controllers[color].append(controller)
        return controller
