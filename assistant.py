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
import io
import itertools
import json
import logging
import os
import random
import requests
import weakref

from collections import namedtuple
from enum import Enum
from functools import partial
from kivy.clock import Clock, mainthread
from kivy.logger import Logger
from puzzleview import themes_dict as puzzle_themes
from puzzleview import PuzzleCollection
from speech.nlp import describe_move

logging.getLogger('urllib3.connectionpool').setLevel(logging.INFO)


_opening_description = 'A name or a detailed description, preferably including variations.'
_eco_code = 'ECO (Encyclopaedia of Chess Openings) code.'

_valid_puzzle_themes = { k for k in puzzle_themes if PuzzleCollection().filter(k) }

_functions = [
    {
        'name': 'explain_concept',
        'description': 'Present the explanation of a chess idea, concept or opening.',
        'parameters': {
            'type': 'object',
            'properties' : {
                'answer': {
                    'type': 'string',
                    'description': 'Answer to a user query regarding an idea in chess.'
                },
            }
        }
    },
    {
        'name': 'select_chess_puzzles',
        'description': (
            'Select puzzles by theme. Must never be called with an invalid theme.'
            'Do not ever use this function in response to queries about openings.'
        ) + 'The complete list of valid themes is: ' + ','.join(_valid_puzzle_themes),
        'parameters': {
            'type': 'object',
            'properties' : {
                'theme': {
                    'type': 'string',
                    'description': 'puzzle theme'
                },
            }
        }
    },
    {
        'name': 'process_chess_openings',
        'description': 'Format a list of openings returned by the model, so they can be presented to the user.',
        'parameters': {
            'type': 'object',
            'properties' : {
                'openings' : {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'name': {
                                'type': 'string',
                                'description': _opening_description,
                            },
                            'eco': {
                                'type': 'string',
                                'description': _eco_code
                            },
                        }
                    }
                }
            },
            'required': ['openings']
        }
    },
    {
        'name': 'handle_user_choice',
        'description': (
            'Process the user selection from a list of options (1-based).'
            'Use only when the user message clearly suggests a selection or choice.'
            'Do not use this function when user message ends with question mark.'
        ),
        'parameters': {
            'type': 'object',
            'properties' : {
                'choice': {
                    'type': 'integer',
                    'description': 'One-based selection index.'
                },
            },
            'required': ['choice']
        }
    },
]


_system_prompt = (
    'You are a chess tutor that assists with openings and puzzles.'
    'Always respond by making function calls.'
    'Always respond with JSON that conforms to the function call API.'
    'Do not include computer source code in your replies.'
    'Do not suggest openings that have been recently looked into, '
    'unless expressly asked to recapitulate or to summarize.'
    'When recommending puzzles, stick with the current theme, unless '
    'a specific theme is requested. Politely refuse to answer queries '
    'outside the scope of chess. Concept explanations must be concise '
    'and avoid move sequence examples.'
)


class AppLogic(Enum):
    NONE = 0
    OK = 1
    RETRY = 2
    INVALID = 3
    CONTEXT = 4


FunctionResult = namedtuple('FunctionCallResult', 'response context', defaults=(AppLogic.NONE, None))


def remove_func(funcs, func_name):
    '''
    Remove function named func_name from list of function dicts.
    '''
    funcs = {f['name']:f for f in funcs if f['name'] != func_name}  # convert to dictionary
    assert func_name not in funcs  # verify it is removed

    return list(funcs.values())  # convert back to list


class FunctionCall:
    dispatch = {}

    def __init__(self, name, arguments):
        self.name = name
        self.arguments = json.loads(arguments)

    def execute(self):
        Logger.info(f'FunctionCall: {self.name}({self.arguments})')
        if self.name in FunctionCall.dispatch:
            return FunctionCall.dispatch[self.name](self.arguments)

    @staticmethod
    def register(name, func):
        FunctionCall.dispatch[name] = func


def format_choices(choices):
    '''
    Format choices to be presented to the user.

    choices: a list of [{'name': ..., 'eco': ...}, ... ] dicts; 'eco' is optional.
    '''

    if len(choices) == 1:
        choices = choices[0]['name']

    else:
        choices = [c['name'] for c in choices]
        choices = '; '.join([f'{i}. {n}' for i,n in enumerate(choices, start=1)])

    return choices


