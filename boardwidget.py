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
from functools import partial

import chess
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.graphics import *
from kivy.properties import *
from kivy.metrics import *
from kivy.uix.bubble import Bubble, BubbleButton
from kivy.uix.modalview import ModalView
from kivy.utils import get_color_from_hex, platform

from chesswidget.AtlasChessWidget import AtlasChessWidget

"""
Override chess widget with custom behaviors
"""
class BoardWidget(AtlasChessWidget):

    __events__ = ('on_user_move', 'on_drag', 'on_drag_end', 'on_square',)

    atlas_name = StringProperty('images/pieces')
    board_image = StringProperty('images/board', allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.visible_hints = False
        self._variation_hints = lambda *_: None

        if not kwargs.get('grid_color', None):
            self.grid_color = (0.45, 0.25, 0.25, 0.8)

        self.bubble_view = None
        self._copy = lambda *_: None
        self._paste = lambda *_: None
        self._hint = lambda *_: None
        self.drag = None
        self.enable_variation_hints = True
        self.check_indicator = True
        self.long_press_delay = 0.75
        self.set_textures(atlas=self.atlas_name, board=self.board_image)


    def board_texture(self):
        if self.board_tex is None and self.board:
            self.board_tex = CoreImage(self.board + '-{}.jpg'.format(self.flip)).texture
        return self.board_tex


    def on_drag(self, *_):
        pass


    def on_drag_end(self, *_):
        pass


    def on_long_press(self, touch):
        if not self.bubble_view and not self.drag:
            self.highlight_pos = touch.pos
            self.show_copy_paste_bubble()


    def on_square(self, *_):
        pass


    """ Drag selected piece """
    def on_touch_move(self, touch):
        if square := self._square_name_from_coords(touch.pos):

            if self.drag:
                self.cancel_long_press()
            else:
                self.drag = self.model.piece_at(chess.parse_square(square))
                if self.drag:
                    self.move = square

            if self.drag:
                board = self.model.copy()
                if self.move:
                    board.remove_piece_at(chess.parse_square(self.move))
                self.redraw_pieces(None, board=board)
                xy = [p - self.square_size/2 for p in touch.pos]
                with self.canvas:
                    Color(*self.clear_color)
                    self.redraw_drag_piece(board, self.drag, chess.parse_square(square), xy, 2 * [self.square_size])


    def on_touch_up(self, touch):
        super().on_touch_up(touch)
        if self.inside(touch.pos):
            self.enable_variation_hints = bool(self.move)
        self.redraw(self.last_move)
        self.visible_hints = False
        if self.drag:
            self.dispatch('on_drag_end', touch)
        self.drag = None

        if square := self._square_name_from_coords(touch.pos):
            self.dispatch('on_square', square)


    def highlight_piece_threat(self, piece, square, xy, size, board=None):
        board = board or self.model
        if self.is_check(board, piece, square):
            Ellipse(pos=[x+1 for x in xy], size=[s-2 for s in size], source='images/redblur.png')


    def is_check(self, board, piece, square):
        if self.check_indicator and piece.piece_type == chess.KING and piece.color == self.model.turn:
            return bool(board.attackers_mask(not self.model.turn, square))


    def redraw_drag_piece(self, board, piece, square, xy, size):
        if not self.dispatch('on_drag', piece, square, xy, size) and piece:
            if self.is_check(board, piece, square):
                Ellipse(pos=[x+1 for x in xy], size=[s-2 for s in size], source='images/redblur.png')
            self.redraw_one_piece(piece, square, xy, size)


    def redraw_one_piece(self, piece, square, xy, size):
        if piece:
            self.highlight_piece_threat(piece, square, xy, size)
            super().redraw_one_piece(piece, square, xy, size)


    def redraw_pieces(self, move, board=None, overlay=False, scale=1):
        if board:
            with board._lock:
                self._redraw_pieces(move, board, overlay, scale)
        else:
            with self.model._lock:
                self._redraw_pieces(move, board, overlay, scale)


    def _redraw_pieces(self, move, board=None, overlay=False, scale=1):
        super().redraw_pieces(move, board, overlay, scale)
        if board is None and self.margin > 12:
            self._draw_turn_indicator(self.model)

        if self.enable_variation_hints and not self.drag:
            self._variation_hints(self.model)
            self.canvas.add(self.selection)


    def _draw_turn_indicator(self, board):
        with self.canvas:
            Color(.5,.5,.5,.5)
            xy = [x+self.board_size-self.margin+3 for x in self.board_pos]
            Rectangle(pos=xy, size=2*[self.margin-6])
            Color(1,1,1,1) if board.turn else Color(0,0,0,1)
            xy = [x+self.board_size-self.margin+6 for x in self.board_pos]
            Rectangle(pos=xy, size=2*[self.margin-12])


    def hide_bubble(self, *_):
        if self.bubble_view:
            self.bubble_view.dismiss()


    """
        Show a bubble widget inside of a ModalView;
        for promotion choices, Copy/Paste buttons, game commentary.
    """
    def show_bubble(self, bubble, auto_dismiss=False, on_dismiss=lambda *_:None):
        # avoid showing the bubble during the app's initial size calculation
        if any((i <= 100 for i in self.size)):
            return

        # Do not show the bubble if there's a modal view active
        if isinstance(Window.children[0], ModalView):
            return

        # calculate pos_hint
        x, y = (max(0, min(i-j/2, k-j))/k for i,j,k in zip(self.highlight_pos, bubble.size, self.size))

        def _xarrow_pos():
            r = self.highlight_pos[0] / self.size[0]
            if 0.2 < r < 0.8:
                return '_mid'
            else:
                return '_right' if r >= 0.8 else '_left'

        if bubble.show_arrow:
            bubble.arrow_pos = ('top' if y < 0.5 else 'bottom') + _xarrow_pos()

        def _on_dimiss(*_):
            on_dismiss()
            self.bubble_view = None

        self.bubble_view = ModalView(pos_hint={'x': x, 'y': y}, size_hint=(None, None), size=[i+12 for i in bubble.size])
        self.bubble_view.overlay_color=(0,0,0,0.25)
        self.bubble_view.auto_dismiss = auto_dismiss
        self.bubble_view.on_dismiss = _on_dimiss
        self.bubble_view.background_color = (1, 1, 1, 0.25) # transparent
        self.bubble_view.add_widget(bubble)
        self.bubble_view.open()


    def show_promotion_bubble(self, move, callback):
        piece = self.model.piece_at(move.from_square)
        if piece:
            uci = move.uci()
            self.highlight_move(uci[2:4])
            self._show_promotion_bubble(piece.color, partial(callback, uci))


    def _show_promotion_bubble(self, color, callback):
        fg_color = ['#0c0c0c', '#c0c0c0']
        bg_color = ['#606060', '#0c0c0c']

        self.hide_bubble()

        """ bind to BubbleButton """
        def _select_promotion(piece_type, *_):
            self.hide_bubble()
            callback(piece_type)

        height = self.square_size * 1.1
        bubble = Bubble(size_hint=(None, None), size=(4 * height, height),
            background_color=bg_color[color], background_image='')

        # [chess.KNIGHT, chess.KING)
        for piece_type in range(2, 6):

            text = f'[color={fg_color[color]}]{self.piece_codes[color][piece_type]}[/color]'
            button = BubbleButton(text=text, markup=True, font_name=self.piece_font_name, font_size=sp(32))
            button.on_release = partial(_select_promotion, piece_type)
            bubble.add_widget(button)

        button = BubbleButton(text=self.close_icon_code, font_name=self.piece_font_name, font_size=sp(32))
        bubble.add_widget(button)
        button.on_release = self.hide_bubble

        self.show_bubble(bubble)


    def show_copy_paste_bubble(self):
        _buttons = {
            'Copy': self._copy(),
            'Paste': self._paste(),
            'Hint': self._hint(),
        }
        def _do_action(action, *_):
            self.hide_bubble()
            action()

        actions = [a for a in _buttons if _buttons[a]]
        if actions:
            bubble = Bubble(size_hint=(None, None), size=(sp(90) * len(actions), sp(75)), show_arrow=False)
            for a in actions:
                bubble.add_widget(BubbleButton(text=a, on_release=partial(_do_action, _buttons[a]), font_size=sp(18)))
            self.show_bubble(bubble, auto_dismiss=True)


    def set_piece_codes(self, piece_codes, font_name, close):
        self.piece_codes = piece_codes
        self.piece_font_name = font_name
        self.close_icon_code = close


    def screen_coords_from_move(self, move):
        return self.screen_coords(move.from_square % 8, move.from_square // 8) + \
               self.screen_coords(move.to_square % 8, move.to_square // 8)
