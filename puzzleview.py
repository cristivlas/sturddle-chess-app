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
from kivy.metrics import sp
from kivy.properties import *
from kivy.uix.gridlayout import GridLayout
from kivy.uix.relativelayout import RelativeLayout

from boardwidget import BoardWidget
from engine import BoardModel

import xml.etree.ElementTree as ET

# Based on:
# https://github.com/lichess-org/lila/blob/master/translation/source/puzzleTheme.xml

__xml = '''<?xml version="1.0" encoding="UTF-8"?>
<themes>
<string name="advancedPawnDescription">A pawn deep in enemy territory, possibly promoting soon.</string>
<string name="advantageDescription">Gain a decisive advantage. (200cp ≤ eval ≤ 600cp)</string>
<string name="anastasiaMateDescription">A knight and rook or queen trap the king between the board edge and a friendly piece.</string>
<string name="arabianMateDescription">A knight and rook trap the king in a board corner.</string>
<string name="attackingF2F7Description">Attack targeting f2 or f7 pawn, e.g., in the fried liver opening.</string>
<string name="attractionDescription">Exchange or sacrifice forcing an opponent piece to a vulnerable square.</string>
<string name="backRankMateDescription">Checkmate king on home rank, trapped by its pieces.</string>
<string name="bishopEndgameDescription">Endgame with bishops and pawns only.</string>
<string name="bodenMateDescription">Two bishops on criss-crossing diagonals mate a king blocked by friendly pieces.</string>
<string name="castlingDescription">Secure king and deploy rook for attack.</string>
<string name="capturingDefenderDescription">Remove a defending piece to capture another undefended piece.</string>
<string name="doubleBishopMateDescription">Two bishops on adjacent diagonals mate a king blocked by friendly pieces.</string>
<string name="dovetailMateDescription">Queen mates adjacent king with escape squares blocked by friendly pieces.</string>
<string name="equalityDescription">Recover from losing position, achieve draw or balance. (eval ≤ 200cp)</string>
<string name="kingsideAttackDescription">Attack opponent's king after kingside castling.</string>
<string name="clearanceDescription">Move clearing square, file, or diagonal for a tactical idea.</string>
<string name="defensiveMoveDescription">Move(s) needed to avoid losing material or advantage.</string>
<string name="deflectionDescription">Distract an opponent piece from guarding key square. Aka "overloading".</string>
<string name="discoveredAttackDescription">Unveil attack by moving a blocking piece, like a knight.</string>
<string name="doubleCheckDescription">Check with two pieces after a discovered attack.</string>
<string name="enPassantDescription">Capture an opponent pawn bypassing with en passant rule.</string>
<string name="exposedKingDescription">Tactic with a poorly defended king, often leading to checkmate.</string>
<string name="forkDescription">Move attacking two opponent pieces at once.</string>
<string name="hangingPieceDescription">Tactic with an undefended opponent piece, free to capture.</string>
<string name="hookMateDescription">Checkmate with rook, knight, pawn, and enemy pawn limiting king escape.</string>
<string name="interferenceDescription">Move piece between opponent pieces, leaving one or both undefended.</string>
<string name="intermezzoDescription">Play immediate threat before expected move. Aka "Zwischenzug" or "In between".</string>
<string name="knightEndgameDescription">Endgame with knights and pawns only.</string>
<string name="longDescription">Three moves to win.</string>
<string name="mateDescription">Win with flair.</string>
<string name="mateIn1Description">Checkmate in one move.</string>
<string name="mateIn2Description">Checkmate in two moves.</string>
<string name="mateIn3Description">Checkmate in three moves.</string>
<string name="mateIn4Description">Checkmate in four moves.</string>
<string name="mateIn5Description">Solve a long mating sequence.</string>
<string name="oneMoveDescription">One-move puzzle.</string>
<string name="pawnEndgameDescription">Endgame with only pawns.</string>
<string name="pinDescription">Piece unable to move without exposing higher value piece to attack.</string>
<string name="promotionDescription">Promote a pawn to queen or minor piece.</string>
<string name="queenEndgameDescription">Endgame with queens and pawns only.</string>
<string name="queenRookEndgameDescription">Endgame with queens, rooks, and pawns only.</string>
<string name="queensideAttackDescription">Attack opponent's king after queenside castling.</string>
<string name="quietMoveDescription">Move without check or capture, preparing hidden threat.</string>
<string name="rookEndgameDescription">Endgame with rooks and pawns only.</string>
<string name="sacrificeDescription">Give up material for advantage after forced moves.</string>
<string name="skewerDescription">High value piece attacked, revealing lower value piece behind it. Inverse of pin.</string>
<string name="smotheredMateDescription">Knight checkmates king surrounded by its pieces.</string>
<string name="superGMDescription">Puzzles from top players' games.</string>
<string name="trappedPieceDescription">Piece unable to escape capture due to limited moves.</string>
<string name="underPromotionDescription">Promote to knight, bishop, or rook.</string>
<string name="veryLongDescription">Four or more moves to win.</string>
<string name="xRayAttackDescription">Piece attacks or defends through an enemy piece.</string>
<string name="zugzwangDescription">Opponent's moves worsen their position.</string>
<string name="healthyMixDescription">Varied puzzles. Be ready for anything, like in real games.</string>
</themes>
'''

