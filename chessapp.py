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
from kivy.config import Config

Config.set('graphics', 'resizable', False)
Config.set('graphics', 'multisample', 16)

import math
import re
from collections import defaultdict
from datetime import datetime
from functools import partial
from io import StringIO
from os import path
from time import sleep

import chess.pgn
import sturddle_chess_engine as chess_engine

from kivy.app import App
from kivy.base import ExceptionHandler, ExceptionManager
from kivy.clock import Clock, mainthread
from kivy.core.clipboard import Clipboard
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.effects.scroll import ScrollEffect
from kivy.graphics import *
from kivy.graphics.tesselator import Tesselator
from kivy.logger import Logger
from kivy.metrics import *
from kivy.properties import *
from kivy.storage.dictstore import DictStore
from kivy.uix.actionbar import ActionButton
from kivy.uix.bubble import Bubble
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.dropdown import DropDown
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.utils import get_color_from_hex, platform

from boardwidget import BoardWidget
from engine import BoardModel, Engine
from movestree import MovesTree
from msgbox import MessageBox, ModalBox
from opening import ECO

try:
    from android.runnable import run_on_ui_thread
    from jnius import autoclass

    android_api_version = autoclass('android.os.Build$VERSION')
    AndroidView = autoclass('android.view.View')
    AndroidPythonActivity = autoclass('org.kivy.android.PythonActivity')

    Logger.debug(
        'Application runs on Android, API level {0}'.format(
            android_api_version.SDK_INT
        )
    )
except ImportError:
    def run_on_ui_thread(func):
        def wrapper(*args):
            Logger.debug(f'{func.__name__} called on non android platform')
        return wrapper


def hlink(link):
    return f'[color=2fa7d4][ref={link}[/color]' if link else ''


#############################################################################
CHESS   = 'https://python-chess.readthedocs.io/en/latest/]python-chess'
CODE    = 'https://github.com/cristivlas/sturddle-chess-app]github.com/sturddle-chess-app'
KIVY    = 'https://kivy.org/]Kivy'
ICON    = 'https://www.flaticon.com/free-icons/chess]Chess icon created by Freepik - Flatico'
TITLE   = f'Sturddle Chess  {Engine.version()}'
ABOUT   = f"""Powered by the [b]Sturddle Chess Engine[/b],
{hlink(KIVY)}, and {hlink(CHESS)} {Engine.chess_ver()}.

{hlink(CODE)}
(C) 2022 [i]cristi.vlasceanu@gmail.com[/i]
Sturddlefish image by Alexandra Nicolae

{hlink(ICON)}
"""
#############################################################################

GAME    = 'game'
IMAGE   = 'images/sturddlefish.png'
VIEW_MODE = ' Mode [color=A0A0A0]/[/color][b][color=FFA045] Engine Off[/color][/b]'

WIDTH   = 650
HEIGHT  = 960

# Modified Font Awesome codes for chess pieces
PIECE_CODES = [
    [0, '\uF468', '\uF469', '\uF46A', '\uF46B', '\uF46C', '\uF46D'],
    [0, '\uF470', '\uF471', '\uF472', '\uF473', '\uF474', '\uF475'],
]
COLOR_NAMES = ['Black', 'White']



def is_mobile():
    return platform in ['ios', 'android']


if not is_mobile():
    Config.set('input', 'mouse', 'mouse,multitouch_on_demand')


def bold(text):
    return f'[b]{text}[/b]'


"""
    Draw an arrow on the chess board.
"""
class Arrow:
    def __init__(self, **kwargs):
        from_xy = kwargs.get('from_xy', (0, 0))
        to_xy = kwargs.get('to_xy', (100, 100))
        width = kwargs.get('width', 10)
        head_size = max(1.05 * width, kwargs.get('head_size', 2 * width))
        outline_width = kwargs.get('outline_width', 1)
        color = kwargs.get('color', [0,1,0,1])
        outline_color = kwargs.get('outline_color', [0,0,0,1])

        length = math.dist(from_xy, to_xy)
        points = [-width/4, 0, -width/2, length-head_size, -head_size/2, length-head_size,
                  0, length, head_size/2, length-head_size, width/2, length-head_size, width/4, 0 ]

        tess = Tesselator()
        tess.add_contour(points)
        tess.tesselate()

        PushMatrix()
        Translate(*from_xy)

        angle = -math.degrees(math.atan2(to_xy[0]-from_xy[0], to_xy[1]-from_xy[1]))
        Rotate(angle=angle, origin=(0,0))

        Color(*color)
        for v, i in tess.meshes:
            Mesh(vertices=v, indices=i, mode='triangle_fan')

        Color(*outline_color)
        SmoothLine(points=points, width=outline_width, joint='miter')

        PopMatrix()


class AppSettings(GridLayout):
    pass


class AdvancedSettings(GridLayout):
    pass


class EditControls(GridLayout):
    pass


class FontScalingLabel(Label):
    max_font_size = sp(18)
    auto_wrap = True
    default_background = get_color_from_hex('202020')

    def __init__(self, **kwargs):
        super(FontScalingLabel, self).__init__(**kwargs)
        self.margin = -2, 0
        self.bind(size=self.scale_font)

    def scale_font(self, *_):
        self.font_size = self.max_font_size
        self.texture_update()
        while any([self.texture_size[i] > self.size[i] for i in [0,1]]):
            if self.font_size <= 1:
                break
            self.font_size -= 1
            self.texture_update()


class Menu(DropDown):
    pass


"""
A widget for displaying game transcripts and PGN comments.
"""
class Notepad(TextInput):
    lined = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.lined:
            self.bind(size=self._redraw)
            self.padding[0] = 60
        self.bind(size=self._resize)
        self._height_adjusted = False
        self._update_graphics_ev.cancel()


    def _redraw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.background_color)
            Rectangle(pos=self.pos, size=self.size)
            y = self.y + self.padding[1]
            Color(0,1,1,0.5)
            while y < self.y + self.size[1]:
                Line(points=[self.x, y, self.x + self.size[0], y])
                y += self.line_height + self.line_spacing
            # vertical red lines
            Color(1,0,0,0.7)
            x = self.x + self.padding[0] - 10
            Line(points=[x, self.y, x, self.y + self.size[1]])
            Line(points=[x + 3, self.y, x + 3, self.y + self.size[1]])
            Color(0,0,0,1)


    def _resize(self, *_):
        if 100 < self.height < self.minimum_height:
            self.height = self.minimum_height
            self.size_hint_y = None
        self._height_adjusted = True


    def _update_graphics(self, *args):
        if self._height_adjusted:
            super()._update_graphics(*args)



