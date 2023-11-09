import json
import logging
import openai
import os
import random
import weakref

from collections import namedtuple
from enum import Enum
from functools import partial
from kivy.clock import Clock
from puzzleview import themes_dict as puzzle_themes
from puzzleview import PuzzleCollection
from rapidfuzz import process as fuzz_match


_opening_description = 'A name or a detailed description, preferably including variations.'
_valid_puzzle_themes = { k for k in puzzle_themes if PuzzleCollection().filter(k) }

_functions = [
    {
        'name': 'select_chess_puzzles',
        'description': (
            'Select chess puzzle by theme tag.'
            'Theme must be valid.'
        ),
        'parameters': {
            'type': 'object',
            'properties' : {
                'theme': {
                    'type': 'string',
                    'description': 'Theme tag. Must be one of: ' +','.join(_valid_puzzle_themes)
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
                                'description': 'ECO (Encyclopaedia of Chess Openings) code.'
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
                                'description': 'ECO (Encyclopaedia of Chess Openings) code.'
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

        return FunctionResult()

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

    def _completion_request(self, messages, *, functions):
        response = None
        try:
            response = openai.ChatCompletion.create(
                api_key=self._app.get_openai_key(obfuscate=False),
                model=self.model,
                messages=messages,
                functions=functions,
                temperature=self.temperature
            )
            logging.debug(response)

        except openai.error.ServiceUnavailableError as e:
            logging.warn(e)

        except:
            logging.exception('ChatCompletion request failed')

        if response:
            try:
                top = response['choices'][0]
                message = top['message']
                reason = top['finish_reason']

                if reason != 'function_call':
                    self._say(message['content'])

                elif function_call := self._create_function_call(message):
                    result = function_call.execute()

                    if not result:
                        result = FunctionResult(AppResponse.NONE, f'{message}')

                    elif not result.context:
                        result = FunctionResult(result.response, f'{message}')

                    return function_call.name, result

                return None, FunctionResult()

            except:
                logging.exception('Error processing ChatCompletion response.')

        return None, FunctionResult(AppResponse.RETRY)

    @staticmethod
    def _create_function_call(response):
        if call := response.get('function_call'):
            return FunctionCall(call['name'], call['arguments'])

    def _process_openings(self, inputs):
        openings = inputs.get('openings', None)
        if not openings:
            return FunctionResult(AppResponse.RETRY)

        if len(openings) == 1:
            self._play_opening(openings[0])
            return FunctionResult(AppResponse.OK)

        prefix = random.choice([
            'Here are some ideas',
            'I would suggest',
            'Some openings to consider include'
        ])
        self._say(f'{prefix}: ' + ','.join([v['name'] for v in openings]))
        return FunctionResult(AppResponse.SELECT, f'Choices: {openings}')

    def _lookup_opening(self, name, eco, min_confidence=80):
        '''
        Lookup opening in the ECO (Encyclopaedia of Chess Openings).

        '''
        if not self._app.eco:
            return None

        name = name.lower()  # by_name.keys() are lowercase
        if eco:
            # Try looking up by ECO codes first.
            if rows := self._app.eco.by_eco.get(eco, None):
                # The ECO from ChatGPT may be incorrect. Verify by matching the name.
                # Also, there may be multiple matches. Matching by name helps disambiguating.
                rows = {r['name'].lower(): r for r in rows}
                match, score, _ = fuzz_match.extractOne(name, rows.keys())
                logging.debug(f'_lookup_opening: match={match} score={score}')
                if score >= 90:
                    return rows[match]

        match, score, _ = fuzz_match.extractOne(name, self._app.eco.by_name.keys())
        logging.debug(f'_lookup_opening: name="{name}" match="{match}" score={score}')
        if score >= min_confidence:
            return self._app.eco.by_name[match]

    def _play_opening(self, opening):
        name = opening.get('name')
        if eco := opening.get('eco', None):
            # TODO: handle ECO code ranges.
            eco = eco.lower().split('-')[0]

        if row := self._lookup_opening(name, eco):
            Clock.schedule_once(lambda *_: self._app.play_opening(name), 0.1)

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

        if choice > 0 and choice <= len(openings):
            selection = choice - 1
        elif len(openings) == 1:
            selection = 0
        else:
            return FunctionResult(AppResponse.RETRY, 'Invalid selection')

        self._play_opening(openings[selection])
        return FunctionResult(AppResponse.OK)

    def _select_puzzles(self, inputs):
        theme = inputs.get('theme', None)
        if not theme:
             return FunctionResult(AppResponse.NONE)

        puzzles = PuzzleCollection().filter(theme)

        if not puzzles:
            return FunctionResult(AppResponse.INVALID)

        selection = random.choice(puzzles)
        self._app.selected_puzzle = selection[3]  # TODO: FIXME
        self._app.load_puzzle(selection)
        return FunctionResult(AppResponse.OK)

    def _register_funcs(self):
        FunctionCall.register('process_chess_openings', self._process_openings)
        FunctionCall.register('process_user_opening_choice', self._select_opening)
        FunctionCall.register('select_chess_puzzles', self._select_puzzles)

    def _say(self, text):
        logging.info(text)
        Clock.schedule_once(lambda *_: self._app.speak(text), 0.1)

    def run(self, user_input, max_retries=3):
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

            func_name, func_result = self._completion_request(messages, functions=funcs)

            if func_result.response == AppResponse.SELECT:
                self._context = func_result.context  # Save the context for next time.

            if func_result.response in (AppResponse.INVALID, AppResponse.RETRY):

                if func_name and func_result.response == AppResponse.INVALID:
                    # Remove the function that returned INVALID response from the list.
                    funcs = {f['name']:f for f in funcs if f['name'] != func_name}
                    assert func_name not in funcs
                    funcs = list(funcs.values())

                else:
                    self._context = func_result.context

            else:
                return True