# Parse the XML file and convert it into a Python dictionary
themes_dict = {}
for child in ET.fromstring(__xml):
    key = child.attrib['name']
    value = child.text
    themes_dict[key] = value


def puzzle_description(themes: str):
    theme_list = themes.split()

    description = ''
    for theme in theme_list:
        key = theme + 'Description'
        if key in themes_dict:
            description += themes_dict[key] + '\n'

    return description.strip()


class PuzzleCollection:
    def __init__(self):
        self._puzzles = []
        from puzzles import puzzles
        self._parse(puzzles)

    def _parse(self, epd):
        i = 0
        for fields in epd.split('\n'):
            if not fields:
                continue # skip empty lines
            fields = fields.split(';')
            tokens = fields[0]
            if ' bm ' in tokens:
                tokens = tokens.split(' bm ')
            elif ' am ' in tokens:
                tokens = tokens.split(' am ')

            fen = tokens[0]
            solutions = tokens[1].strip().split(' ')
            id = None
            for f in fields:
                f = f.strip()
                if f.startswith('id '):
                    id = f.split('id ')[1]
                    break
            i += 1
            self._puzzles.append((id, fen, solutions, i, fields[-1]))

    @property
    def count(self):
        return len(self._puzzles)

    def get(self, start, count):
        return self._puzzles[start : start + count]


class PuzzleView(GridLayout):
    _container = ObjectProperty(None)
    _page_size = NumericProperty(10)
    _board_size = NumericProperty(sp(250))

    selection = ObjectProperty(None, allownone=True)
    prev_page_size = NumericProperty(0)
    next_page_size = NumericProperty(0)
    play = ObjectProperty(lambda *_:None)

    def __init__(self, index=0, **kwargs):
        super().__init__(**kwargs)
        self._collection = PuzzleCollection()
        self._num_pages = (self._collection.count + self._page_size - 1) // self._page_size
        self._page = []
        self._offset = 0

        if index:
            self._offset = ((index-1) // self._page_size) * self._page_size
        self._show_page(self._offset, index)

    def _show_page(self, offset, selection_index=0):
        self.selection = None
        self._page = self._collection.get(offset, self._page_size)
        self.next_page_size = min(self._collection.count - offset - len(self._page), self._page_size)
        self.prev_page_size = min(self._page_size, offset)
        self._offset = offset

        self._container.clear_widgets()

        for puzzle in self._page:
            board_view = BoardWidget(board_image='images/greyboard', grid_color=(0,0,0,0))
            board_view.set_model(BoardModel(fen=puzzle[1]))
            board_view.highlight_area = lambda *_:None  # disable highlights
            board_view.on_touch_move = lambda *_:None   # disable piece dragging
            if not board_view.model.turn:
                board_view.rotate()
            selection = Selection(size_hint=(None, None), size=(self._board_size, self._board_size))
            selection.add_widget(board_view)
            selection.puzzle = puzzle
            selection.bind(on_touch_down=self.on_select)
            if selection_index == puzzle[3]:
                selection.selected = True
                self.selection = selection
            self._container.add_widget(selection)

        page_num = offset // self._page_size + 1
        self._info.text = f'Page {page_num:2d} / {self._num_pages:2d}'
        if self.selection:
            self._scroll.scroll_to(self.selection, animate=False)

    def next_page(self):
        self._show_page(self._offset + self._page_size)

    def prev_page(self):
        self._show_page(self._offset - self._page_size)

    def on_select(self, w, touch):
        if w.collide_point(*touch.pos):
            prev = self.selection
            self.selection = None
            w.selected ^= True
            if w.selected:
                self.selection = w
            if prev and prev != w:
                prev.selected = False


class Selection(RelativeLayout):
    selected: BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.puzzle = None