"""
Widget for selecting the opening book file.
"""
class PolyglotChooser(GridLayout):
    _filechooser = ObjectProperty(None)
    selection = StringProperty('')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.dir = 1

    def dismiss(self):
        self._popup.dismiss()

    def _on_selection(self, _, sel):
        if sel:
            filename = sel[0]
            if len(filename) > 40:
                basename = path.basename(filename)
                filename = filename[:36 - len(basename)] + '.../' + basename
            self._selected.text = 'Current book: ' + filename

    def switch_data_dir(self, btn):
        self.dir ^= 1

        def view_files(path, *_):
            try:
                btn.text = btn._app
                self._filechooser.filter_dirs = False
                self._filechooser.rootpath = path
            except:
                Logger.exception('view_files')

        if self.dir:
            self._filechooser.rootpath = '.'
            self._filechooser.filter_dirs = True
            btn.text = btn._sys
        else:
            if platform == 'android':
                Environment = autoclass('android.os.Environment')
                data_path = Environment.getExternalStorageDirectory().getPath()

                from android.permissions import Permission, request_permissions
                request_permissions(
                    [Permission.READ_EXTERNAL_STORAGE],
                    callback=partial(view_files, data_path))
            else:
                view_files('..')


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
        self._num_pages = self._collection.count // self._page_size
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


class Root(GridLayout):
    pass


class Selection(RelativeLayout):
    selected: BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.puzzle = None


class no_update_callbacks:
    def __init__(self, engine):
        self._engine = engine
        self._update = engine.update_callback
        self._move = None

    def __no_update(self, move):
        # record last move, but don't update the UI
        self._move = move

    def __enter__(self):
        self._engine.update_callback = self.__no_update
        return self

    def __exit__(self, *_):
        # restore update callback
        self._engine.update_callback = self._update

        # ...and perform one single update
        self._update(self._move)


