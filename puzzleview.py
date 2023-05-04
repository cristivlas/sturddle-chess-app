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
  <string name="advancedPawnDescription">One of your pawns is deep into the opponent position, maybe threatening to promote.</string>
  <string name="advantageDescription">Seize your chance to get a decisive advantage. (200cp ≤ eval ≤ 600cp)</string>
  <string name="anastasiaMateDescription">A knight and rook or queen team up to trap the opposing king between the side of the board and a friendly piece.</string>
  <string name="arabianMateDescription">A knight and a rook team up to trap the opposing king on a corner of the board.</string>
  <string name="attackingF2F7Description">An attack focusing on the f2 or f7 pawn, such as in the fried liver opening.</string>
  <string name="attractionDescription">An exchange or sacrifice encouraging or forcing an opponent piece to a square that allows a follow-up tactic.</string>
  <string name="backRankMateDescription">Checkmate the king on the home rank, when it is trapped there by its own pieces.</string>
  <string name="bishopEndgameDescription">An endgame with only bishops and pawns.</string>
  <string name="bodenMateDescription">Two attacking bishops on criss-crossing diagonals deliver mate to a king obstructed by friendly pieces.</string>
  <string name="castlingDescription">Bring the king to safety, and deploy the rook for attack.</string>
  <string name="capturingDefenderDescription">Removing a piece that is critical to defence of another piece, allowing the now undefended piece to be captured on a following move.</string>
  <string name="doubleBishopMateDescription">Two attacking bishops on adjacent diagonals deliver mate to a king obstructed by friendly pieces.</string>
  <string name="dovetailMateDescription">A queen delivers mate to an adjacent king, whose only two escape squares are obstructed by friendly pieces.</string>
  <string name="equalityDescription">Come back from a losing position, and secure a draw or a balanced position. (eval ≤ 200cp)</string>
  <string name="kingsideAttackDescription">An attack of the opponent's king, after they castled on the king side.</string>
  <string name="clearanceDescription">A move, often with tempo, that clears a square, file or diagonal for a follow-up tactical idea.</string>
  <string name="defensiveMoveDescription">A precise move or sequence of moves that is needed to avoid losing material or another advantage.</string>
  <string name="deflectionDescription">A move that distracts an opponent piece from another duty that it performs, such as guarding a key square. Sometimes also called "overloading".</string>
  <string name="discoveredAttackDescription">Moving a piece (such as a knight), that previously blocked an attack by a long range piece (such as a rook), out of the way of that piece.</string>
  <string name="doubleCheckDescription">Checking with two pieces at once, as a result of a discovered attack where both the moving piece and the unveiled piece attack the opponent's king.</string>
  <string name="enPassantDescription">A tactic involving the en passant rule, where a pawn can capture an opponent pawn that has bypassed it using its initial two-square move.</string>
  <string name="exposedKingDescription">A tactic involving a king with few defenders around it, often leading to checkmate.</string>
  <string name="forkDescription">A move where the moved piece attacks two opponent pieces at once.</string>
  <string name="hangingPieceDescription">A tactic involving an opponent piece being undefended or insufficiently defended and free to capture.</string>
  <string name="hookMateDescription">Checkmate with a rook, knight, and pawn along with one enemy pawn to limit the enemy king's escape.</string>
  <string name="interferenceDescription">Moving a piece between two opponent pieces to leave one or both opponent pieces undefended, such as a knight on a defended square between two rooks.</string>
  <string name="intermezzoDescription">Instead of playing the expected move, first interpose another move posing an immediate threat that the opponent must answer. Also known as "Zwischenzug" or "In between".</string>
  <string name="knightEndgameDescription">An endgame with only knights and pawns.</string>
  <string name="longDescription">Three moves to win.</string>
  <string name="mateDescription">Win the game with style.</string>
  <string name="mateIn1Description">Deliver checkmate in one move.</string>
  <string name="mateIn2Description">Deliver checkmate in two moves.</string>
  <string name="mateIn3Description">Deliver checkmate in three moves.</string>
  <string name="mateIn4Description">Deliver checkmate in four moves.</string>
  <string name="mateIn5Description">Figure out a long mating sequence.</string>
  <string name="oneMoveDescription">A puzzle that is only one move long.</string>
  <string name="pawnEndgameDescription">An endgame with only pawns.</string>
  <string name="pinDescription">A tactic involving pins, where a piece is unable to move without revealing an attack on a higher value piece.</string>
  <string name="promotionDescription">Promote one of your pawn to a queen or minor piece.</string>
  <string name="queenEndgameDescription">An endgame with only queens and pawns.</string>
  <string name="queenRookEndgameDescription">An endgame with only queens, rooks and pawns.</string>
  <string name="queensideAttackDescription">An attack of the opponent's king, after they castled on the queen side.</string>
  <string name="quietMoveDescription">A move that does neither make a check or capture, nor an immediate threat to capture, but does prepare a more hidden unavoidable threat for a later move.</string>
  <string name="rookEndgameDescription">An endgame with only rooks and pawns.</string>
  <string name="sacrificeDescription">A tactic involving giving up material in the short-term, to gain an advantage again after a forced sequence of moves.</string>
  <string name="skewerDescription">A motif involving a high value piece being attacked, moving out the way, and allowing a lower value piece behind it to be captured or attacked, the inverse of a pin.</string>
  <string name="smotheredMateDescription">A checkmate delivered by a knight in which the mated king is unable to move because it is surrounded (or smothered) by its own pieces.</string>
  <string name="superGMDescription">Puzzles from games played by the best players in the world.</string>
  <string name="trappedPieceDescription">A piece is unable to escape capture as it has limited moves.</string>
  <string name="underPromotionDescription">Promotion to a knight, bishop, or rook.</string>
  <string name="veryLongDescription">Four moves or more to win.</string>
  <string name="xRayAttackDescription">A piece attacks or defends a square, through an enemy piece.</string>
  <string name="zugzwangDescription">The opponent is limited in the moves they can make, and all moves worsen their position.</string>
  <string name="healthyMixDescription">A bit of everything. You don't know what to expect, so you remain ready for anything! Just like in real games.</string>
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

