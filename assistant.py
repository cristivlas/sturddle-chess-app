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
import json
import logging
import os
import random
import requests
import weakref

from collections import namedtuple
from enum import Enum
from functools import partial
# from gpt_utils import get_token_count
from kivy.clock import Clock, mainthread
from kivy.logger import Logger
from puzzleview import themes_dict as puzzle_themes
from puzzleview import PuzzleCollection
from transcribe import substitutions

logging.getLogger('urllib3.connectionpool').setLevel(logging.INFO)


'''
Functions.

https://platform.openai.com/docs/guides/function-calling

'''
_description = 'A name or a detailed description, preferably including variations.'
_eco = 'Encyclopedia of Chess Openings'
_valid_puzzle_themes = { k for k in puzzle_themes if PuzzleCollection().filter(k) }

_functions = [
    {
        'name': 'lookup_openings',
        'description': f'This function looks up chess openings by name in the {_eco}',
        'parameters': {
            'type': 'object',
            'properties' : {
                'openings': {
                    'type': 'array',
                    'description': 'The names to look up',
                    'items': {
                        'type': 'string',
                    }
                }
            },
            'required': ['openings']
        }
    },
    {
        'name': 'present_answer',
        'description': 'Present an answer to a question about a chess idea, concept or opening.',
        'parameters': {
            'type': 'object',
            'properties' : {
                'answer': {
                    'type': 'string',
                    'description': 'The answer to a question regarding chess.'
                },
                'topic' : {
                    'type': 'string',
                    'description': 'The topic of the answered question.'
                }
            },
            'required': ['answer', 'topic']
        }
    },
    {
        'name': 'select_chess_puzzles',
        'description': (
            'Select puzzles by theme. Must be called with a valid puzzle theme.'
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
        'name': 'play_chess_opening',
        'description': 'Play an opening move sequence.',
        'parameters': {
            'type': 'object',
            'properties' : {
                'name': {
                    'type': 'string',
                    'description': 'The name of the opening.'
                },
                'eco': {
                    'type': 'string',
                    'description': 'ECO code.'
                },
                'epd': {
                    'type': 'string',
                    'description': 'Extended Position Description',
                },
            },
            'required': ['name', 'eco']
        }
    },
]

_system_prompt = (
    'You are a chess tutor that assists with openings and puzzles. '
    'You are embedded in a chess application, and you: '
    'Always respond by making function calls; '
    # Note: Request MUST contain JSON word for json-mode to work.
    # https://platform.openai.com/docs/guides/text-generation/json-mode
    'always respond with JSON that conforms to the function call API; '
    'always refer to openings and variations by their complete names.'
)


class AppLogic(Enum):
    NONE = 0
    OK = 1
    FUNCTION = 2
    RETRY = 3
    INVALID = 4


FunctionResult = namedtuple('FunctionResult', 'response data', defaults=(AppLogic.NONE, None))


class FunctionCall:
    dispatch = {}

    def __init__(self, name, arguments):
        self.name = name
        self.arguments = json.loads(arguments)

    def execute(self, user_request):
        Logger.info(f'Assistant: FunctionCall={self.name}({self.arguments})')
        if self.name in FunctionCall.dispatch:
            return FunctionCall.dispatch[self.name](user_request, self.arguments)

    @staticmethod
    def register(name, func):
        FunctionCall.dispatch[name] = func


class Query:
    class Kind(Enum):
        NONE = 0
        GENERIC = 1
        FUNCTION_CALL = 2
        OPENING_SELECTION = 3
        PUZZLE_THEME = 4

    _kinds = {
        'generic': Kind.GENERIC,
        'function_call': Kind.FUNCTION_CALL,
        'opening_selection': Kind.OPENING_SELECTION,
        'puzzle_theme': Kind.PUZZLE_THEME,
    }

    def __init__(self, *, kind, request, result):
        self.kind = Query._kinds[kind]
        self.request = request
        self.result = result


def get_token_count(model, messages, functions):
    '''
    Quick-and-dirty workaround for tiktoken.so being broken on Android (bad ELF).
    '''
    msg = json.dumps(messages)
    fun = json.dumps(functions)
    tok = (len(msg) + len(fun)) / 4.5  # approximate characters per token.
    return int(tok)


class Context:
    def __init__(self):
        self.queries = []
        self.current_opening = None


    def system_extra(self, app):
        '''
        Construct a list of additional info to be applied to the system prompt.
        '''
        extra = []

        user_color = ['Black', 'White'][app.engine.opponent]
        extra.append(f'User is playing as {user_color}.')

        extra.append(f'Moves played so far: {app.get_current_play()}')

        return extra


    def messages(self, current_msg, *, app, model, functions, token_limit):
        '''
        Construct a list of messages to be passed to the OpenAI API call.
        '''
        while True:
            msgs = self._construct_messages(
                current_msg,
                app=app,
                model=model,
                functions=functions
            )
            if not self.queries:
                break

            token_count = get_token_count(model, msgs, functions)

            if token_count <= token_limit:
                Logger.debug(f'Assistant: token_count={token_count}')
                break

            self.queries.pop(0)  # remove oldest history entry

        return msgs


    def _construct_messages(self, current_msg, app, model, functions):
        msgs = [{
            'role': 'system',
            'content': _system_prompt + '.'.join(self.system_extra(app))
        }]

        for item in self.queries:
            msgs.append({'role': 'user', 'content': item.request})
            assist = {
                'role': 'assistant',
                'content': None
            }
            if item.kind == Query.Kind.GENERIC:
                assist['content'] = item.result

            elif item.kind == Query.Kind.OPENING_SELECTION:
                assist['content'] = str(item.result)

            elif item.kind == Query.Kind.PUZZLE_THEME:
                assist['content'] = item.result

            elif item.kind == Query.Kind.FUNCTION_CALL:
                call = item.result
                assist['function_call'] = {
                    'name': call.name,
                    'arguments': json.dumps(call.arguments),
                }
            msgs.append(assist)

        msgs.append(current_msg)

        return msgs


    def add_opening(self, opening):
        '''
        Keep track of played openings, for future ideas.
        '''
        if isinstance(opening, dict):
            name, eco = opening['name'], opening['eco']
        else:
            name, eco = opening.name, opening.eco

        if name != self.current_opening:
            self.current_opening = name
            self.queries.append(Query(
                kind='generic',
                request=f'What is the current game?',
                result=json.dumps({'name': name, 'eco': eco})
            ))


    @staticmethod
    def describe_theme(theme):
        ''' Return English description of a puzzle theme.'''
        return puzzle_themes.get(theme, theme).rstrip(',.:')


    def pop_function_call(self):
        for i, q in reversed(list(enumerate(self.queries))):
            if q.kind == Query.Kind.FUNCTION_CALL:
                q = self.queries.pop(i)
                Logger.debug(f'Assistant: pop {i}/{len(self.queries)} {q.result.name}')
                assert q.kind == Query.Kind.FUNCTION_CALL
                break


def remove_func(funcs, func_name):
    '''
    Remove function named func_name from list of function dictionaries.
    '''
    funcs = {f['name']:f for f in funcs if f['name'] != func_name}  # convert to dictionary
    assert func_name not in funcs  # verify that it is removed

    return list(funcs.values())  # convert back to list


class Assistant:
    def __init__(self, app):
        self._app = weakref.proxy(app)
        self._ctxt = Context()
        self._register_funcs()
        self.enabled = True
        self.endpoint = 'https://api.openai.com/v1/chat/completions'
        self.model = 'gpt-3.5-turbo-1106'
        self.retry_count = 3
        self.requests_timeout = 3.0
        self.initial_temperature = 0.01
        self.temperature_increment = 0.01
        self.token_limit = 2048


    def add_opening(self, opening):
        self._ctxt.add_opening(opening)


    def append_history(self, *, kind, request, result):
        self._ctxt.queries.append(Query(kind=kind, request=request, result=result))


    def _completion_request(self, user_request, messages, *, functions, function_call, temperature, timeout):
        response = None
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self._app.get_openai_key(obfuscate=False),
        }

        json_data = {
            'model': self.model,
            'messages': messages,
            'functions': functions,
            'function_call': function_call,
            'temperature': temperature,

            # https://platform.openai.com/docs/guides/text-generation/json-mode
            #'response_format': {'type': 'json_object'},
        }
        try:
            response = requests.post(
                self.endpoint,
                headers=headers,
                json=json_data,
                timeout=timeout,
            )
            if response:
                return self._handle_api_response(user_request, json.loads(response.content))
            else:
                Logger.error(f'Assistant: {json.loads(response.content)}')

        except requests.exceptions.ReadTimeout as e:
            Logger.warning(f'Assistant: _completion_requst failed: {e}')
            return None, FunctionResult(AppLogic.RETRY)

        except:
            Logger.exception('Assistant: Error generating API response.')

        return None, FunctionResult()


    def _handle_api_response(self, user_request, response):
        '''
        Handle response from the OpenAI API call.
        '''
        try:
            Logger.debug(f'Assistant: response={response}')
            top = response['choices'][0]
            message = top['message']
            reason = top['finish_reason']

            if reason != 'function_call':
                return None, self._handle_non_function(user_request, message)

            elif function_call := self._create_function_call(message):
                result = function_call.execute(user_request)

                if not result:
                    result = FunctionResult()

                if result.response == AppLogic.FUNCTION:
                    self.append_history(
                        kind='function_call',
                        request=user_request,
                        result=function_call,
                    )

                return function_call.name, result

        except:
            Logger.exception('Assistant: Error handling API response.')

        return None, FunctionResult()


    def _handle_non_function(self, user_request, message):
        content = message['content']

        for retry in range(3):
            if not content:
                break
            try:
                response = json.loads(content)
                if 'answer' in response:
                    return self._handle_answer(user_request, response)
                else:
                    return FunctionResult(AppLogic.RETRY)

            except json.decoder.JSONDecodeError as e:
                content = content[:e.pos]

        self._respond(message['content'], user_request=user_request)
        return FunctionResult()


    @staticmethod
    def _create_function_call(response):
        if call := response.get('function_call'):
            return FunctionCall(call['name'], call['arguments'])


    def run(self, user_input):
        if not user_input.strip():
            return False  # prevent useless, expensive calls

        funcs = _functions
        temperature = self.initial_temperature
        timeout = self.requests_timeout

        current_message = {
            'role': 'user',
            'content': user_input,
        }

        retry_count = 0
        function_call = 'auto'

        while retry_count < self.retry_count:
            messages = self._ctxt.messages(
                current_message,
                app=self._app,
                model=self.model,
                functions=funcs,
                token_limit=self.token_limit,
            )
            Logger.debug(f'Assistant:\n{json.dumps(messages, indent=2)}')

            # Call the OpenAI API.
            func_name, func_result = self._completion_request(
                user_input,
                messages,
                functions=funcs,
                function_call=function_call,
                temperature=temperature,
                timeout=timeout,
            )

            if func_result.response != AppLogic.FUNCTION:
                self._ctxt.pop_function_call()

            if func_result.response == AppLogic.INVALID:
                funcs = remove_func(funcs, func_name)
                retry_count += 1

            elif func_result.response == AppLogic.RETRY:
                timeout *= 2
                temperature += self.temperature_increment
                retry_count += 1

                if func_result.data:
                    current_message = {
                        'role': 'user',
                        'content': func_result.data
                    }

            elif func_result.response == AppLogic.FUNCTION:
                current_message = {
                    'role': 'function',
                    'name': func_name,
                    'content': json.dumps(func_result.data)
                }
                # function_call = 'none'

            # Crucial to return True on success: prevent endless loops.
            else:
                return True


    # -------------------------------------------------------------------
    #
    # FunctionCall handlers.
    #
    # -------------------------------------------------------------------

    def _handle_answer(self, user_request, inputs):
        if answer := inputs.get('answer'):
            self._respond(answer, inputs.get('topic'), user_request=user_request)
            return FunctionResult(AppLogic.OK)

        return FunctionResult(AppLogic.INVALID)


    def _handle_lookup_openings(self, user_request, inputs):
        requested_openings = inputs.get('openings')
        if not requested_openings:
            return FunctionResult(AppLogic.INVALID)

        results = []
        for name in requested_openings:
            eco_opening = self._lookup_opening({'name': name})
            if not eco_opening:
                Logger.warning(f'Assistant: Not found: {str(inputs)}')
            else:
                result = {
                    'name': eco_opening.name,
                }
                if len(requested_openings) == 1:
                    # include details if looking up a single opening
                    result['eco'] = eco_opening.eco
                    result['epd'] = eco_opening.epd
                    result['pgn'] = eco_opening.pgn

                results.append(result)

        return FunctionResult(AppLogic.FUNCTION, results)


    def _handle_chess_opening(self, user_request, inputs):
        if 'name' not in inputs:
            Logger.error(f'Assistant: {inputs}')
            return FunctionResult(AppLogic.INVALID)

        opening = self._lookup_opening(inputs)

        if not opening:
            Logger.error(f'Assistant: {inputs}')
            return FunctionResult(AppLogic.INVALID)
        else:
            self.append_history(
                kind='opening_selection',
                request=user_request,
                result=inputs
            )
            current = self._app.get_current_play()

            if current.startswith(opening.pgn):
                return FunctionResult(
                    AppLogic.RETRY,
                    (
                        'The opening that you suggested is already in play. '
                        'Suggest an opening with a move sequence not included in: '
                    ) + f'{current}'
                )
            else:
                self._schedule_action(lambda *_: self._app.play_opening(opening))
                return FunctionResult(AppLogic.OK)


    def _handle_puzzle_theme(self, user_request, inputs):
        '''
        Handle the suggestion of a puzzle theme.
        '''
        theme = inputs.get('theme')
        if not theme:
            return FunctionResult(AppLogic.INVALID)

        puzzles = PuzzleCollection().filter(theme)
        if not puzzles:
            return FunctionResult(AppLogic.INVALID)

        def play_puzzle():
            '''
            Choose puzzle at random from the subset that matches the theme, and play it.
            '''
            selection = random.choice(puzzles)
            self._app.selected_puzzle = selection[3]
            self._app.load_puzzle(selection)

            # Add to the history only if the puzzle is actually loaded.
            self.append_history(
                kind='puzzle_theme',
                request=user_request,
                result=theme
            )

        self._schedule_action(
            lambda *_: self._app.new_action(
                'practice: ' + Context.describe_theme(theme),
                play_puzzle
            )
        )
        return FunctionResult(AppLogic.OK)


    def _register_funcs(self):
        FunctionCall.register('present_answer', self._handle_answer)
        FunctionCall.register('play_chess_opening', self._handle_chess_opening)
        FunctionCall.register('select_chess_puzzles', self._handle_puzzle_theme)
        FunctionCall.register('lookup_openings', self._handle_lookup_openings)


    # -------------------------------------------------------------------
    #
    # Miscellaneous helpers.
    #
    # -------------------------------------------------------------------

    def _lookup_opening(self, choice, confidence=90):
        '''
        Lookup opening in the ECO "database".
        '''
        assert self._app.eco

        name = choice['name']
        eco = choice.get('eco')
        result = self._app.eco.name_lookup(name, eco, confidence=confidence)

        if not result:
            result = self._app.eco.phonetical_lookup(name, confidence=75)

        return result


    @mainthread
    def _say(self, text):
        if text and self._app.speak_moves:
            self._app.speak(text)


    def _respond(self, text, topic=None, *, user_request):
        '''
        Respond to a user question with speech and text bubble.
        '''
        text = text.replace('\n', ' ')
        if user_request:
            self.append_history(kind='generic', request=user_request, result=text)

        self._schedule_action(lambda *_: self._app.text_bubble(text))
        self._speak_response(text, topic)


    def _speak_response(self, text, topic):
        pgn = None

        # Substitute PGN snippets with pronounceable descriptions of the moves.
        substs = substitutions(text).items()
        for old, new in substs:
            if not pgn:
                pgn = old  # Hold on to the 1st occurence of a move sequence
            text = text.replace(old, new, 1)

        self._say(text)

        if pgn:
            self._schedule_action(lambda *_: self._app.play_pgn(pgn, topic))


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
