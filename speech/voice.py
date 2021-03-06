"""
Sturddlefish Chess App (c) 2022 Cristian Vlasceanu
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
import os
import random
import weakref
from functools import partial

from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.logger import Logger
from kivy.properties import *
from kivy.uix.actionbar import ActionButton
from kivy.uix.gridlayout import GridLayout
from kivy.uix.textinput import TextInput

from . import tts
from .nlp import NLP, describe_move
from .stt import stt


class LanguageInput(GridLayout):
    @property
    def stt_supported(self):
        return stt.is_supported()


class Input:
    '''
    Natural language input box with speech-to-text support.
    '''
    def __init__(self, app):
        self._app = weakref.proxy(app)
        self._popup = None
        self._input = None
        self._nlp = NLP()
        self._error = ''
        self._text = ''
        self._results = []

        try:
            # play audible feedback when command is understood
            self._ok_sound = SoundLoader.load(os.path.join(os.path.dirname(__file__), 'ok.mp3'))
        except:
            self._ok_sound = None
        if self._ok_sound:
            self._ok_sound.volume = 0.5


    def is_running(self):
        '''
        is the input dialog running?
        '''
        return bool(self._input)


    def start(self):
        '''
        Construct the dialog box and start speech-to-text if supported.
        '''
        self._input = LanguageInput()

        def on_input(text_input):
            if text := text_input.text.strip():
                self._process([text])
        self._input.ids.text.bind(on_text_validate=on_input)

        def on_focus(_, focus):
            if focus and stt.is_listening():
                stt.stop()
        self._input.ids.text.bind(focus=on_focus)

        self._app.message_box('', '', self._input, auto_wrap=False)
        self._popup = self._app.modal.popup
        self._popup.pos_hint={'y': .87}
        self._popup.size_hint=(1, .13)

        # microphone button
        self._listen = ActionButton(
            text='\uF131',
            background_disabled_normal='atlas://data/images/defaulttheme/action_item',
            disabled=not stt.is_supported(),
            font_name=self._app.font_awesome,
            on_press=self._toggle_listening
        )
        self._popup.ids.title_box.add_widget(self._listen, index=2)
        self._popup.bind(on_dismiss=self._dismiss)

        if stt.is_supported():
            def on_error(msg):
                self._error = f'Error: {msg}'

            stt.results_callback = self._on_results
            stt.error_callback = on_error
            self._start_stt()

        Clock.schedule_interval(self._check_state, 0.05)


    def stop(self):
        if self._popup:
            self._popup.dismiss()


    def _check_state(self, _):
        if stt.is_listening():
            self._listen.text = '\uF130'
            self._input.ids.text.text = self._text
            self._popup.ids.title.text = 'Listening...'
        else:
            self._listen.text = '\uF131'
            self._popup.ids.title.text = self._error

        def callback(*_):
            if self._results:
                self._parse(self._results.pop())

        if self._results:
            # Delay parsing to allow for the UI to update.
            Clock.schedule_once(callback, 0.5)


    def _dismiss(self, _):
        '''
        Cleanup when the modal popup is dismissed
        '''
        Clock.unschedule(self._check_state)
        stt.stop()
        tts.stop()
        self._popup = None
        self._input = None
        self._results = []


    def _on_results(self, results, done = True):
        '''
        results: list(str)
        done: False if results are partial, True if recognition complete
        '''
        Logger.debug(f'stt: {results} done={done}')

        # Cannot change the texture of a widget from a non-UI thread, hold on
        # to the text here and set it later in the _check_state timer callback.
        if results:
            self._text = results[-1]

        if done:
            self._process(results)


    def _process(self, results):
        '''
        Queue results for parsing on the main thread.
        '''
        self._results.append(results)


    def _parse(self, results):
        '''
        @mainthread

        Run a batch of results through the language processor.
        Stop input if command was successfully recognized.
        '''
        def on_autocorrect(text):
            if self._input:
                self._text = text
                self._input.ids.text.text = text
            return text

        fen = self._app.engine.board.fen()

        moves = self._nlp.run(fen, results, on_autocorrect=on_autocorrect)

        # if len(moves) > 1 _select_move will ask for disambiguation
        # stop stt so the machine does not listen to its own speech
        stt.stop()

        if self._select_move(list(moves)):
            if self._ok_sound:
                self._ok_sound.play()
            return self.stop()

        self._start_stt()


    def _select_move(self, moves):
        if not moves:
            pass
        elif len(moves) > 1:
            self._multiple_matches(moves)
        else:
            return self._make_move(moves.pop(0))


    def _make_move(self, move):
        if self._app.on_user_move(self, move.uci()):
            return True

        elif self._app.engine.is_game_over():
            if self._app.engine.board.is_checkmate():
                self.stop()
                self._app.speak(random.choice(
                    ['Congratulations', 'Nicely done!', 'Well played']
                ))
        else:
            self._app.speak('The move is incorrect.')

        return False


    def _multiple_matches(self, moves):
        '''
        The move specification is ambiguous, request clarification
        '''
        assert moves

        # Do the moves all share the same from_square?
        same_square = True

        from_square = moves[0].from_square
        for m in moves[1:]:
            if m.from_square != from_square:
                same_square = False
                break

        # Describe the moves. If all share the same from_square,
        # use the piece name, otherwise use the starting square
        b = self._app.engine.board

        self._app.speak(
            'Did you mean: '
            + '; '.join([describe_move(b, m, not same_square) for m in moves[:-1]])
            + '; or ' + describe_move(b, moves[-1], not same_square)
            + '?'
        )


    def _start_stt(self, *_):
        if not self.is_running():
            return

        if tts.is_speaking():
            Logger.debug('stt: tts busy')
            Clock.schedule_once(self._start_stt, 0.5)

        else:
            self._error = ''
            self._text = ''
            stt.start()


    def _toggle_listening(self, *_):
        stt.stop() if stt.is_listening() else self._start_stt()