class Context:
    def __init__(self, max_size=1024):
        self.max_size = max_size
        self._options = []
        self._opening_names = []
        self._theme = None
        self._text = None


    def __str__(self):
        s = self.to_string()
        while s and len(s) > self.max_size:
            if self._text:
                self._text = None
            elif self._opening_names:
                self._opening_names.pop(0)
            else:
                self._theme = None
            s = self.to_string()

        return s


    def to_string(self):
        '''
        Construct a message as if coming from the Assistant.
        '''
        ctxt = [self._text]

        if self._options:
            ctxt.append(f'These openings match your previous queries: {format_choices(self._options)}.')

        if self._opening_names:
            openings = ','.join([f'"{n}"' for n in self._opening_names])
            ctxt.append(f'I see that you have studied the following openings, in chronological order: {openings}.')

        if theme := self._theme:
            ctxt.append(f'I see that you practiced puzzles themed: {theme} ({self.describe_theme(theme)}).')

        return '\n'.join([i for i in ctxt if i])


    def add_opening(self, opening):
        if isinstance(opening, dict):
            name = opening['name']
        else:
            name = opening.name
        try:
            self._opening_names.remove(name)
        except ValueError:
            pass

        self._opening_names.append(name)
        self._options.clear()


    def set_puzzle_theme(self, theme):
        self._theme = theme


    @staticmethod
    def describe_theme(theme):
        ''' Return English description of a puzzle theme.'''
        return puzzle_themes.get(theme, theme).rstrip(',.:')


    def set_text(self, text):
        self._text = text

def find_moves(text):
    '''
    Find first PGN snippet that starts with " moves 1. "
    '''
    mark = ' moves 1.'
    start, end = text.find(mark), -1
    if start >= 0:
        i = start + len(mark)
        for n in itertools.count(2):
            mark = f'{n}.'
            j = text.find(mark, i)
            if j < 0:
                break
            i = j + len(mark)
        end = text.find('.', i)
        start += len(' moves ')
    return start, end


def transcribe_moves(text):
    '''
    Replace first PGN snippet of " moves 1. ... " with moves described in English.
    '''
    start, end = find_moves(text)
    if start >= 0:
        moves = []
        game = chess.pgn.read_game(io.StringIO(text[start:end]))
        if game:
            # Iterate through all moves and play them on a board.
            board = game.board()
            for move in game.mainline_moves():
                # Collect move descriptions in English
                moves.append(
                    describe_move(
                        board,
                        move,
                        announce_check=True,
                        announce_capture=True,
                        spell_digits=True
                    ))
                board.push(move)

            # Replace moves with the sequence of verbose descriptions
            old = text[start:end]
            new = ','.join(moves)
            text = text.replace(old, new)

    return text