class ChessApp(App):
    icon = 'chess.png'

    # Node-per-second limits by "skill-level"
    NPS_LEVEL = [ 2000, 3000, 4500, 6000, 10000, 15000, 20000, 25000 ]
    FUZZ =      [ 95,   75,   55,   40,   25,    20,    15,    10    ]

    MAX_DIFFICULTY = len(NPS_LEVEL) + 1

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        chess.pgn.LOGGER.setLevel(50)
        self.modal = None
        self.store = DictStore('game.dat')
        self.eco = None
        self.engine = Engine(self.update, self.update_move, Logger.info)
        self.engine.depth_callback = self.update_hash_usage
        self.engine.promotion_callback = self.get_promotion_type
        self.engine.search_callback = self.search_callback

        # wrap engine search
        self._search_move = self.engine.search_move
        self.engine.search_move = self.search_move

        self.use_eco(True)
        self.moves_record = MovesTree()
        self.__study_mode = False
        self.edit = None
        self.puzzle = None
        self.last_puzzle = 0
        self.comments = True # show PGN comments in view mode?

        self._time_limit = [ 1, 3, 5, 10, 15, 30, 60, 180, 300, 600, 900 ]
        self.limit = 1
        self.delay = 0
        self.difficulty_level = 1
        self.nps = 0 # nodes per second
        self.show_nps = False
        self.show_hash = False


    def exit(self, *_):
        self.confirm('Exit application and save game', self.stop)


    def about(self, *_):
        self.message_box(TITLE, ABOUT, Image(source=IMAGE), auto_wrap=False)
        self.modal.popup.size_hint=(.9, .35)
        self.modal.popup.message_max_font_size = sp(14)


    def _auto_open(self):
        """ Play (for both sides) a sequence of moves from the opening book """
        self._opening = self.opening.text
        def callback():
            self.identify_opening()
            if self.opening.text:
                self._opening = self.opening.text

        title = 'Opening Book'
        with no_update_callbacks(self.engine):
            if self.engine.auto_open(callback):
                if self._opening:
                    Clock.schedule_once(lambda *_: self.message_box(title, f'[color=40FFFF][u]{self._opening}[/u][/color]'), 1)
            else:
                # This should not happen, because engine.can_auto_open() should return False when
                # the opening book has no suitable moves for the given position, and the UI button
                # should be disabled -- but just in case...
                Clock.schedule_once(lambda *_: self.message_box(title, 'No suitable moves were found.'), 1)
        self.update_button_states()


    def auto_open(self):
        self.confirm('Lookup matching sequence in the opening book and make moves for both sides', self._auto_open)

    """
    https://stackoverflow.com/questions/43159532/hiding-navigation-bar-on-android
    https://developer.android.com/training/system-ui/immersive
    """
    @run_on_ui_thread
    def _android_hide_menu(self, restore=False):
        if android_api_version.SDK_INT >= 19:
            activity = autoclass('org.kivy.android.PythonActivity').mActivity
            View = autoclass('android.view.View')
            decorView = activity.getWindow().getDecorView()
            flags = View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY \
                    | View.SYSTEM_UI_FLAG_FULLSCREEN \
                    | View.SYSTEM_UI_FLAG_LOW_PROFILE \
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
            decorView.setSystemUiVisibility(flags)


    def build(self):
        Window.bind(on_request_close=self.on_quit)
        Window.bind(on_keyboard=self.on_keyboard)
        Window.bind(on_restore=lambda *_: self._android_hide_menu(True))

        if not is_mobile():
            try:
                import pyautogui
                w, h = pyautogui.size()
                r = 0.85
                Window.size = (WIDTH/HEIGHT * h * r, h * r)
                Window.top = h * (1-r) / 2
            except:
                Window.size = (WIDTH, HEIGHT)

        root = Root()
        for id, widget in root.ids.items():
            setattr(self, id, widget)
        self.board_widget.set_model(self.engine.board)

        # custom fonts and codes for the promotion bubble
        self.board_widget.set_piece_codes(PIECE_CODES, 'fonts/Font Awesome 5 Free Solid.ttf', close='\uF410')

        self.board_widget._copy = self._copy
        self.board_widget._paste = self._paste
        self.board_widget._hint = self._hint
        self.board_widget._variation_hints = self.variation_hints

        self.board_widget.bind(on_user_move=self.on_user_move)
        self.board_widget.bind(on_drag=self.on_drag)
        self.board_widget.bind(on_drag_end=self.on_drag_end)
        self.board_widget.bind(on_square=self.on_square)

        self.build_menu()
        self.load()

        # Position the widgets that show hash usage and nodes-per-seconds
        def on_size(w, *_):
            y = (w.height - w.board_size) / 2
            self.nps_label.y = y - self.nps_label.height - dp(5)
            self.hash_label.y = y - self.hash_label.height - dp(5)

        self.board_widget.bind(size=on_size)

        return root


    def build_menu(self):
        self.menu = Menu()
        for id, widget in self.menu.ids.items():
            setattr(self, id, widget)


    def can_undo(self):
        if self.study_mode:
            return not self.puzzle and bool(self.engine.board.move_stack)
        return self.engine.can_undo()


    def can_redo(self):
        if self.study_mode:
            return not self.puzzle and self.moves_record.current_move
        return self.engine.can_redo()


    def can_restart(self):
        return not self.engine.busy and self.game_in_progress()


    """
    Use ECO categorization to match moves played so far against classic openings
    """
    def identify_opening(self):

        if self.eco is None:
            self.opening.text = ''
        else:
            if opening := self.eco.lookup(self.board_widget.model):
                self.format_opening(opening['name'])
            else:
                self.opening.text = ''


    def format_opening(self, opening_name):
        opening_name = f'[i][ref=https://www.google.com/search?q="{opening_name}"][b]{opening_name}[/b][/ref][/i]'
        self.opening.text = opening_name


    def load_game_study(self, store):
        label = store.get('study_name', None)
        game = chess.pgn.read_game(StringIO(store.get('named_study', '')))
        if game:
            self.moves_record = MovesTree.import_pgn(game, label, fen=game.headers.get('FEN', None))
            self.update_moves_record(last_move=True)


    """
    Load app state (including game in progress, if any)
    """
    def load(self):
        if self.store.exists(GAME):
            store = self.store.get(GAME)
            self.engine.opponent = store.get('play_as', True)
            self.engine.setup(store.get('moves', []), store.get('fen', None))
            if not self.engine.opponent:
                self.board_widget.rotate()

            self.set_study_mode(store.get('study_mode', False))
            self.engine.use_opening_book(store.get('use_opening_book', True))
            self.engine.polyglot_file=store.get('polyglot', self.engine.polyglot_file)
            self.engine.variable_strategy = store.get('var_strategy', True)
            self.use_eco(store.get('use_eco', True))
            self.engine.set_notation(store.get('notation', 'san'))
            self.load_game_study(store)
            self.limit = store.get('limit', self._limit)
            self.engine.depth = store.get('depth', self.engine.depth)
            self.engine.algorithm = store.get('algo', Engine.Algorithm.MTDF)
            self.engine.clear_hash_on_move = store.get('clear_hash', False)
            self.comments = store.get('comments', True)
            self.cpu_cores = store.get('cores', 1)
            self.see = store.get('see', False)

            # Set difficulty after cores, as it resets cores to 1 if level < MAX
            self.set_difficulty_level(int(store.get('level', 1)))

            self.show_hash = store.get('show_hash', False)
            self.show_nps = store.get('show_nps', False)
            self.last_puzzle = store.get('puzzle', 0) # 1-based index


    """
    Save app state
    """
    def save(self, *_):
        self.store.put(GAME,
            fen=self.engine.starting_fen(),
            moves=self.engine.board.move_stack,
            play_as=self.engine.opponent,
            study_mode=self.study_mode,
            study_name=self.moves_record.head.label,
            named_study=self.moves_record.export_pgn(),
            use_opening_book=(self.engine.book != None),
            polyglot=self.engine.polyglot_file,
            var_strategy=self.engine.variable_strategy,
            limit=self.limit,
            depth=self.engine.depth,
            notation=self.engine.notation,
            use_eco=(self.eco != None),
            algo=self.engine.algorithm,
            level=self.difficulty_level,
            comments=self.comments,
            cores=self.cpu_cores,
            see=self.see,
            show_hash=self.show_hash,
            show_nps=self.show_nps,
            clear_hash=self.engine.clear_hash_on_move,
            puzzle=self.last_puzzle
        )

        self.update_button_states()


    def on_keyboard(self, window, keycode1, keycode2, text, modifiers):
        # Ctrl+Z or Android back button
        undo = keycode1 in [27, 1001] if is_mobile() else (keycode1 == 122 and 'ctrl' in modifiers)
        if undo:
            if not self.edit:
                self.board_widget.hide_bubble()
                self.undo_move()
            return True

        if 'ctrl' in modifiers and not self.edit:
            if keycode1 == 99:
                if 'shift' in modifiers:
                    self.copy_fen()
                elif f := self._copy():
                    f()
                return True
            if keycode1 == 118:
                if 'shift' in modifiers:
                    self.paste_fen()
                elif f := self._paste():
                    f()
                return True
            if keycode1 == 121:
                self.redo_move()
                return True

            if keycode1 == 101:
                self.edit_start()
                return True

            # Ctrl+P dump game record for debugging purposes
            if keycode1 == 112:
                title, _ = self.transcribe()
                text = self.moves_record.export_pgn() + f' {{ {self.engine.board.epd()} }}'
                self.text_box(title, text)
                return True

        if keycode1 == 27:
            return True # don't close on Escape


    def on_pause(self):
        return True


    def on_quit(self, *args, **kwargs):
        self.engine.cancel()
        self.engine.stop()


    def on_start(self):
        self._android_hide_menu()
        self.update(self.engine.last_moves()[-1])
        self.engine.start()
        if not self.engine.is_opponents_turn():
            self.engine.make_move()


    def on_resume(self):
        self._android_hide_menu()


    def on_promo(self, move, promo):
        return self.on_user_move(move, move + chess.piece_symbol(promo))


    def on_user_move(self, _, move):
        self._android_hide_menu()

        if self.edit:
            return self.edit_apply(move)

        if not self.study_mode:
            return self.engine.input(move)

        # AI off: puzzle or view mode
        else:
            if self.puzzle:
                move = self.engine.validate_from_uci(move)
                if move:
                    board = chess.Board(fen=self.engine.board.epd())
                    san = board.san_and_push(move)
                    if any((san in self.puzzle[2], move.uci() in self.puzzle[2])):
                        self.message_box(self.puzzle[0], 'Congrats, correct move!')
                        self.modal.popup.content._buttons.size_hint = 1,.35
                        self.modal.popup.content._buttons.add_widget(Button(
                            text='Another Puzzle', font_size=sp(18), on_release=self.puzzles))
                        self.modal.popup.content._buttons.add_widget(Button(
                            text='Play from Here', font_size=sp(18), on_release=
                            lambda *_:self.set_study_mode(self.modal.popup.dismiss())))
                        move = self.engine.apply(move)
                        self.puzzle = None
                    else:
                        def wrong(*_):
                            self.status_label.text = '[b]Try again.[/b]'
                            self.status_label.background = get_color_from_hex('#E44D2E')
                            Clock.schedule_once(lambda *_: self.engine.undo(), 2)

                        self.engine.apply(move)
                        Clock.schedule_once(wrong)
                        move = None
            else:
                move = self.engine.apply(self.engine.validate_from_uci(move))

            if move:
                self.update_moves_record(last_move=True)
                return move


    def on_drag(self, w, piece, square, xy, size):
        assert w == self.board_widget
        assert w.drag
        if self.edit:
            return self.edit_draw_drag(w, piece, square, xy, size)


    def on_drag_end(self, w, touch):
        assert w == self.board_widget
        assert w.drag
        if self.edit and w.move:
            square = chess.parse_square(w.move[-2:])
            if w.inside(touch.pos):
                w.model.set_piece_at(square, w.drag)
                self.update()
            else:
                w.model.remove_piece_at(square)
                self.update()
            w.move = str()


    def on_square(self, w, square):
        assert w == self.board_widget
        if self.edit and not w.move:
            self.edit_toggle_castling_rights(square)


    #
    # Label formatting utils
    #
    def bold_color_text(self, text, turn=None):
        color = ['6BDE23', 'FFA045']
        c_index = self.engine.is_opponents_turn()
        if turn != None:
            opponent = self.engine.opponent
            c_index = opponent != turn
        return f'[color={color[c_index]}]{bold(text)}[/color]'


    def status_turn_color(self, text):
        color = ['ffffff', '000000']
        return f'[color={color[not self.engine.board.turn]}]{bold(text)}[/color]'


    def _status(self):
        """
        Get status text and background, to reflect application state. Called by update_status()
        """
        background = [0.4,0.7,0.6,0.45] if self.study_mode else FontScalingLabel.default_background
        if self.edit:
            return f'Edit Mode ({COLOR_NAMES[self.board_widget.model.turn]} to play)', background

        if self.engine.board.is_checkmate():
            return [self.bold_color_text('Checkmate!'), background]
        if self.engine.board.is_stalemate():
            return ['Stalemate', background]
        if self.engine.board.is_insufficient_material():
            return ['Draw (insufficient pieces to win)', background]

        check = self.bold_color_text('Check! ') if self.engine.board.is_check() else ''
        if self.engine.is_game_over():
            return ['Draw', background]

        if self.study_mode:
            return [check or self.study_title, background]

        background=[[1,0.5,0.1,0.6], [0.6,1,0.5,0.55]][self.engine.board.turn]
        if self.engine.is_opponents_turn():
            return [check + self.status_turn_color('Your turn to move.'), background]

        return [self.status_turn_color(f'{COLOR_NAMES[self.engine.board.turn]} to play'), background]


    """
    Switch sides and rotate the board around.
    """
    def flip_board(self):
        if self.engine.can_switch():
            self.board_widget.rotate()
            self.engine.opponent ^= True
            self.engine.update_last_moves()
            self.update(self.engine.last_moves()[-1])
            if not self.engine.is_opponents_turn():
                self.engine.make_move()


    def update_button_states(self):
        self.new_button.disabled = not self.can_restart()
        self.auto_open_button.disabled = bool(self.edit) or not self.engine.can_auto_open()
        self.undo_button.disabled = bool(self.edit) or not self.can_undo()
        self.redo_button.disabled = bool(self.edit) or not self.can_redo()
        self.switch_button.disabled = bool(self.edit) or not self.engine.can_switch()
        self.share_button.disabled = bool(self.edit) or not self.game_in_progress()
        self.play_button.disabled = bool(self.edit)

        if self.edit:
            self.edit_button.text = 'Exit Editor'
            self.edit_button.on_release = self.edit_quit
            self.edit.ids.apply_and_stop.disabled = not self.edit_has_changes()
        else:
            self.edit_button.text = 'Edit Board'
            self.edit_button.on_release = self.edit_start


    def update_hash_usage(self):
        if self.show_hash:
            self.hash_label.text = f'{self.engine.hashfull / 10:.1f}%'


    @mainthread
    def update(self, move=None, show_comment=True):
        self.engine.bootstrap.set()

        with self.board_widget.model._lock:
            self.update_status()
            self.update_button_states()
            self.update_board(move)
            self.update_captures()
            self.identify_opening()

            if self.edit:
                self.edit_update_castling_rights()
            else:
                self.save()

        # check for engine errors from the worker thread
        if self.engine.error:
            def rethrow(*_):
                raise self.engine.error
            self.message_box('Exception', repr(self.engine.error), on_close=rethrow)

        elif self.study_mode and self.comments and show_comment:
            self.show_comment(self.moves_record.current_comment)


    def update_board(self, move=None):
        selected_square = self.board_widget.move if len(self.board_widget.move)==2 else None
        self.board_widget.update(move)
        if selected_square:
            self.board_widget.highlight_move(selected_square)


    def update_status(self):
        markup, background = self._status()
        assert background
        self.status_label.text, self.status_label.background = markup, background

        if not self.engine.busy:
            self.nps_label.text = ''

            if not self.show_hash:
                self.hash_label.text = ''


    def show_comment(self, comment):
        if comment and 1 < len(comment):
            comment = comment.replace('\n', ' ')
            # condense whitespaces
            comment = re.sub('[ \t]+', ' ', comment)
            comment = comment.strip()
            if comment[0].islower():
                comment = '... ' + comment
            self.text_bubble(comment)


    @mainthread
    def update_move(self, turn, move):
        if move is None:
            self.w_move_label.text = ''
            self.b_move_label.text = ''
        elif not turn:
            self.b_move_label.text = self.markup(move, turn)
        else:
            def move_count():
                n = len(self.engine.board.move_stack)
                return n // 2 + n % 2
            self.w_move_label.text = '[i]{:2d}[/i]. '.format(move_count()) + self.markup(move, turn)
            self.b_move_label.text = ''


    def update_captures(self):
        text_color = ['ffffff', 'c0b0b0']
        opponent = self.engine.opponent
        for color, label in zip([opponent, not opponent], [self.captures_ours, self.captures_theirs]):
            pieces = ''
            for piece_type in sorted(self.board_widget.model._captures[color]):
                pieces += PIECE_CODES[color][piece_type]
            label.text = f'[color={text_color[color]}]{pieces}[/color]'


    def markup(self, move, turn=None):
        if 'x' in move:
            return self.bold_color_text(move, turn)
        else:
            return bold(move)


    def load_pgn(self, pgn, what):
        if game := chess.pgn.read_game(pgn):
            action = f'paste {what} from clipboard'
            self._new_game_action(action, lambda *_: Clock.schedule_once(partial(self._load_pgn, game)))


    def _load_pgn(self, node, *_):
        try:
            fen = node.board().fen()
        except ValueError as e:
            Logger.error(f'load_pgn: {e}')
            return
        self.engine.pause(cancel=True)
        self.start_new_game(auto_move=False)
        self.set_study_mode(True)
        self.engine.set_fen(fen)
        name = self._game_name(node)
        self.moves_record = MovesTree.import_pgn(node, name, fen=fen)
        self.show_comment(node.comment)
        with no_update_callbacks(self.engine):
            while self.moves_record.current_move:
                self.engine.apply(self.moves_record.pop())
        Logger.info(f'load_pgn: {name}')


    def _game_name(self, game):
        white = game.headers.get('White', '?')
        black = game.headers.get('Black', '?')
        if white != '?' and black != '?':
            date = game.headers.get('Date', '?')
            if date[0] == '?':
                date = ''
            else:
                date = ' ' + date.split('.')[0]
            return f'{white} vs {black}{date}'


    def game_in_progress(self):
        return self.engine.board.move_stack or self.engine.starting_fen() != chess.STARTING_FEN


    def _new_game_action(self, text, action):
        if self.game_in_progress() or self.edit:
            if self.edit:
                if self.edit_has_changes():
                    prompt = 'Discard changes'
                else:
                    prompt = 'Quit editor'
            elif self.puzzle:
                prompt = 'Cancel the current puzzle'
            else:
                prompt = 'Abandon the current game'
            self.confirm(f'{prompt} and ' + text, action)
        else:
            action()


    def new_game(self, *_):
        assert self.can_restart()
        self._new_game_action(f'start a new game', self.start_new_game)


    def start_new_game(self, auto_move=True, editing=False):
        if self.edit and not editing:
            self._edit_stop(apply=False)
        self.b_move_label.text, self.w_move_label.text = ('', '')
        self.engine.restart(auto_move=auto_move)
        self.board_widget.cancel_long_press()
        self.board_widget.set_model(self.engine.board)
        self.moves_record.clear()
        # restarting the engine above takes care of making a move for WHITE
        self._set_study_mode(False, auto_move=False)
        self.update_hash_usage()


    def undo_move(self, b=None, long_press_delay=0.35):
        if self.can_undo():
            if self.study_mode:
                # keep rewinding as long as button is pressed
                self._long_press(b, self.undo_move, long_press_delay)
                self.update_moves_record(last_move=False)
                self.engine.board.pop()
                self.engine.update_prev_moves()
                self.update(self.engine.last_moves()[-1], show_comment=False)
            else:
                self.undo_button.disabled = True
                Clock.schedule_once(lambda *_: self.engine.undo())


    def redo_move(self, b=None, long_press_delay=0.35):
        if self.can_redo():
            if self.study_mode:
                # keep forwarding as long as button is pressed
                self._long_press(b, self.redo_move, long_press_delay)
                self.board_widget.enable_variation_hints = True
                self.engine.apply(self.moves_record.pop())
            else:
                self.redo_button.disabled = True
                self.engine.redo()


    def _long_press(self, b, action, delay):
        if b:
            accel = 0.9
            Clock.schedule_once(lambda *_: action(b, delay * accel) if b.state=='down' else None, delay)


    def message_box(self, title, text='', user_widget=None, on_close=lambda _: None, font_size=20, auto_wrap=True):
        def modal_done(on_close):
            if self.modal:
                on_close(self.modal)
            self.modal = None
        if not self.modal:
            self.modal = MessageBox(title, text, user_widget, on_close=lambda *_: modal_done(on_close), auto_wrap=auto_wrap)
            self.modal.font_size = font_size


    @staticmethod
    def _text_view(text, font_size, use_bubble=True, background_color=(1,1,1,1), lined=False):
        """ Helper for text_box and text_bubble """
        text = Notepad(text=text, font_size=font_size, readonly=True, font_name='Roboto-Italic',
                       use_bubble=use_bubble, background_color=background_color, lined=lined)
        view = ScrollView(do_scroll_x=False, do_scroll_y=True, effect_cls=ScrollEffect)
        view.add_widget(text)
        view.bind(on_scroll_start=lambda *_:text._hide_cut_copy_paste())
        return view, text


    def text_box(self, title, text, font_size=20):
        view, text = self._text_view(text, font_size, background_color=(1,1,.65,1), lined=True)
        self.message_box(title=title, text='', user_widget=view, on_close=lambda *_:text._hide_handles())


    def text_bubble(self, text, font_size=20, background_color=(1,1,1,0.5), width=360, max_height=160):
        if not self.board_widget.bubble_view:
            view, text = self._text_view(text, font_size, False, background_color)
            bubble_size = (width, min(max_height, text.minimum_height * 2))
            bubble = Bubble(size_hint=(None, None), show_arrow=False, size=bubble_size)
            bubble.add_widget(view)

            # highlight the starting square, so that the bubble *may* leave the destination visible
            move = self.engine.last_moves()[-1]
            if move:
                self.board_widget.highlight_move(move.uci()[:2])

            self.board_widget.show_bubble(bubble, auto_dismiss=True, on_dismiss=lambda *_:text._hide_handles())


    def confirm(self, text, yes_action, no_action = None):
        def callback(msgbox):
            if msgbox.value == 'Yes':
                return yes_action()
            elif no_action and msgbox.value == 'No':
                return no_action()

        self.message_box(title='Confirm', text=text + '?', on_close=callback)


    def _modal_box(self, title, content, close='\uF057', on_open=lambda *_:None):
        def on_close(*_):
            self.save()
            self.update(self.engine.last_moves()[-1])

        popup = ModalBox(title=title, content=content, size_hint=(0.9, 0.775), on_dismiss=on_close, close_text=close)
        content._popup = popup
        popup.on_open = on_open
        popup.open()
        return popup


    def puzzles(self, *_):
        confirm = True
        if self.modal:
            confirm = False
            self.modal.popup.dismiss()

        def select_puzzle(puzzle):
            self._load_pgn(chess.pgn.read_game(StringIO(f'[FEN "{puzzle[1]}"]')))
            if self.board_widget.model.turn == self.board_widget.flip:
                self.flip_board()
            self.puzzle = puzzle
            self.lsat_puzzle = puzzle[3]
            view._popup.dismiss()

        def confirm_puzzle_selection(puzzle):
            if confirm:
                self._new_game_action('play selected puzzle', partial(select_puzzle, puzzle))
            else:
                select_puzzle(puzzle)

        def on_selection(_, selected):
            if selected:
                self.last_puzzle = selected.puzzle[3]

        view = PuzzleView(index = self.last_puzzle)
        view.play = confirm_puzzle_selection
        view.bind(selection = on_selection)
        self._modal_box('Puzzles', view)


    def cancel_puzzle(self):
        self.puzzle = None


    def settings(self, *_):
        self._modal_box('Settings', AppSettings())


    def advanced_settings(self, *_):
        self._modal_box('Advanced', AdvancedSettings(), close='\uF100')


    def select_opening_book(self, *_):
        def _select_current():
            books.selection = path.abspath(self.engine.polyglot_file)

        books = PolyglotChooser()
        self._modal_box('Select File', books, on_open=_select_current, close='\uF100')


    def set_opening_book(self, file_choser, paths):
        if paths:
            self.engine.polyglot_file = paths[0]
            self.engine.use_opening_book(self.engine.book != None)


    @property
    def study_mode(self):
        return self.__study_mode


    def set_study_mode(self, value, controls=[]):
        """
        Turn off the AI so the user can study
        and go back and forth through the moves.
        """
        if self.__study_mode != value:
            self._set_study_mode(value)

        for widget in controls:
            widget.disabled = not value and not self.engine.is_opponents_turn()


    def _set_study_mode(self, value, auto_move=True):
        self.__study_mode = value
        self.update(self.engine.last_moves()[-1])
        if value:
            self.undo_button.text = ' \uf053 '
            self.redo_button.text = ' \uf054 '
            self.play_button.text = ' \uF204 '
            self.engine.pause(True)
            self.engine.redo_list.clear()
            self.update_moves_record(last_move=True)
        else:
            self.cancel_puzzle()

            # study mode off, turn the engine back on
            self.undo_button.text = ' \uf2ea '
            self.redo_button.text = ' \uf2f9 '
            self.play_button.text = ' \uF205 '
            self.update_redo_list()
            self.engine.resume(auto_move)


    def transcribe(self, headers={}):
        return self.engine.transcript(self.eco, headers)


    def use_eco(self, use):
        """ Use Encyclopedia of Chess Openings to identify opening """
        self.eco = ECO() if use else None
        if getattr(self, 'opening', None):
            self.identify_opening()


    """ Engine callback, prompt the user for promo type """
    def get_promotion_type(self, move):
        self.board_widget.show_promotion_bubble(move, self.on_promo)


    """ Paste PGN string from clipboard """
    def paste(self, *_):
        self.load_pgn(StringIO(Clipboard.paste()), 'game')


    def paste_fen(self, *_):
        if text := Clipboard.paste():
            self.load_pgn(StringIO(f'[FEN "{text}"]'), 'position')


    def validate_clipboard(self):
        if text := Clipboard.paste():
            if game := chess.pgn.read_game(StringIO(text)):
                return game.mainline_moves() or game.headers.get('FEN', None)


    def copy_fen(self):
        Clipboard.copy(self.board_widget.model.epd())


    def _copy(self):
        if not self.edit and self.game_in_progress():
            return lambda *_: Clipboard.copy(self.transcribe()[1])


    def _paste(self):
        if self.validate_clipboard():
            return lambda *_: self.paste()


    def _hint(self):
        if not self.edit:
            hints = []

            if self.puzzle:
                try:
                    board = self.engine.board.copy()
                    hints = [board.parse_san(m) for m in self.puzzle[2]]
                except:
                    pass

            elif self.engine.can_auto_open():
                try:
                    board = self.engine.board.copy()
                    book_entries = self.engine.book.find_all(board)
                    hints = [entry.move for entry in book_entries]
                except:
                    pass

            if hints:
                return partial(self._move_hints, board, hints)


    """
        Draw opening moves hints on the board widget canvas
    """
    def _move_hints(self, board, entries, redraw=True):
        if redraw:
            self.board_widget.redraw()
        self.board_widget.visible_hints = True

        square_size = self.board_widget.square_size
        count_per_target_square = defaultdict(int)
        piece_per_target_square = defaultdict(int)

        # count pieces per target square, for scaling down texture size
        for move in entries:
            if move.promotion:
                continue
            count_per_target_square[move.to_square] += 1

        entries.sort(key=lambda move: chess.square_distance(move.from_square, move.to_square), reverse=True)
        for move in entries:
            if move.promotion:
                continue
            f = count_per_target_square[move.to_square]
            is_capture = board.is_capture(move)
            if is_capture and f==1:
                f += 1
            scale = .75 if f==1 else 1.5/f
            piece_size = 2 * [square_size * scale]

            # keep count of pieces so far per target square
            c = piece_per_target_square[move.to_square]
            piece_per_target_square[move.to_square] += 1

            coords = self.board_widget.screen_coords_from_move(move)
            move.from_xy = [x + square_size / 2 for x in coords[:2]]
            move.to_xy = [x + c * square_size / f - square_size * (scale - 1/f)/2 for x in coords[2:]]

            with self.board_widget.canvas:
                if move.promotion:
                    piece = chess.Piece(move.promotion, board.turn)
                else:
                    piece = board.piece_at(move.from_square)

                if piece:
                    texture = self.board_widget.piece_texture(piece)
                    Color(1, 1, 1, 0.35)
                    Rectangle(pos=move.to_xy, size=piece_size, texture=texture)

                Arrow(
                    from_xy=move.from_xy,
                    to_xy=[x + s / 2 for x, s in zip(move.to_xy, piece_size)],
                    # color=(0.95, 0.25, 0, 0.45) if is_capture else (0.25, 0.75, 0, 0.45),
                    color=(0.25, 0.75, 0, 0.45),
                    width=square_size / 7.5,
                    outline_color=(1, 1, 0.5, 0.75),
                    outline_width=2)

    """
    Engine.search_move wrapper. Set up timer to handle time info and custom draws.
    """
    def search_move(self):
        self.nps = 0
        """
        Show elapsed time and other info.
        """
        @mainthread
        def _timer(*_):
            s = (datetime.now() - start_time).total_seconds()

            if s and self.show_nps:
                nps = self.nps or (self.engine.node_count / s)
                self.nps_label.text = f'{int(nps):10d}'

            s = int(s)
            d = self.engine.current_depth()

            info = f'Thinking... (depth: {d:2d}) {s//60:02d}:{s%60:02d}'
            self.status_label.text = self.status_turn_color(info)
            self.status_label.texture_update()
            if search := self.engine.search:
                self.progress.value = search.eval_depth

        start_time = datetime.now()
        event = Clock.schedule_interval(_timer, 0.1)

        try:
            return self._search_move()
        finally:
            self.progress.value = 0
            event.cancel()
            Clock.schedule_once(lambda *_: self.board_widget.redraw_board())


    """
        Share game transcript in PGN format.
        See https://en.wikipedia.org/wiki/Portable_Game_Notation
    """
    def share(self):
        title, text = self.transcribe()
        if platform == 'android':
            try:
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                Intent = autoclass('android.content.Intent')
                String = autoclass('java.lang.String')
                intent = Intent()
                intent.setAction(Intent.ACTION_SEND)
                intent.putExtra(Intent.EXTRA_TEXT, String(text))
                intent.putExtra(Intent.EXTRA_SUBJECT, String(title))
                intent.setType('text/plain')
                chooser = Intent.createChooser(intent, String('Share ...'))
                PythonActivity.mActivity.startActivity(chooser)
            except Exception as e:
                self.message_box('Exception', repr(e))
        else:
            self.text_box(title, text)


    @property
    def study_title(self):
        label = self.moves_record.current.label if self.moves_record.current else None
        return label or ('Puzzle' if self.puzzle else 'View') + VIEW_MODE


    """
    Update the self.moves_record tree with current moves variation
    """
    def update_moves_record(self, last_move):
        self.moves_record.add_moves(self.engine.board)
        if last_move:
            self.moves_record.pop()


    """
    Populate engine's redo list with moves from the self.moves_record tree
    """
    def update_redo_list(self):
        current = self.moves_record.current

        if current and current.move:
            self.moves_record.rewind()
            self.moves_record.pop()
            synced, prev_move, ply = False, None, 0

            while move := self.moves_record.pop():
                if move.uci() == current.move.uci():
                    synced = True
                    if ply % 2 == self.engine.opponent and self.engine.last_moves()[-1] != move:
                        self.engine.apply(move)

                if synced and ply % 2 != self.engine.opponent:
                    self.engine.redo_list.insert(0, move)
                    self.engine.redo_list.insert(0, prev_move)
                prev_move = move
                ply += 1

            self.moves_record.current = current


    def variation_hints(self, board):
        if self.study_mode and not self.edit:
            node = self.moves_record.current
            if node and node.parent and len(node.parent.variations) > 1:
                self._move_hints(board, [n.move for n in node.parent.variations], False)

    #
    # Board Editing
    #
    def edit_apply(self, move):
        move = chess.Move.from_uci(move)
        board = self.board_widget.model
        if piece := board.piece_at(move.from_square):
            board.set_piece_at(move.to_square, piece)
            board.remove_piece_at(move.from_square)
        self.update()


    def edit_clear(self):
        self.board_widget.model.clear()
        self.update()


    def edit_toggle_castling_rights(self, square):
        square = chess.parse_square(square)
        if square in [chess.A1, chess.A8, chess.H1, chess.H8]:
            board = chess.Board(fen=self.board_widget.model.fen())
            board.castling_rights ^= chess.BB_SQUARES[square]
            board.castling_rights = board.clean_castling_rights()
            if board.is_valid():
                self.board_widget.model.set_fen(board.fen())
            self.edit_update_castling_rights()
            self.edit.ids.apply_and_stop.disabled = not self.edit_has_changes()


    def edit_update_castling_rights(self):
        self.board_widget.redraw_board()

        with self.board_widget.canvas.before:
            board = self.board_widget.model
            for square in chess.scan_forward(board.castling_rights):
                Color(0.75, 1, 0, 0.5)
                xy = self.board_widget.screen_coords(square % 8, square // 8)
                Rectangle(pos=[x+1 for x in xy], size=2 * [self.board_widget.square_size-2])
                Color(1, 1, 1, 1)


    def edit_draw_drag(self, w, piece, square, xy, size):
        assert piece == self.board_widget.drag
        coords = [xy, (xy[0]+size[0]-1, xy[1]+size[1]-1)]
        if any((not self.board_widget.inside(xy) for xy in coords)):
            Rectangle(pos=xy, size=size, source='images/delete.png')
            w.redraw_one_piece(piece, square, xy, [0.65 * i for i in size])
            return True


    def edit_flip_board(self):
        self.flip_board()
        self.update_move(None, None)


    def edit_flip_turn(self):
        self.board_widget.model.turn ^= True
        self.update()


    def edit_has_changes(self):
        assert self.edit
        return self.board_widget.model != self.engine.board


    def edit_start(self):
        if not self.edit:
            self.engine.pause()
            self.hash_label.text = ''
            self.edit = EditControls(pos_hint=(0, None), size_hint=(1, 0.1))
            self.edit.flip = self.board_widget.flip
            self.root.add_widget(self.edit, index=2)
            self.board_widget.set_model(self.board_widget.model.copy())
            self.cancel_puzzle()
            self.update_move(None, None)
            self.update()

            action = 'Touch' if is_mobile() else 'Click'
            self.text_bubble(action + ' corners to modify castling rights.')


    def edit_stop(self, apply=False):
        assert self.edit
        if not self.edit_has_changes():
            self._edit_stop()
        elif apply:
            assert self.edit_has_changes() # ... otherwise the button is disabled
            self.confirm(f'Exit editor and apply changes', partial(self._edit_stop, True))
        else:
            self.confirm(f'Exit editor and discard changes', partial(self._edit_stop, False))


    def _edit_stop(self, apply = False):
        self.modal = None
        if apply:
            fen = self.board_widget.model.epd()
            board = chess.Board(fen=fen)
            status = board.status()
            if status == chess.STATUS_VALID:
                study_mode = self.study_mode
                self.start_new_game(auto_move=False, editing=True)
                self.engine.set_fen(fen)
                self.moves_record = MovesTree(fen=fen)
                self.set_study_mode(study_mode)
            else:
                return self.message_box(str(status), 'The position on the board is not valid.')

        if not apply and self.edit.flip != self.board_widget.flip:
            self.edit_flip_board()

        self.board_widget.set_model(self.engine.board)
        self.root.remove_widget(self.edit)
        self.edit = None
        self.update(self.engine.last_moves()[-1])
        self.engine.update_last_moves()
        if not self.study_mode:
            self.update_hash_usage()
            self.engine.resume()


    def edit_start_drag(self, piece_type, color):
        self.board_widget.move = str()
        self.board_widget.drag = chess.Piece(piece_type, color)


    def edit_quit(self, *_):
        if self.edit_has_changes():
            self.confirm(f'Apply changes to board', partial(self._edit_stop, True), self._edit_stop)
        else:
            self._edit_stop()

    #
    # Settings for the search algorithm
    #
    @property
    def limit(self):
        return self._limit


    @limit.setter
    def limit(self, limit):
        self._limit = max(0, min(limit, self.max_limit))
        self.engine.time_limit = self.time_limit(self._limit)


    @property
    def max_limit(self):
        return len(self._time_limit)-1


    def time_limit(self, limit):
        return self._time_limit[int(limit)]


    """ Display time limit in settings dialog """
    def time_limit_str(self, limit):
        limit = self.time_limit(limit)
        if limit <= 0:
            return 'Unlimited'
        if limit < 60:
            return f'{limit:2d} sec'
        limit //= 60
        return f'{limit:2d} min'


    """
    Dumb down the engine by inserting delays
    """
    def search_callback(self, search, millisec):
        # no delays at MAX_DIFFICULTY
        assert self.difficulty_level < self.MAX_DIFFICULTY

        target_nps = self.NPS_LEVEL[self.difficulty_level-1]
        time_limit = self._time_limit[self._limit] * 1000

        while time_limit > millisec and search.nps > target_nps:
            millisec = search.nanosleep(100000)
            self.nps = search.nps

        self.nps = search.nps


    def set_difficulty_level(self, level, cores_slider=None):
        if self.difficulty_level != level:
            self.difficulty_level = int(level)
            self.delay = 0
            if level >= len(self.FUZZ):
                chess_engine.set_param('EVAL_FUZZ', 0)
            else:
                chess_engine.set_param('EVAL_FUZZ', self.FUZZ[level])

            if level == self.MAX_DIFFICULTY:
                self.engine.search_callback = None
                if cores_slider:
                    cores_slider.disabled = False
            else:
                self.engine.search_callback = self.search_callback
                self.cpu_cores = 1
                if cores_slider:
                    cores_slider.value = 1
                    cores_slider.disabled = True


    @property
    def cpu_cores(self):
        return chess_engine.get_params()['Threads']


    @cpu_cores.setter
    def cpu_cores(self, value):
        chess_engine.set_param('Threads', int(value))


    @property
    def cpu_cores_max(self):
        return chess_engine.get_param_info()['Threads'][2]


    @property
    def see(self):
        return chess_engine.get_params()['SEE']


    @see.setter
    def see(self, see):
        chess_engine.set_param('SEE', int(see))


"""
Workaround for rare, intermittent Builder.sync() crashes.
"""
class __EH(ExceptionHandler):
    def handle_exception(self, inst):
        Logger.exception(f'Exception caught by ExceptionHandler')
        if isinstance(inst, TypeError):
            return ExceptionManager.PASS
        quit()


ExceptionManager.add_handler(__EH())
