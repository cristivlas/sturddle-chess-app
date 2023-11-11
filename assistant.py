import ast
import json
import logging
import os
import random
import weakref

from collections import namedtuple
from enum import Enum
from functools import partial
from kivy.clock import Clock
from opening import strip_punctuation
from puzzleview import themes_dict as puzzle_themes
from puzzleview import PuzzleCollection


_opening_description = 'A name or a detailed description, preferably including variations.'
_eco_code = 'ECO (Encyclopaedia of Chess Openings) code.'

_valid_puzzle_themes = { k for k in puzzle_themes if PuzzleCollection().filter(k) }

_functions = [
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
                    'description': 'theme'
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
            'Process the user selection from a list of options.'
            'use only when the user message clearly suggests a selection or choice.'
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
        logging.info(f'FunctionCall: {self.name}({self.arguments})')
        if self.name in FunctionCall.dispatch:
            return FunctionCall.dispatch[self.name](self.arguments)

    @staticmethod
    def register(name, func):
        FunctionCall.dispatch[name] = func


class Assistant:
    def __init__(self, app):
        self.model = 'gpt-3.5-turbo-1106'
        self._app = weakref.proxy(app)
        self._context = None  # Optional context to pass as the assistant role content
        self._options = []
        self._register_funcs()


    def _completion_request(self, messages, *, functions, temperature, timeout):
        import requests
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
                'https://api.openai.com/v1/chat/completions',
                headers=headers,
                json=json_data,
                timeout=timeout,
            )
            if response:
                return self._handle_response(json.loads(response.content))

        except requests.exceptions.ReadTimeout as e:
            logging.warn(f'request: {e}')
            return None, FunctionResult(AppLogic.RETRY)

        except:
            logging.exception('Error generating ChatCompletion response.')

        return None, FunctionResult()


    def _format_choices(self, choices):
        '''
        Format choices to be presented to the user.

        choices: a list of [{'name': ..., 'eco': ...}, ... ] dicts; 'eco' is optional.
        '''
        self._options = choices

        if len(choices) == 1:
            choices = choices[0]['name']

        else:
            choices = [c['name'] for c in choices]
            choices = '; '.join([f'{i}. {n}' for i,n in enumerate(choices, start=1)])

        self._context = choices  # save context for future queries
        return choices


    def _handle_response(self, response):
        try:
            logging.debug(f'response: {response}')
            top = response['choices'][0]
            message = top['message']
            reason = top['finish_reason']

            if reason != 'function_call':
                self._say(message['content'])

            elif function_call := self._create_function_call(message):
                result = function_call.execute()
                if not result:
                    result = FunctionResult(AppLogic.NONE, f'{message}')

                return function_call.name, result
        except:
            logging.exception('Error handling ChatCompletion response.')

        return None, FunctionResult()


    @staticmethod
    def _create_function_call(response):
        if call := response.get('function_call'):
            return FunctionCall(call['name'], call['arguments'])


    def _process_openings(self, inputs):
        '''
        Present the user with openings suggestion(s).
        '''
        if openings := self._validate_opening_choices(inputs):
            # "Normalize" the names
            choices = [self._lookup_opening(i['name'], i.get('eco')) for i in openings]

            # Retain name and eco only, unique names.
            choices = {i.name: i.eco for i in choices if i}

            # Convert back to list of dicts.
            choices = [{'name': k, 'eco': v} for k,v in choices.items()]

            if len(choices) == 1:
                # Ask the user if they want to play the opening.
                self._schedule_action(partial(self._play_selected_opening, choices[0]))
                return FunctionResult(AppLogic.OK)

            elif choices:
                self._show_choices(choices, message=random.choice([
                    'Here are some ideas',
                    'I would suggest',
                    'Some openings to consider include'
                ]))
                return FunctionResult(AppLogic.OK)

        return FunctionResult(AppLogic.RETRY)


    def _lookup_opening(self, name, eco, confidence=75):
        if self._app.eco:
            result = self._app.eco.name_lookup(name, eco, confidence=90)

            if not result:
                # Classification code returned by model may be wrong, retry without it.
                result = self._app.eco.name_lookup(name, eco, confidence=confidence)

            return result


    def _play_selected_opening(self, opening):
        name, eco = opening['name'], opening.get('eco')

        if self._app.play_opening_sequence(self._lookup_opening(name, eco)):
            self.reset_context()


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
            self._schedule_action(partial(self._play_selected_opening, selection))

        else:
            self._show_choices(self._options, message='Choice is out of range. Valid options are')

        return FunctionResult(AppLogic.OK)


    def _select_puzzles(self, inputs):
        theme = inputs.get('theme')
        if not theme:
            return FunctionResult(AppLogic.INVALID)

        puzzles = PuzzleCollection().filter(theme)

        if not puzzles:
            return FunctionResult(AppLogic.INVALID)

        selection = random.choice(puzzles)

        def play_puzzle():
            self._app.selected_puzzle = selection[3]
            self._app.load_puzzle(selection)

        action = 'practice: ' + strip_punctuation(puzzle_themes.get(theme, theme)).lower()
        self.reset_context()
        self._context = action
        self._schedule_action(lambda *_: self._app._new_game_action(action, play_puzzle))

        return FunctionResult(AppLogic.OK)


    def _register_funcs(self):
        FunctionCall.register('process_chess_openings', self._process_openings)
        FunctionCall.register('handle_user_choice', self._select_opening)
        FunctionCall.register('select_chess_puzzles', self._select_puzzles)


    def _say(self, text):
        logging.debug(f'say: {text}')
        if text and text[0].isalnum():
            Clock.schedule_once(lambda *_: self._app.speak(text), 0.1)


    def _show_choices(self, choices, *, message):
        text = self._format_choices(choices)

        if message:
            self._say(f'{message}: {text}')

        if len(choices) > 1:
            self._schedule_action(lambda *_: self._app.text_bubble(text))


    def _schedule_action(self, action, *_):
        '''
        Schedule action to run after all modal popups are dismissed.

        '''
        from kivy.core.window import Window
        from kivy.uix.modalview import ModalView

        if isinstance(Window.children[0], ModalView):
            Clock.schedule_once(partial(self._schedule_action, action))

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


    def reset_context(self):
        self._context = None
        self._options = []


    def _run_mock(self):
        # self._options = [
        #     {'name': "Queen's Pawn Game: Anglo-Slav Opening", 'eco': 'A40'},
        #     {'name': "Polish Opening: King's Indian Variation, Sokolsky Attack", 'eco': 'A00'},
        #     {'name': 'Bird Opening', 'eco': 'A02'},
        #     {'name': 'Nimzo-Larsen Attack', 'eco': 'A01'}
        # ]
        # return self._select_opening({'choice': 42})

        return self._process_openings ({
            'openings': [
                {'name': 'Bongcloud Opening'},
                {'name': 'Orangutan Opening'},
                {'name': 'Sokolsky Opening'},
                {'name': "Bird's Opening"},
                {'name': 'Nimzowitsch-Larsen Attack'}
            ]})


    def run(self, user_input, max_retries=3, timeout=3.0):
        # return self._run_mock()  # test and debug

        if not user_input.strip():
            return False  # prevent useless, expensive calls

        funcs = _functions
        temperature = 0

        for retry_count in range(max_retries):
            messages = [
                {
                    'role': 'system',
                    'content': (
                        'You are a chess tutor that assists with openings and puzzles.'
                        'Always respond by making function calls.'
                        'Always respond with JSON that conforms to the function call API.'
                    )
                },
                {
                    'role': 'user',
                    'content': user_input
                }
            ]

            if self._context:  # Pass context back to the model.
                messages.append({
                    'role': 'assistant',
                    'content': self._context
                })

            func_name, func_result = self._completion_request(
                messages,
                functions=funcs,
                temperature=temperature,
                timeout=timeout,
            )

            if func_result.response == AppLogic.CONTEXT:
                self._say('I do not understand the context.')
                user_input = 'Help'

            elif func_result.response == AppLogic.INVALID:
                funcs = remove_func(funcs, func_name)

            elif func_result.response == AppLogic.RETRY:
                timeout *= 2
                temperature += 0.05

            else:
                return True