class Assistant:
    def __init__(self, app):
        self.enabled = True
        self.endpoint = 'https://api.openai.com/v1/chat/completions'
        self.model = 'gpt-3.5-turbo-1106'
        self.retry_count = 3
        self.requests_timeout = 3.0
        self.initial_temperature = 0.01
        self.temperature_increment = 0.01

        self._app = weakref.proxy(app)
        self._ctxt = Context()
        self._register_funcs()


    def add_opening(self, opening):
        self._ctxt.add_opening(opening)


    @property
    def _options(self):
        return self._ctxt._options


    @_options.setter
    def _options(self, options):
        self._ctxt._options = options


    def context(self):
        return str(self._ctxt)


    def _completion_request(self, messages, *, functions, temperature, timeout):
        response = None
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self._app.get_openai_key(obfuscate=False),
        }
        json_data = {
            'model': self.model,
            'messages': messages,
            'functions': functions,
            'temperature': temperature
        }
        try:
            response = requests.post(
                self.endpoint,
                headers=headers,
                json=json_data,
                timeout=timeout,
            )
            if response:
                return self._handle_response(json.loads(response.content))

        except requests.exceptions.ReadTimeout as e:
            Logger.warning(f'request: {e}')
            return None, FunctionResult(AppLogic.RETRY)

        except:
            Logger.exception('Error generating ChatCompletion response.')

        return None, FunctionResult()


    def _handle_response(self, response):
        try:
            Logger.debug(f'response: {response}')
            top = response['choices'][0]
            message = top['message']
            reason = top['finish_reason']

            if reason != 'function_call':
                self._show_text(message['content'])

            elif function_call := self._create_function_call(message):
                result = function_call.execute()
                if not result:
                    result = FunctionResult()

                return function_call.name, result
        except:
            Logger.exception('Error handling ChatCompletion response.')

        return None, FunctionResult()


    @staticmethod
    def _create_function_call(response):
        if call := response.get('function_call'):
            return FunctionCall(call['name'], call['arguments'])


    def _explain_concept(self, inputs):
        answer = inputs.get('answer')
        if not answer:
            return FunctionResult(AppLogic.INVALID)

        # Handle the case of the model repeating back an opening name:
        for choice in self._options:
            if choice['name'] == answer:
                self._play_opening(choice)
                return FunctionResult(AppLogic.OK)

        # This can get very expensive when searching for long strings.
        if len(answer) <= 100:
            choice = {'name': answer}
            opening = self._lookup_opening(choice)
            if opening:
                self._play_opening(choice)
                return FunctionResult(AppLogic.OK)

        # Handle the case of the model repeating back a puzzle theme:
        if answer in puzzle_themes:
            return self._select_puzzles({'theme': answer})

        self._show_text(answer)
        return FunctionResult(AppLogic.OK)


    def _process_openings(self, inputs):
        '''
        Present the user with openings suggestion(s).
        '''
        if openings := self._validate_opening_choices(inputs):

            if False:
                # "Normalize" the names
                choices = [self._lookup_opening(i) for i in openings]

                # Retain name and eco only, unique names.
                choices = {i.name: i.eco for i in choices if i}

            else:
                choices = {i['name']: i.get('eco') for i in openings}

            # Convert back to list of dicts.
            choices = [{'name': k, 'eco': v} for k,v in choices.items()]

            if len(choices) == 1:
                self._play_opening(choices[0])
                return FunctionResult(AppLogic.OK)

            elif choices:
                self._options = choices

                self._show_choices(choices, prefix_msg=random.choice([
                    'Consider these possibilities',
                    'You might find these interesting',
                    'How about these choices',
                    'Take a look at these openings',
                    'Here are some openings to consider',
                    'These might catch your interest',
                    'A few suggestions'
                ]))
                return FunctionResult(AppLogic.OK)

        return FunctionResult(AppLogic.RETRY)


    def _lookup_opening(self, choice, confidence=75):
        if self._app.eco:
            name = choice['name']
            eco = choice.get('eco')
            result = self._app.eco.name_lookup(name, eco, confidence=confidence)

            if not result and eco:
                # Classification code returned by model may be wrong, retry without it.
                result = self._app.eco.name_lookup(name, eco, confidence=confidence)

            return result


    def _play_opening(self, choice):
        self._schedule_action(
            lambda *_: self._app.play_opening(self._lookup_opening(choice))
        )


    def _select_opening(self, inputs):
        '''
        Called in response to the user expressing a choice of openings.

        Expect that contextual state is valid; the model is not assumed to be stateful.
        '''
        if not self._options:
            return FunctionResult(AppLogic.CONTEXT)

        choice = inputs.get('choice')
        if not choice:
            return FunctionResult(AppLogic.RETRY)

        choice = int(choice) - 1  # 1-based

        if choice >= 0 and choice < len(self._options):
            selection = self._options[choice]
            self._play_opening(selection)

        else:
            self._show_choices(
                self._options,
                prefix_msg='Your choice is out of range. Valid options'
            )

        return FunctionResult(AppLogic.OK)


    def _select_puzzles(self, inputs):
        theme = inputs.get('theme')
        if not theme:
            return FunctionResult(AppLogic.INVALID)

        puzzles = PuzzleCollection().filter(theme)

        if not puzzles:
            return FunctionResult(AppLogic.INVALID)

        def play_puzzle():
            ''' Choose a puzzle at random from the subset that matches the theme, and play it. '''
            selection = random.choice(puzzles)
            self._app.selected_puzzle = selection[3]
            self._app.load_puzzle(selection)
            self._ctxt.set_puzzle_theme(theme)

        self._schedule_action(
            lambda *_: self._app.new_action(
                'practice: ' + Context.describe_theme(theme),
                play_puzzle
            )
        )
        return FunctionResult(AppLogic.OK)


    def _register_funcs(self):
        FunctionCall.register('explain_concept', self._explain_concept)
        FunctionCall.register('process_chess_openings', self._process_openings)
        FunctionCall.register('handle_user_choice', self._select_opening)
        FunctionCall.register('select_chess_puzzles', self._select_puzzles)


    @mainthread
    def _say(self, text):
        Logger.debug(f'_say: {text}')
        if text:
            self._app.speak(text)


    def _show_choices(self, choices, *, prefix_msg):
        text = format_choices(choices)

        if prefix_msg:
            self._say(f'{prefix_msg}: {text}')

        if len(choices) > 1:
            self._schedule_action(lambda *_: self._app.text_bubble(text))


    def _show_text(self, text):
        self._ctxt.set_text(text)
        self._say(transcribe_moves(text))
        self._schedule_action(lambda *_: self._app.text_bubble(text))


    def _schedule_action(self, action, *_):
        '''
        Schedule action to run after all modal popups are dismissed.

        '''
        from kivy.core.window import Window
        from kivy.uix.modalview import ModalView

        if self._app.voice_input.is_running():
            self._app.voice_input.stop()

        if isinstance(Window.children[0], ModalView):
            Clock.schedule_once(partial(self._schedule_action, action), 0.1)
        else:
            action()


    @staticmethod
    def _validate_opening_choices(inputs):
        '''
        Expect the inputs to be a list of openings, each having a 'name'.
        '''
        openings = inputs.get('openings', [])
        if any(('name' not in item for item in openings)):
            openings = None
        return openings


    def _run_mock(self):
        # self._options = [
        #     {'name': "Queen's Pawn Game: Anglo-Slav Opening", 'eco': 'A40'},
        #     {'name': "Polish Opening: King's Indian Variation, Sokolsky Attack", 'eco': 'A00'},
        #     {'name': 'Bird Opening', 'eco': 'A02'},
        #     {'name': 'Nimzo-Larsen Attack', 'eco': 'A01'}
        # ]
        # return self._select_opening({'choice': 42})
        ...
        # return self._process_openings({
        #     'openings': [
        #         {'name': 'Bongcloud Opening'},
        #         {'name': 'Englund Gambit', 'eco': 'A40'},
        #         {'name': 'Benko Gambit', 'eco': 'A57'},
        #         {'name': 'Blackburne Shilling Gambit', 'eco': 'C44'},
        #         {'name': 'Latvian Gambit', 'eco': 'C40'}
        #     ]})
        ...
        # return self._explain_concept({'answer': 'Nimzo-Larsen Attack'})
        # return self._explain_concept({'answer': 'underPromotion'})
        # return self._explain_concept({
        #     "answer":
        #     "The Hyperaccelerated Dragon is a variation of the Sicilian Defense that "
        #     "arises after the moves 1.e4 c5 2.Nf3 g6. It is characterized by an early "
        #     "fianchetto of the dark-squared bishop and aims to create an asymmetrical pawn "
        #     "structure. The Hyperaccelerated Dragon allows Black to avoid some of the main "
        #     "lines of the Sicilian Defense and leads to dynamic and unbalanced positions."
        # })
        ...


    def run(self, user_input):
        # return self._run_mock()  # test and debug

        if not user_input.strip():
            return False  # prevent useless, expensive calls

        funcs = _functions
        temperature = self.initial_temperature
        timeout = self.requests_timeout

        for retry_count in range(self.retry_count):
            messages = [
                {
                    'role': 'system',
                    'content': _system_prompt
                },
                {
                    'role': 'user',
                    'content': user_input
                }
            ]

            if context := self.context():  # Pass context back to the model.
                Logger.debug(f'context: {context}')
                messages.append({
                    'role': 'assistant',
                    'content': context
                })

            func_name, func_result = self._completion_request(
                messages,
                functions=funcs,
                temperature=temperature,
                timeout=timeout,
            )

            if func_result.response == AppLogic.CONTEXT:
                self._say('I do not understand the context.')
                user_input = 'help'

            elif func_result.response == AppLogic.INVALID:
                funcs = remove_func(funcs, func_name)

            elif func_result.response == AppLogic.RETRY:
                timeout *= 2
                temperature += self.temperature_increment

            else:
                return True
