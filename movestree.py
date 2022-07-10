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
"""
import weakref
import chess.pgn

class Node:
    def __init__(self, move, comment=None, label=None):
        self.parent = None
        self.move = move
        self.comment = comment.replace('\n', ' ') if comment else comment
        self.label = label
        self.child = None
        self.variations = []

    def add(self, node):
        assert self.move or not self.parent
        if node:
            try:
                self.child = self.variations.index(node)
            except ValueError:
                self.variations.append(node)
                assert node.parent is None
                node.parent = weakref.proxy(self)
                self.child = -1
            return self.variations[self.child]

    def __eq__(self, node):
        return self.move.uci() == node.move.uci()


def _clone(node, label=None):
    new_node = Node(move=node.move, comment=node.comment, label=label)
    for child in node.variations:
        new_node.add(_clone(child, label))
    return new_node


def _select_default(node):
    if node:
        if node.child != None:
            assert node.variations
        return node.child


def _add_variation(game_node, node, label):
    if label is None or node.label == label:
        new_game_node = game_node.add_variation(node.move)
        new_game_node.comment = node.comment
        for child in node.variations:
            _add_variation(new_game_node, child, label)


class MovesTree:
    def __init__(self, select_variation_callback=None, fen=None):
        self.select_callback = select_variation_callback or _select_default
        self.clear()
        self.fen = fen

    def add(self, node):
        self.current = self.current.add(node)
        self.pgn = None

    def add_moves(self, board):
        self.rewind()
        for move in board.move_stack:
            self.add(Node(move))

    def clear(self):
        self.head = self.current = Node(None)
        self.current_comment = None
        self.pgn = None
        self.fen = None

    @property
    def current_move(self):
        return self.current.move if self.current else None

    def next(self):
        child_node_index = self.select_callback(self.current)
        if child_node_index != None:
            return self.current.variations[child_node_index]

    def pop(self):
        move = self.current_move
        if self.current:
            self.current_comment = self.current.comment
        self.current = self.next()
        return move

    def rewind(self):
        self.current = self.head
        if self.current:
            self.current_comment = self.current.comment

    def export_pgn(self):
        if self.pgn is None:
            game = chess.pgn.Game()
            if self.fen:
                game.headers['FEN'] = self.fen

            for node in self.head.variations:
                _add_variation(game, node, self.head.label)

            exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
            self.pgn = game.accept(exporter)
        return self.pgn

    @staticmethod
    def import_pgn(node, label=None, select_variation_callback=None, fen=None):
        tree = MovesTree(select_variation_callback, fen)
        if node:
            tree.current = tree.head = _clone(node, label)
            tree.pop() # make self.current point to the first move
        return tree
