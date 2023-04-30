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
            self._puzzles.append((id, fen, solutions, i))

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
