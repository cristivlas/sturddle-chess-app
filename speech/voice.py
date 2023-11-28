"""
Sturddlefish Chess App (c) 2022, 2023 Cristian Vlasceanu
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

import inspect
import os
import random
import weakref
from functools import partial

from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.logger import Logger
from kivy.metrics import dp
from kivy.properties import *
from kivy.uix.actionbar import ActionButton
from kivy.uix.gridlayout import GridLayout
from kivy.uix.textinput import TextInput

from . import tts
from .nlp import NLP, describe_move
from .stt import stt

import msgbox

_DISABLED_ACTION_ITEM = 'atlas://data/images/defaulttheme/action_item'

class LanguageInput(GridLayout):  # See chessapp.kv
    @property
    def stt_supported(self):
        return stt.is_supported()


class Input:
    '''
    Natural language input box with speech-to-text support.
    If stt not supported, the user can type in the commands.
    '''
    def __init__(self, app):
        self._app = weakref.proxy(app)
        self._ask_mode = False
        self._popup = None
        self._input = None
        self._nlp = NLP()
        self._error = ''
        self._text = ''
        self._results = []  # Voice recognition results.
        self._send = None

        try:
            # play audible feedback when command is understood
            self._ok_sound = SoundLoader.load(os.path.join(os.path.dirname(__file__), 'ok.mp3'))
        except:
            self._ok_sound = None
        if self._ok_sound:
            self._ok_sound.volume = 0.5


    def enter(self, *_):
        assert self._input
        if text := self.get_text_input():
            self._input.ids.text.focus = False  # Hide the virtual keyboard.
            self._process([text])


    def _is_ask_mode(self):
        '''
        Running a confirmation dialog (Yes/No)?
        '''
        popup = self._popup
        return all((
            type(popup) == msgbox.ModalBox,
            popup.content,
            popup.content._buttons,
            popup.content._buttons.children,
            all(btn.text.lower() in ['yes', 'no'] for btn in popup.content._buttons.children)
        ))


    def is_running(self):
        return bool(self._input)


    def start(self, show_dialog=True):
        '''
        Construct the dialog box and start speech-to-text if supported.
        If show_dialog is False, "attach" to the current modal message
        box, so that Yes / No confirmation boxes can be voice-answered.
        '''
        assert not self.is_running()

        self._input = LanguageInput()

        # Stop listening when the user starts typing inside the text input.
        def on_focus(_, focus):
            if focus and stt.is_listening():
                stt.stop()
        self._input.ids.text.bind(focus=on_focus)

        if show_dialog:
            self._app.message_box('', '', self._input, auto_wrap=False)
            popup = self._app.modal.popup

            # Set the position and size of the popup dialog.
            popup.pos_hint={'top': 1.0}
            popup.size_hint=(1, None)
            popup.height = dp(110)

        self._popup = self._app.modal.popup
        self._ask_mode = self._is_ask_mode()

        # Add the microphone button.
        self._listen = ActionButton(
            text='\uF131',
            background_disabled_normal=_DISABLED_ACTION_ITEM,
            disabled=not stt.is_supported(),
            font_name=self._app.font_awesome,
            on_press=self._toggle_listening
        )
        self._popup.ids.title_box.add_widget(self._listen, index=2)
        self._popup.bind(on_dismiss=self._dismiss)

        # In full dialog mode, add a "send" button.
        if show_dialog:
            # Add the send button.
            self._send = ActionButton(
                text='\uF27A',
                background_disabled_normal=_DISABLED_ACTION_ITEM,
                disabled=True,
                font_name=self._app.font_awesome,
                halign='right',
                on_press=self.enter
            )
            popup.ids.title_box.add_widget(self._send, index=-1)

        if stt.is_supported():
            def on_error(msg):
                self._error = f'Error: {msg}'

            stt.results_callback = self._on_results
            stt.error_callback = on_error
            self._start_stt()

        Clock.schedule_interval(self._check_state, 0.05)


    def stop(self):
        if self._popup and not self._ask_mode:
            self._popup.dismiss()
        else:
            self._dismiss()


    def _check_state(self, _):
        if not self._input:
            return  # callback fired after dialog dismissed?

        if stt.is_listening():
            self._listen.text = '\uF130'
            self._input.ids.text.text = self._text
            self._popup.ids.title.text = 'Listening...'
        else:
            self._listen.text = '\uF131'
            self._popup.ids.title.text = self._error

        def callback(*_):
            if self._results:
                last = self._results.pop()
                self._input.ids.text.text = last[0]
                self._parse(last)

        if self._results:
            # Delay parsing to allow for the UI to update.
            Clock.schedule_once(callback, 0.5)

        if self._send:
            self._send.disabled = not self.get_text_input()


    def _dismiss(self, *_):
        '''
        Cleanup when the modal popup is dismissed
        '''
        if self.is_running():
            Clock.unschedule(self._check_state)
            stt.stop()
            tts.stop()
            self._popup = None
            self._input = None
            self._results = []
            self._send = None
            Logger.debug('voice: stopped')


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
        Queue up STT results to be parsed on the main thread.
        '''
        self._results.append(results)


    def _parse(self, results):
        '''
        @mainthread

        Run a batch of results through the language processor.
        Stop listening if the input was handled successfully.

        The user input is processed in three steps:
            - use the NLP grammar and look for move specs;
            - if no move specifications are detected, use the commands grammar ("analyze" etc.)
            - finally, send the input to the ChatGPT-powered Assistant.
        When the assistant is available (API key valid, network connected, etc.), the NLP grammar
        will match strings only from the beginning of the input, otherwise it will search through
        the entire input.
        '''

        # NLP.run takes a fen string parameter instead of a chess.Board;
        # slightly inefficient perhaps but more abstract and standalone testable.
        fen = self._app.engine.board.fen()

        # Use stricter parsing when the Assistant is available.
        parse_from_start = self._app.can_use_assistant()

        moves = self._nlp.run(fen, results, parse_from_start=parse_from_start)

        # if len(moves) > 1 _select_move will ask for disambiguation
        # stop stt so the machine does not listen to its own speech
        stt.stop()

        if self._select_move(list(moves)):
            if self._ok_sound and self.is_running():
                self._ok_sound.play()
            self.stop()
        else:
            self._start_stt()  # keep listening


    def _run_command(self, command, args):
        actions = {
            'analyze': self._app.analyze,
            'backup': self._app.backup,
            'edit': self._app.edit_start,
            'exit': self._app.exit,
            'hints': self._app.hints,
            'new': self._app.new_game,
            'opening': self._app.play_phonetical_match,
            'puzzle': self._app.puzzles,
            'replay': self._app.replay,
            'settings': self._app.settings,
            'switch': self._app.flip_board,
            'variations': self._app.variations,
        }

        if command in actions:
            func = actions[command]
            params = [
                p for p in inspect.signature(func).parameters.values()
                if p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
            ]
            if params:
                if not args:
                    return False
                cmd = lambda *_: func(args)
            else:
                cmd = lambda *_: func()
            Clock.schedule_once(cmd, 0.1)
            return True

        if not self._ask_mode:
            return self._app.chat_assist()

        return False


    def _select_move(self, moves):
        ''' Process moves, handle other (voice) inputs.

        If the list of moves is empty, it means the NLP module has not
        recognized a phrase indicating a move: continue with _run_command,
        which looks for simple commands in the input; if no command is
        recognized, and the chat assistant is available, pass the input to it.

        If there is exactly one move in the moves list, make the move.

        If there are more moves in the list, continue with _multiple_matches
        asking the user to disambiguate.

        Args:
            moves (list): A list of moves that require disambiguation, or empty.

        Returns:
            bool: Returns True if handled (request was resolved).
        '''

        # Handle "ask mode" (answer Yes/No questions) first;
        # in this mode self.stop() does not dismiss the current
        # modal popup (the button action triggered in response
        # to either yes/no answer is expected to dismiss the popup).
        command = self._nlp.command

        if self._ask_mode and command in ['yes', 'no']:
            assert type(self._popup) == msgbox.ModalBox
            for btn in self._popup.content._buttons.children:
                if btn.text == command.capitalize():
                    btn.trigger_action(0.1)
                    break
            return True

        # Cancel "ask mode" if another command or move was given
        if self._nlp.command or moves:
            self._ask_mode = False

        if not moves:
            return self._run_command(self._nlp.command, self._nlp.args)
        elif len(moves) > 1:
            return self._multiple_matches(moves)
        else:
            return self._make_move(moves.pop(0))


    def _make_move(self, move):
        return self._app.on_user_move(self, move.uci()) or self._app.engine.is_game_over()


    def _multiple_matches(self, moves):
        '''
        Called by _select_moves when the move is ambiguous. Request clarification.
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
            + '; '.join([describe_move(b, m, not same_square, spell_digits=True) for m in moves[:-1]])
            + '; or ' + describe_move(b, moves[-1], not same_square, spell_digits=True)
            + '?'
        )
        return False


    def _start_stt(self, *_):
        if self._input and self._input.ids.text.focus:
            Logger.debug('voice: has text input focus, not starting stt')
            return

        if tts.is_speaking():
            Logger.debug('stt: tts busy')
            Clock.schedule_once(self._start_stt, 0.5)

        elif self.is_running():
            self._error = ''
            self._text = ''
            stt.ask_mode = self._ask_mode
            stt.start()
            Logger.debug(f'stt: started (ask_mode={self._ask_mode})')


    def _toggle_listening(self, *_):
        stt.stop() if stt.is_listening() else self._start_stt()


    def get_text_input(self):
        if self._input:
            return self._input.ids.text.text.strip()


    def get_user_input(self):
        return self._nlp.input
