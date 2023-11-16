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
from itertools import zip_longest
from gpt_utils import get_token_count
from kivy.clock import Clock, mainthread
from kivy.logger import Logger
from normalize import substitute_chess_moves
from puzzleview import themes_dict as puzzle_themes
from puzzleview import PuzzleCollection

logging.getLogger('urllib3.connectionpool').setLevel(logging.INFO)


_ECO = 'Encyclopedia of Chess Openings'
_valid_puzzle_themes = { k for k in puzzle_themes if PuzzleCollection().filter(k) }

''' Function names. '''
_analyze_position = 'analyze_position'
_get_game_transcript = 'get_PGN'
_lookup_openings = 'lookup_openings'
_play_chess_opening = 'play_chess_opening'
_present_answer = 'present_answer'
_select_chess_puzzles = 'select_chess_puzzles'

''' Schema constants. '''
_arguments = 'arguments'
_array = 'array'
_answer = 'answer'
_content = 'content'
_description = 'description'
_eco = 'eco'
_function = 'function'
_function_call = 'function_call'
_items = 'items'
_object = 'object'
_openings = 'openings'
_role = 'role'
_parameters = 'parameters'
_properties = 'properties'
_required = 'required'
_name = 'name'
_string = 'string'
_system = 'system'
_theme = 'theme'
_topic = 'topic'
_transcript = 'transcript'
_type = 'type'
_user = 'user'

''' Functions.
https://platform.openai.com/docs/guides/function-calling
'''
_FUNCTIONS = [
    {
        _name: _analyze_position,
        _description: 'This function analyzes the current game position.',
        _parameters: {
            _type: _object,
            _properties: {}
        }
    },
    {
        _name: _get_game_transcript,
        _description: (
            'This function returns the PGN transcript of the current game,'
            'which includes information about the opening being played and '
            'the list of moves played so far.'
        ),
        _parameters: {
            _type: _object,
            _properties: {}
        }
    },
    {
        _name: _lookup_openings,
        _description: f'This function looks up chess openings by name in the {_ECO}',
        _parameters: {
            _type: _object,
            _properties : {
                _openings: {
                    _type: _array,
                    _description: 'The names to look up',
                    _items: {
                        _type: _string,
                    }
                }
            },
            _required: [_openings]
        }
    },
    {
        _name: _present_answer,
        _description: 'Present an answer to a question about a chess idea, concept or opening.',
        _parameters: {
            _type: _object,
            _properties : {
                _answer: {
                    _type: _string,
                    _description: 'The answer to a question regarding chess.'
                },
                _topic : {
                    _type: _string,
                    _description: 'The topic of the answered question.'
                }
            },
            _required: [_answer, _topic]
        }
    },
    {
        _name: _select_chess_puzzles,
        _description: (
            'Select puzzles by theme. Must be called with a valid puzzle theme.'
        ) + 'The complete list of valid themes is: ' + ', '.join(_valid_puzzle_themes),
        _parameters: {
            _type: _object,
            _properties : {
                _theme: {
                    _type: _string,
                    _description: 'puzzle theme'
                },
            }
        }
    },
    {
        _name: _play_chess_opening,
        _description: (
            'Play an opening move sequence.'
            'This function should not be used for general game analysis or to predict '
            'game progression but is reserved for specific requests about openings.'
        ),
        _parameters: {
            _type: _object,
            _properties : {
                _name: {
                    _type: _string,
                    _description: 'The name of the opening.'
                },
                _eco: {
                    _type: _string,
                    _description: 'ECO code.'
                },
            },
            _required: [_name, _eco]
        }
    },
]
# print(json.dumps(_FUNCTIONS, indent=4))

