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
            'Puzzles and chess openings are mutually exclusive. '
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
        'name': 'process_user_opening_choice',
        'description': (
            'Process the user selection from a list of openings,'
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
            'required': ['choice', 'openings']
        }
    },
]


class AppResponse(Enum):
    NONE = 0
    OK = 1
    RETRY = 2
    SELECT = 3
    INVALID = 4


FunctionResult = namedtuple('FunctionCallResult', 'response context', defaults=(AppResponse.NONE, None))


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
        self.temperature = 0.1
        self._app = weakref.proxy(app)
        self._context = None
        self._register_funcs()


    def _completion_request(self, messages, *, functions, timeout):
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
            'temperature': self.temperature
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
            return None, FunctionResult(AppResponse.RETRY)

        except:
            logging.exception('Error generating ChatCompletion response.')

        return None, FunctionResult()


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
                    result = FunctionResult(AppResponse.NONE, f'{message}')

                return function_call.name, result
        except:
            logging.exception('Error handling ChatCompletion response.')

        return None, FunctionResult()


    @staticmethod
    def _create_function_call(response):
        if call := response.get('function_call'):
            return FunctionCall(call['name'], call['arguments'])

    def _process_openings(self, inputs):
        matches = inputs.get('openings', None)
        if not matches:
            return FunctionResult(AppResponse.RETRY)

        if len(matches) == 1:
            self._schedule_action(partial(self._play_selected_opening, matches[0]))
            return FunctionResult(AppResponse.OK)

        # Lookup openings and "normalize" names
        choices = set()
        for opening in matches:
            name = opening['name']
            item = self._lookup_opening(name, opening.get('eco', None))
            if item:
                choices.add(item.name)

        logging.info(f'choices: {choices}')

        if choices:
            prefix = random.choice([
                'Here are some ideas',
                'I would suggest',
                'Some openings to consider include'
            ])
            self._say(f'{prefix}:\n' + '.\n'.join(choices))

        return FunctionResult(AppResponse.SELECT, f'{list(choices)}')


    def _lookup_opening(self, name, eco, confidence=75):
        if self._app.eco:
            result = self._app.eco.name_lookup(name, eco, confidence=90)

            if not result:
                # Classification code returned by model may be wrong, retry without it
                result = self._app.eco.name_lookup(name, eco, confidence=confidence)

            return result


    def _play_selected_opening(self, opening):
        name = opening.get('name')
        eco = opening.get('eco', None)
        self._app.play_opening_sequence(self._lookup_opening(name, eco))


    def _select_opening(self, inputs):
        '''
        Select opening from possible multiple inputs.
        '''
        openings = inputs.get('openings', None)
        if not openings:
            return FunctionResult(AppResponse.RETRY)

        choice = inputs.get('choice', None)
        if choice is None:
            return FunctionResult(AppResponse.RETRY)

        choice = int(choice)
        if choice > 0 and choice <= len(openings):
            selection = choice - 1

        elif len(openings) == 1:
            selection = 0
            if choice != 0 and self._context:
                try:
                    options = ast.literal_eval(self._context)
                    openings = [{'name':options[choice-1]}]  # will raise exc if out of range
                except:
                    pass
        else:
            return FunctionResult(AppResponse.RETRY)

        self._schedule_action(partial(self._play_selected_opening, openings[selection]))
        return FunctionResult(AppResponse.OK)


    def _select_puzzles(self, inputs):
        theme = inputs.get('theme', None)
        if not theme:
            return FunctionResult(AppResponse.INVALID)

        puzzles = PuzzleCollection().filter(theme)

        if not puzzles:
            return FunctionResult(AppResponse.INVALID)

        selection = random.choice(puzzles)

        def play_puzzle():
            self._app.selected_puzzle = selection[3]
            self._app.load_puzzle(selection)

        action = 'practice: ' + strip_punctuation(puzzle_themes.get(theme, theme)).lower()
        self._schedule_action(lambda *_: self._app._new_game_action(action, play_puzzle))
        return FunctionResult(AppResponse.OK)


    def _register_funcs(self):
        FunctionCall.register('process_chess_openings', self._process_openings)
        FunctionCall.register('process_user_opening_choice', self._select_opening)
        FunctionCall.register('select_chess_puzzles', self._select_puzzles)


    def _say(self, text):
        logging.debug(f'say: {text}')
        if text and text[0].isalnum():
            Clock.schedule_once(lambda *_: self._app.speak(text), 0.1)


    def _schedule_action(self, action, *_):
        '''
        Schedule action to run after the voice input interface stops.
        '''
        if self._app.voice_input.is_running():
            Clock.schedule_once(partial(self._schedule_action, action))

        else:
            action()


    def reset_context(self):
        self._context = None


    def run(self, user_input, max_retries=3, timeout=3.0):

        # Testing...
        # return self._select_opening({'choice': 4, 'openings': [{'name': 'St. George Defense'}]})
        # return self._process_openings({'openings':[
        #     {'name': 'St. George Defense'},
        #     {'name': 'Borg Defense'},
        #     {'name': 'Nimzowitsch-Larsen Attack'},
        #     {'name': 'Sodium Attack'}
        # ]})

        # self._context = "['St. George Defense', 'Nimzowitsch-Larsen Attack', 'Sodium Attack']"
        # return self._select_opening({'choice': 2, 'openings': [{'name': 'St. George Defense'}]})

        if not user_input.strip():
            return False  # prevent useless, expensive calls

        funcs = _functions

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
                timeout=timeout
            )
            self._context = func_result.context  # Save the context for next time.

            if func_result.response in (AppResponse.INVALID, AppResponse.RETRY):

                if func_result.response == AppResponse.INVALID:
                    # Remove the function that returned INVALID response from the list.
                    funcs = {f['name']:f for f in funcs if f['name'] != func_name}
                    assert func_name not in funcs
                    funcs = list(funcs.values())

                timeout *= 2

            else:
                return True
