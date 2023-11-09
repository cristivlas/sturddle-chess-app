import json
import logging
import openai
import os
import random

from collections import namedtuple
from enum import Enum
from opening import ECO
from puzzleview import themes_dict as puzzle_themes
from puzzleview import PuzzleCollection
from rapidfuzz import process as fuzz_match


GPT_MODEL = 'gpt-3.5-turbo-1106'

# Testing and debugging.
test_responses = [
    {
        "id": "chatcmpl-8InBWhRs00u8JHINgdoh9E23nf4lY",
        "object": "chat.completion",
        "created": 1699489662,
        "model": "gpt-3.5-turbo-1106",
        "choices": [
        {
            "index": 0,
            "message": {
            "role": "assistant",
            "content": None,
            "function_call": {
                "name": "select_chess_puzzles",
                "arguments": "{\"theme\":\"gambit\"}"
            }
            },
            "finish_reason": "function_call"
        }
        ],
        "usage": {
        "prompt_tokens": 277,
        "completion_tokens": 20,
        "total_tokens": 297
        },
    "system_fingerprint": "fp_eeff13170a"
    }
]

class AppResponse(Enum):
    NONE = 0
    OK = 1
    RETRY = 2
    SELECT = 3
    INVALID = 4


FunctionResult = namedtuple(
    'FunctionCallResult',
    'response context',
    defaults=(AppResponse.NONE, None)
)


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


def create_function_call(response):
    # TODO: more robust parsing?
    if call := response.get('function_call'):
        return FunctionCall(call['name'], call['arguments'])


def get_api_key():
    key = os.environ.get('OPENAI_API_KEY')
    assert key
    return key


_valid_puzzle_themes = { k for k in puzzle_themes }


_opening_description = (
    'A name or a detailed description, preferably including variations.'
)

FUNCTIONS = [
    {
        'name': 'select_chess_puzzles',
        'description': (
            'Select chess puzzle by theme tag.'
            'Theme must be valid.'
            'Puzzles do not include openings nor gambits.'
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


def chat_completion_request(messages, model=GPT_MODEL, *, funcs):
    response = None

    test = os.environ.get('TEST', None)
    if test is not None and int(test) >= 0 and int(test) < len(test_responses):
        # Mock responses for debugging.
        response = test_responses[int(test)]
    else:
        try:
            response = openai.ChatCompletion.create(
                model=model,
                messages=messages,
                functions=funcs,
                temperature=0
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
                logging.debug(reason)
                print(message['content'])

            elif function_call := create_function_call(message):
                result = function_call.execute()

                if not result.context:
                    result = FunctionResult(result.response, f'{message}')

                return function_call.name, result

            return None, FunctionResult()

        except:
            logging.exception('Error processing ChatCompletion response.')

    return None, FunctionResult(AppResponse.RETRY)


__eco = ECO()  # see _lookup_opening below


def _lookup_opening(name, eco, min_confidence=80):
    '''
    Lookup opening in the ECO (Encyclopaedia of Chess Openings).
    '''
    name = name.lower()  # by_name.keys() are lowercase
    if eco:
        # Try looking up by ECO codes first.
        if rows := __eco.by_eco.get(eco, None):
            # The ECO from ChatGPT may be incorrect. Verify by matching the name.
            # Also, there may be multiple matches. Matching by name helps disambiguating.
            rows = {r['name'].lower(): r for r in rows}
            match, score, _ = fuzz_match.extractOne(name, rows.keys())
            logging.debug(f'lookup_opening match={match} score={score}')
            if score >= 90:
                return rows[match]

    match, score, _ = fuzz_match.extractOne(name, __eco.by_name.keys())
    logging.debug(f'lookup_opening name="{name}" match="{match}" score={score}')
    if score >= min_confidence:
        return __eco.by_name[match]


def show_opening(opening):
    name = opening.get('name')

    if eco := opening.get('eco', None):
        eco = eco.lower().split('-')[0]  # TODO: handle ranges.

    print('*************************************************************')
    print(opening)
    if row := _lookup_opening(name, eco):
        print(row['eco'])
        print(row['name'])
        print(row['pgn'])
    print('*************************************************************')


def format_openings(inputs):
    openings = inputs.get('openings', None)
    if not openings:
        return FunctionResult(AppResponse.RETRY)

    if len(openings) == 1:
        show_opening(openings[0])
        return FunctionResult(AppResponse.OK)

    for i, variation in enumerate(openings):
        name = variation['name']
        print(f'{i+1:2d} {name}')

    return FunctionResult(AppResponse.SELECT, f'Choices: {openings}')


def select_opening(inputs):
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

    show_opening(openings[selection])
    return FunctionResult(AppResponse.OK)


def select_puzzles(inputs):
    theme = inputs['theme']
    if theme not in _valid_puzzle_themes:
        return FunctionResult(AppResponse.INVALID)

    puzzles = PuzzleCollection().filter(theme)

    if not puzzles:
        _valid_puzzle_themes.remove(theme)
        return FunctionResult(AppResponse.INVALID)

    logging.debug(f'select_puzzles: {theme}: {len(puzzles)} matches')
    print(random.choice(puzzles))

    return FunctionResult(AppResponse.OK)


def main():
    if os.environ.get('DEBUG'):
        logging.getLogger().setLevel(logging.DEBUG)

    FunctionCall.register('process_chess_openings', format_openings)
    FunctionCall.register('process_user_opening_choice', select_opening)
    FunctionCall.register('select_chess_puzzles', select_puzzles)

    func_name = None  # last executed
    func_result = FunctionResult()
    retry_count = 0

    funcs = FUNCTIONS

    while True:
        context = None

        if func_result.response in (AppResponse.RETRY, AppResponse.INVALID) and retry_count < 3:
            # Modify request and try again.
            retry_count += 1

            if func_result.response == AppResponse.INVALID and func_name:
                # filter out last called function
                logging.debug(f'removing: {func_name}')
                funcs_by_name = {f['name']:f for f in funcs if f['name'] != func_name}
                assert func_name not in funcs_by_name
                funcs = list(funcs_by_name.values())
            else:
                context = func_result.context

        else:
            prompt = input('\nUser input: ')
            if not prompt:
                break

            funcs = FUNCTIONS
            retry_count = 0

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
                'content': prompt
            }
        ]

        if func_result.response == AppResponse.SELECT:
            # Selection requires context.
            assert func_result.context
            context = func_result.context

        if context:
            # Feed context back into the model.
            messages.append({
                'role': 'assistant',
                'content': context
            })

        func_name, func_result = chat_completion_request(messages, funcs=funcs)


if __name__ == '__main__':
    main()