_system_prompt = (
    "You are a chess tutor embedded within a chess app, assisting with openings, puzzles, and game analysis. "
    "When providing move recommendations or discussing game positions, always use the 'analyze_position' function. "
    "This function is essential for analyzing the current game state and should be your primary tool for any in-game analysis or move suggestions. "
    "Remember to always refer to the latest 'pgn' transcript provided for the current state of the game. "
    "The 'pgn' data reflects all the recent moves and is crucial for accurate analysis and recommendations. "
    "For questions about specific chess openings or demonstrating opening sequences, use the 'play_chess_opening' function, "
    "but only when the user explicitly requests information about a particular opening by name or ECO code. "
    "When asked to look up chess openings, refer to the 'lookup_openings' function, using complete names as per the Encyclopedia of Chess Openings. "
    "If the conversation involves explaining chess concepts, openings, or responding to specific questions about chess ideas, "
    "use the 'present_answer' function, ensuring that your response is aligned with the query's topic. "
    "For selecting chess puzzles, the 'select_chess_puzzles' function should be used, focusing on the theme specified by the user. "
    "Remember, do not suggest moves or game progressions without consulting the 'analyze_position' function to maintain accuracy and relevance."
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
        _function_call: Kind.FUNCTION_CALL,
        'opening_selection': Kind.OPENING_SELECTION,
        'puzzle_theme': Kind.PUZZLE_THEME,
    }

    def __init__(self, *, kind, request, result):
        self.kind = Query._kinds[kind]
        self.request = request
        self.result = result


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
        extra.append(f'User is playing as {user_color}. Override any information that indicates otherwise.')

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
            _role: 'system',
            _content: _system_prompt + '.'.join(self.system_extra(app))
        }]

        for item in self.queries:
            msgs.append({_role: _user, _content: item.request})
            assist = {
                _role: 'assistant',
                _content: None
            }
            if item.kind == Query.Kind.GENERIC:
                assist[_content] = item.result

            elif item.kind == Query.Kind.OPENING_SELECTION:
                assist[_content] = str(item.result)

            elif item.kind == Query.Kind.PUZZLE_THEME:
                assist[_content] = item.result

            elif item.kind == Query.Kind.FUNCTION_CALL:
                call = item.result
                assist[_function_call] = {
                    _name: call.name,
                    _arguments: json.dumps(call.arguments),
                }
            msgs.append(assist)

        msgs.append(current_msg)

        return msgs


    def set_game_info(self, info):
        '''
        Keep track of played openings, for future ideas.
        '''
        if isinstance(info, dict):
            name, eco = info[_name], info.get(_eco)
        else:
            name, eco = info.name, info.eco

        self.current_opening = name


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
    funcs = {f[_name]:f for f in funcs if f[_name] != func_name}  # convert to dictionary
    assert func_name not in funcs  # verify that it is removed

    return list(funcs.values())  # convert back to list


class Assistant:
    def __init__(self, app):
        self._app = weakref.proxy(app)
        self._ctxt = Context()
        self._enabled = True
        self._handlers = {}
        self._register_funcs()
        self._register_handlers()
        self.endpoint = 'https://api.openai.com/v1/chat/completions'
        self.model = 'gpt-3.5-turbo-1106'
        self.retry_count = 3
        self.requests_timeout = 3.0
        self.initial_temperature = 0.01
        self.temperature_increment = 0.01
        self.token_limit = 2048


    def set_game_info(self, info):
        self._ctxt.set_game_info(info)


    def append_history(self, *, kind, request, result):
        self._ctxt.queries.append(Query(kind=kind, request=request, result=result))


    @property
    def enabled(self):
        return self._enabled and self._app.speak_moves


    @enabled.setter
    def enabled(self, enable):
        self._enabled = enable
        if enable and not self._app.speak_moves:
            self._app.speak_moves = True


    def _completion_request(
        self,
        user_request,
        messages,
        *,
        functions,
        function_call,
        temperature,
        timeout,
        async_result=None
    ):
        response = None
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self._app.get_openai_key(obfuscate=False),
        }

        json_data = {
            'model': self.model,
            'messages': messages,
            'functions': functions,
            _function_call: function_call,
            'temperature': temperature,
        }
        try:
            Logger.info(f'Assistant: posting request to {self.endpoint}')

            response = requests.post(
                self.endpoint,
                headers=headers,
                json=json_data,
                timeout=timeout,
            )

            if response:
                return self._handle_api_response(
                    user_request, json.loads(response.content), async_result
                )
            else:
                Logger.error(f'Assistant: {json.loads(response.content)}')

        except requests.exceptions.ReadTimeout as e:
            Logger.warning(f'Assistant: request failed: {e}')
            return None, FunctionResult(AppLogic.RETRY)

        except:
            Logger.exception('Assistant: Error generating API response.')

        return None, FunctionResult()


    def _handle_api_response(self, user_request, response, async_result=None):
        '''
        Handle response from the OpenAI API call.
        '''
        try:
            Logger.debug(f'Assistant: response={response}')
            top = response['choices'][0]
            message = top['message']
            reason = top['finish_reason']

            if reason != _function_call:
                Logger.info(f'Assistant: {reason}')

                return None, self._handle_non_function(reason, user_request, message, async_result)

            elif function_call := self._create_function_call(message):
                result = function_call.execute(user_request)

                if not result:
                    result = FunctionResult()

                if result.response == AppLogic.FUNCTION:
                    self.append_history(
                        kind=_function_call,
                        request=user_request,
                        result=function_call,
                    )

                return function_call.name, result

        except:
            Logger.exception('Assistant: Error handling API response.')

        return None, FunctionResult()


    def _handle_non_function(self, reason, user_request, message, result):
        content = message[_content]

        for retry in range(3):
            if not content:
                break
            try:
                response = json.loads(content)

                for k,h in self._handlers.items():
                    if k in response:
                        return h(user_request, response)
                break

            except json.decoder.JSONDecodeError as e:
                content = content[:e.pos]

        self._respond(message[_content], user_request=user_request, result=result)
        return FunctionResult()


    @staticmethod
    def _create_function_call(response):
        if call := response.get(_function_call):
            return FunctionCall(call[_name], call[_arguments])


    def run(self, user_input, result=None):
        if not user_input.strip():
            return False  # prevent useless, expensive calls

        funcs = _FUNCTIONS
        temperature = self.initial_temperature
        timeout = self.requests_timeout

        current_message = {
            _role: _user,
            _content: user_input,
        }

        retry_count = 0
        function_call = 'auto'

        result_message = None

        if result:
            function_call = 'none'  # Disable function calling.

            func_name = result.pop(_function)
            result_message = {
                _role: _function,
                _name: func_name,
                _content: json.dumps(result),
            }

        while retry_count < self.retry_count:
            messages = self._ctxt.messages(
                current_message,
                app=self._app,
                model=self.model,
                functions=funcs,
                token_limit=self.token_limit,
            )
            if result_message:
                messages.append(result_message)

            Logger.debug(f'Assistant:\n{json.dumps(messages, indent=2)}')

            # Call the OpenAI API.
            func_name, func_result = self._completion_request(
                user_input,
                messages,
                functions=funcs,
                function_call=function_call,
                async_result=result,
                temperature=temperature,
                timeout=timeout,
            )

            if func_result.response != AppLogic.FUNCTION:
                self._ctxt.pop_function_call()
                function_call = 'auto'

            if func_result.response == AppLogic.INVALID:
                funcs = remove_func(funcs, func_name)
                retry_count += 1

            elif func_result.response == AppLogic.RETRY:
                retry_count += 1

                if func_result.data:
                    current_message = {
                        _role: _user,
                        _content: func_result.data
                    }
                else:
                    timeout *= 2
                    temperature += self.temperature_increment

            elif func_result.response == AppLogic.FUNCTION:
                current_message = {
                    _role: _function,
                    _name: func_name,
                    _content: json.dumps(func_result.data)
                }
                function_call = 'none'

            # Crucial to return True on success: prevent endless loops.
            else:
                return True

        Logger.error(f'Assistant: failed, retry={retry_count}/{self.retry_count}.')


    # -------------------------------------------------------------------
    #
    # FunctionCall handlers.
    #
    # -------------------------------------------------------------------

    def _handle_analysis(self, user_request, inputs):

        if self._app.engine.is_game_over():
            return FunctionResult(AppLogic.FUNCTION, str({
                'function': _analyze_position,
                'pgn': self._app.transcribe()[1],
                'result': self._app.engine.result()
            }))

        # Start async analysis, will call back when finished.
        self._app.analyze(assist=(_analyze_position, user_request))
        return FunctionResult(AppLogic.OK)


    def _handle_get_transcript(self, user_request, inputs):
        _, pgn = self._app.transcribe()
        result = {
            'pgn': pgn,
        }
        return FunctionResult(AppLogic.FUNCTION, result)


    def _handle_answer(self, user_request, inputs):
        if answer := inputs.get(_answer):
            self._respond(answer, inputs.get(_topic), user_request=user_request)
            return FunctionResult(AppLogic.OK)

        return FunctionResult(AppLogic.INVALID)


    def _handle_lookup_openings(self, user_request, inputs):
        requested_openings = inputs.get(_openings)
        if not requested_openings:
            return FunctionResult(AppLogic.INVALID)

        results = []
        for name in requested_openings:
            eco_opening = self._lookup_opening({_name: name})
            if not eco_opening:
                Logger.warning(f'Assistant: Not found: {str(inputs)}')
            else:
                result = {
                    _name: eco_opening.name,
                }
                if len(requested_openings) == 1:
                    # include details if looking up a single opening
                    result['eco'] = eco_opening.eco
                    result['pgn'] = eco_opening.pgn

                results.append(result)

        return FunctionResult(AppLogic.FUNCTION, results)


    def _handle_chess_opening(self, user_request, inputs):
        if _name not in inputs:
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
                        f'The opening that you suggested is already in play.'
                        f'Suggest another variation related to {self._ctxt.current_opening},'
                        f'or another opening with a move sequence not included in: {current}.'
                    )
                )
            else:
                self._schedule_action(lambda *_: self._app.play_opening(opening))
                return FunctionResult(AppLogic.OK)


    def _handle_puzzle_theme(self, user_request, inputs):
        '''
        Handle the suggestion of a puzzle theme.
        '''
        theme = inputs.get(_theme)
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


    def _register_handlers(self):
        self._handlers[_answer] = self._handle_answer
        self._handlers[_openings] = self._handle_lookup_openings
        self._handlers[_name] = self._handle_chess_opening
        self._handlers[_theme] = self._handle_puzzle_theme


    def _register_funcs(self):
        FunctionCall.register(_analyze_position, self._handle_analysis)
        FunctionCall.register(_lookup_openings, self._handle_lookup_openings)
        FunctionCall.register(_present_answer, self._handle_answer)
        FunctionCall.register(_play_chess_opening, self._handle_chess_opening)
        FunctionCall.register(_select_chess_puzzles, self._handle_puzzle_theme)
        FunctionCall.register(_get_game_transcript, self._handle_get_transcript)


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

        name = choice[_name]
        eco = choice.get(_eco)
        result = self._app.eco.name_lookup(name, eco, confidence=confidence)

        if not result:
            result = self._app.eco.phonetical_lookup(name, confidence=75)

        return result


    @mainthread
    def _say(self, text):
        if text and self._app.speak_moves:
            Logger.debug(f'Assistant: {text}')
            self._app.speak(text)


    def _respond(self, text, topic=None, *, user_request, result=None):
        '''
        Respond to a user question with speech and text bubble.
        '''
        text = text.replace('\n', ' ')
        if user_request:
            self.append_history(kind='generic', request=user_request, result=text)

        self._schedule_action(lambda *_: self._app.text_bubble(text))
        self._speak_response(text, topic)


    def _speak_response(self, text, topic):
        tts_text = substitute_chess_moves(text, ';')
        self._say(tts_text)


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
