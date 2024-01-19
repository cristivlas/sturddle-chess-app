"""
Sturddlefish Chess App (c) 2021, 2022, 2023, 2024 Cristian Vlasceanu
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
import chess.pgn
import json
import logging
import os
import random
import re
import requests
import weakref

from center import CenterControl
from collections import defaultdict, namedtuple
from enum import Enum
from functools import partial
from intent import IntentClassifier
from io import StringIO
from gpt_utils import get_token_count, get_token_limit
from kivy.clock import Clock, mainthread
from kivy.logger import Logger
from normalize import substitute_chess_moves
from opening import Opening
from puzzleview import PuzzleCollection, puzzle_description
from puzzleview import themes_dict as puzzle_themes
from speech import tts
from worker import WorkerThread

logging.getLogger('urllib3.connectionpool').setLevel(logging.INFO)


_ECO = 'Encyclopedia of Chess Openings'

_valid_puzzle_themes = { k for k in puzzle_themes if PuzzleCollection().filter(k) }

''' Function names. '''
_analyze_position = 'analyze_position'
_load_puzzle = 'load_chess_puzzle'
_lookup_openings = 'lookup_openings'
_make_one_move = 'make_one_move'
_make_moves = 'make_moves'
_play_opening = 'play_opening'

''' Schema keywords, constants. '''
_animate = 'animate'
_arguments = 'arguments'
_assistant = 'assistant'
_array = 'array'
_content = 'content'
_center_control = 'center_control'
_description = 'description'
_eco = 'eco'
_error = 'error'
_fen = 'FEN'
_function = 'function'
_function_call = 'function_call'
_integer = 'integer'
_items = 'items'
_limit = 'limit'
_move = 'move'
_name = 'name'
_object = 'object'
_openings = 'opening_names'
_role = 'role'
_parameters = 'parameters'
_pgn = 'pgn'
_properties = 'properties'
_required = 'required'
_response = 'response'
_result = 'result'
_retry = 'Retry'
_return = 'return'
_state = 'state'
_string = 'string'
_system = 'system'
_theme = 'theme'
_type = 'type'
_turn = 'turn'
_user = 'user'

''' Functions.
https://platform.openai.com/docs/guides/function-calling
'''
_FUNCTIONS = [
    {
        _name: _analyze_position,
        _description: (
            'This function analyzes the current game position. It returns the best move '
            'for the side-to-move and the principal variation (pv).'
        ),
        _parameters: {
            _type: _object,
            _properties: {}
        }
    },
    {
        _name: _lookup_openings,
        _description: f'This function searches chess openings by name in the {_ECO}.',
        _parameters: {
            _type: _object,
            _properties : {
                _openings: {
                    _type: _array,
                    _description: (
                        'An array of names to look up. Always use complete opening names when available.'
                    ),
                    _items: {
                        _type: _string,
                    }
                },
                _limit: {
                    _type: _integer,
                    _description: 'Limit the number of search results.'
                }
            },
            _required: [_openings, _limit]
        }
    },
    {
        _name: _load_puzzle,
        _description: (
            'Load a chess puzzle that matches the specified theme. '
        ) + 'The valid themes are: ' + ', '.join(_valid_puzzle_themes),
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
        _name: _play_opening,
        _description: 'Play the specified opening.',
        _parameters: {
            _type: _object,
            _properties : {
                _name: {
                    _type: _string,
                    _description: 'The name of the opening. Always use complete opening names when available.',
                },
                _user: {
                    _type: _string,
                    _description: 'The side the user wants to play.'
                }
            },
            _required: [_name]
        }
    },
    {
        _name: _make_moves,
        _description: 'Make a sequence of moves on the board. The moves are specified as PGN.',
        _parameters: {
            _type: _object,
            _properties: {
                _pgn: {
                    _type: _string,
                    _description: (
                        'A string containing a PGN snippet. Must contain numbered moves. '
                        'The desired moves must be preceded by the complete game history.'
                    )
                },
                _animate: {
                    _type: 'boolean',
                    _description: (
                        'True to make the moves one by one, in an animated fashion. '
                        'Default is False. Use True when the user wants to see a replay.'
                    ),
                },
                _user: {
                    _type: _string,
                    _description: 'The side the user wants to play as.'
                }
            },
            _required: [_pgn],
        }
    },
    {
        _name: _make_one_move,
        _description: 'Make one single move on the board.',
        _parameters: {
            _type: _object,
            _properties: {
                _move: {
                    _type: _string,
                    _description: 'The move to make, in Standard Algebraic Notation (SAN).'
                }
            },
            _required: [_move]
        }
    }
]

# Limit responses to English, because the app has hardcoded stuff (for now).

_BASIC_PROMPT = (
    f"Always reply with text-to-speech friendly English text. "
    f"Do not state the position of individual pieces or use ASCII art. "
    f"Be concise. Do not return move sequences in non-function call replies. "
)

_SYSTEM_PROMPT = (
    f"You are a chess tutor within a chess app, guiding on openings, puzzles, "
    f"and game analysis. Base your advice strictly on the provided game state; "
    f"avoid assumptions or extrapolations beyond this data. You can demonstrate "
    f"openings with {_play_opening}, and make moves with {_make_moves}. Use "
    f"the latter to play out PVs returned by {_analyze_position}. When calling "
    f"{_lookup_openings}, prefix variations by the base name of the opening, up "
    f"to the colon delimiter. You must always run fresh analysis when the position "
    f"changes. "
) + _BASIC_PROMPT


class AppLogic(Enum):
    NONE = 0
    OK = 1
    RETRY = 2
    INVALID = 3  # Function called with invalid or missing parameters.
    CANCELLED = 4


FunctionResult = namedtuple('FunctionResult', 'response data', defaults=(AppLogic.NONE, None))


def parse_json(text):
    try:
        return json.loads(text)

    except Exception as e:
        Logger.error(f'{_assistant}: {e} {text}')


class FunctionCall:
    dispatch = {}

    def __init__(self, name, arguments):
        self.name = name
        self.arguments = parse_json(arguments)

    def execute(self, user_request):
        Logger.info(f'{_assistant}: FunctionCall={self.name}({self.arguments})')
        if self.name in FunctionCall.dispatch:
            return FunctionCall.dispatch[self.name](user_request, self.arguments)

    @staticmethod
    def register(name, func):
        FunctionCall.dispatch[name] = func


def _get_user_color(app):
    return chess.COLOR_NAMES[app.engine.opponent]


_colors = {'black': False, 'white': True}

def _get_color(name):
    ''' Convert color name back to chess.Color '''
    if name is not None:
        return _colors.get(name.lower())


class GameState:
    def __init__(self, app=None):
        self.valid = False
        if app:
            #self.epd = app.engine.board.epd()
            self.center = CenterControl(app.engine.board)
            self.pgn = app.transcribe(columns=None, engine=False)[1]
            self.turn = None if app.engine.is_game_over() else app.engine.board.turn
            self.user_color = _get_user_color(app)
            self.valid = True

    def to_dict(self):
        turn = None
        if self.turn is not None:
            # Format the turn to make it as clear as possible to the AI:
            turn = f'{chess.COLOR_NAMES[self.turn].capitalize()} to move'

        return {
            # Do not send the FEN, it looks like ChatGPT cannot parse it
            # and it may result in unpronounceable strings in the replies
            #_fen: self.epd,
            _center_control: self.center.status,
            _pgn: self.pgn,
            _turn: turn,
            _user: self.user_color.capitalize(),
        }

    def __str__(self):
        return str(self.to_dict()) if self.valid else 'invalid'


class Context:
    ''' Keeps track of the conversation history '''

    def __init__(self):
        self.history = []
        self.user = None  # The side the user is playing
        self.epd = None


    def add_message(self, message):
        self.history.append(message)


    def add_response(self, response):
        self.add_message({_role: _assistant, _content: response})


    def add_function_call(self, function):
        message = {
            _role: _assistant,
            _content: None,
            _function_call: {
                _name: function.name,
                _arguments: json.dumps(function.arguments)
            }
        }
        self.add_message(message)


    def annotate_user_message(self, app, message):
        '''
        Modify the content of user messages when the position
        or the side played by the user has changed from the last exchange.
        This helps the backend AI better understand the context.

        Args:
            app (object): A weak proxy to the application.
            message (dict): The message to be sent to the AI.

        Returns:
            dict: The input message unchanged, or the modified message.
        '''
        if message[_role] == _user:
            user_color = _get_user_color(app)
            epd = app.engine.board.epd()
            changes = []

            if not app.engine.is_game_over():
                if self.user != user_color:
                    changes.append(f'I am playing as {user_color}.')

                if self.epd and self.epd != epd:
                    if not app.puzzle:
                        changes.append(f'The position has changed: {GameState(app).pgn}.')

            if changes:
                if not app.engine.is_game_over():
                    turn = chess.COLOR_NAMES[app.engine.board.turn]
                    changes.append(f'It is {turn}\'s turn to move.')
                changes = ' '.join(changes)
                #content = f'{changes} {message[_content]}'
                content = f'{message[_content]} (Context: {changes})'
                message = {_role: _user, _content: content}

            self.epd = epd  # Keep track of the board state.
            self.user = user_color  # Keep track of the side played by the user.

        return message


    @staticmethod
    def describe_theme(theme):
        ''' Return English description of a puzzle theme.'''
        return puzzle_themes.get(theme, theme).rstrip(',.:')


    def messages(self, current_msg, *, app, model, functions, token_limit):
        '''
        Construct a list of messages for the OpenAI API.

        Prepend the system prompt and the conversation history, while keeping
        the overall size of the payload under the token_limit.
        '''
        current_msg = self.annotate_user_message(app, current_msg)

        if current_msg[_role] == _function:
            system_prompt = _BASIC_PROMPT  # Save some tokens
        else:
            system_prompt = _SYSTEM_PROMPT

        if app.puzzle:
            system_prompt += (
                f'Summarize the active puzzle without providing any move hints. '
                f'When the user asks for the solution to the problem, reply with '
                f'a grandmaster quote, or a koan. The puzzle theme is: {puzzle_description(app.puzzle)}. '
            )

        while True:
            # Prefix messages with the system prompt.
            msgs = [{_role: 'system', _content: system_prompt}] + self.history + [current_msg]

            token_count = get_token_count(model, msgs, functions)

            if token_count <= token_limit:
                Logger.debug(f'{_assistant}: token_count={token_count}')
                break

            if not self.history:
                # There are no more old messages to remove!
                raise RuntimeError(f'Request size (~{token_count} tokens) exceeds token limit ({token_limit}).')

            self.history.pop(0)  # Remove the oldest message.

        return msgs


    def prune_function_calls(self):
        '''
        Remove older function calls and results from the message history, to keep
        the size of the context under control (the game state info sent back from
        functions can get large fast, and the most recent state is what matters anyway).
        '''
        indices = [i for i in range(len(self.history))]
        # Logger.debug(f'{_assistant}: history=\n{json.dumps(self.history, indent=2)}')
        for i, entry in enumerate(self.history[:-2]):
            if self.history[i][_role] == _function:
                indices.remove(i)
                if i > 0 and _function_call in self.history[i-1]:
                    indices.remove(i-1)
        self.history = [self.history[i] for i in indices]
        # Logger.debug(f'{_assistant}: history=\n{json.dumps(self.history, indent=2)}')


def remove_func(funcs, function):
    ''' Remove function from the schema. '''
    funcs = {f[_name]:f for f in funcs if f[_name] != function}  # convert to dictionary
    assert function not in funcs  # verify that it is removed

    return list(funcs.values())  # convert back to list


class Assistant:
    def __init__(self, app):
        self._app = weakref.proxy(app)
        self._busy = False
        self._cancelled = False
        self._ctxt = Context()
        self._enabled = True
        self._handlers = {}
        self._register_funcs()
        self._register_handlers()
        self.endpoint = 'https://api.openai.com/v1/chat/completions'
        self.model = 'gpt-3.5-turbo-1106'
        self.retry_count = 5
        self.requests_timeout = 5.0
        self.temperature = 0.01
        self._worker = WorkerThread()
        self.last_call = None
        self.session = requests.Session()
        self.intent_recognizer = IntentClassifier()
        self.intent_recognizer.load('intent-model')


    @property
    def busy(self):
        return self._busy


    def cancel(self):
        if self._busy:
            self._app.stop_spinner()
            self._busy = False
            self._cancelled = True
            self.session.close()
            self.session = requests.Session()


    @property
    def enabled(self):
        return (
            self._app.speak_moves  # requires the voice interface, for now
            and self._enabled
            and not self._cancelled  # wait for the cancelled task to finish
        )


    @enabled.setter
    def enabled(self, enable):
        self._enabled = enable
        if enable and not self._app.speak_moves:
            self._app.speak_moves = True


    def _completion_request(self, user_request, messages, *, functions, timeout):
        '''
        Post request to the OpenAI completions endpoint.
        Return tuple containing the name of the handler and a FunctionResult.
        '''
        response = None
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self._app.get_openai_key(obfuscate=False),
        }
        json_data = {
            'model': self.model,
            'messages': messages,
            'temperature': self.temperature,
        }
        if functions:
            json_data['functions'] = functions

        try:
            Logger.info(f'{_assistant}: posting request to {self.endpoint}')

            response = self.session.post(
                self.endpoint,
                headers=headers,
                json=json_data,
                timeout=timeout,
            )
            if self._cancelled:
                Logger.info(f'{_assistant}: response cancelled')
                return None, FunctionResult(AppLogic.CANCELLED)

            if response:
                self._ctxt.add_message(messages[-1])  # outgoing message posted successfully

                return self._on_api_response(user_request, parse_json(response.content))

            else:
                Logger.error(f'{_assistant}: {parse_json(response.content)}')

        except requests.exceptions.ReadTimeout as e:
            Logger.warning(f'{_assistant}: request failed: {e}')
            return None, FunctionResult(AppLogic.RETRY)

        except:
            Logger.exception('Assistant: Error generating API response.')
            return None, FunctionResult(AppLogic.RETRY)

        return None, FunctionResult()


    def _on_api_response(self, user_request, response):
        '''
        Handle response from the OpenAI API, dispatch function calls as needed.
        '''
        try:
            Logger.debug(f'{_assistant}: response={response}')
            top = response['choices'][0]
            message = top['message']
            reason = top['finish_reason']

            if reason != _function_call:
                Logger.info(f'{_assistant}: {reason}')

                return None, self._on_non_function(reason, user_request, message)

            elif function_call := self._create_function_call(message):

                # Save the function_call to the conversation history before executing it.
                self._ctxt.add_function_call(function_call)

                result = function_call.execute(user_request)

                if not result:
                    result = FunctionResult()

                return function_call.name, result

        except:
            Logger.exception('Assistant: Error handling API response.')

        return None, FunctionResult()


    def _on_non_function(self, reason, user_request, message):
        ''' Called when the finish_reason in the API response is anything but 'function_call' '''
        content = message[_content]

        # Handle both plain text and JSON-formatted responses.
        for retry in range(3):
            if not content:
                break
            try:
                response = json.loads(content)
                if isinstance(response, dict):
                    for k,h in self._handlers.items():
                        if k in response:
                            Logger.info(f'{_assistant}: handler={k}')
                            return h(user_request, response)
                break

            except json.decoder.JSONDecodeError as e:
                content = content[:e.pos]

        response = message[_content]

        # Handle some bad responses from the AI model.
        if '```' in response:
            Logger.warning(f'{_assistant}: RETRY {response}')
            return FunctionResult(AppLogic.RETRY, 'Do not use code blocks.')

        if contains_epd(response):
            Logger.warning(f'{_assistant}: RETRY {response}')
            return FunctionResult(AppLogic.RETRY, 'Do not use FEN or EPD in your replies.')

        self._ctxt.prune_function_calls()
        self._ctxt.add_response(response)  # Save response into conversation history.

        self.respond_to_user(response)

        return FunctionResult()


    def _create_function_call(self, response):
        self.last_call = None
        if call := response.get(_function_call):
            self.last_call = call
            return FunctionCall(call[_name], call[_arguments])


    def call(self, user_input, callback_result=None):
        '''
        Entry point. Initiate asynchronous task and return. Put up a spinner.

        Args:
            user_input (str): User command, request, etc.
            callback_result (dict, optional): used by callbacks to post results back to the AI.

        Returns:
            bool: False if cancelled or call with empty inputs, otherwise True
        '''
        assert not self._busy  # Caller must check the busy state.

        if self._cancelled:
            return False  # Wait for the cancelled job to finish.

        if not user_input:
            return False

        self._busy = True
        self._app.start_spinner()

        Logger.debug(f'{_assistant}: {user_input}')

        def detect_intent(user_input):
            intents = self.intent_recognizer.classify_intent(user_input, top_n=10)
            return intents

        def task_completed():
            self._busy = False
            self._cancelled = False
            self._app.update(self._app.engine.last_moves()[-1], save_state=False)

        def background_task():
            intents = None
            if not callback_result and self._app.use_intent_recognizer:
                # Attempt to detect user's intent locally, to save a roundtrip.
                Logger.info(f'{_assistant}: calling intent recognizer')
                intents = detect_intent(user_input)

                Logger.info(f'{_assistant}: intents={intents}, user_input="{user_input}"')
                if self._cancelled:
                    Logger.info(f'{_assistant}: task cancelled')
                    return task_completed()

                if intents and self._resolve_intents(user_input, intents):
                    return task_completed()

            # Call the remote service.
            status = self._call_on_same_thread(user_input, callback_result, intents)
            task_completed()
            if status is None:
                self.respond_to_user('Sorry, I cannot complete your request at this time.')

        self._worker.send_message(background_task)
        return True


    def _call_on_same_thread(self, user_request, callback_result=None, intents=None):
        '''
        Calls the OpenAI model in the background and handles the response.

        This method interacts with the OpenAI model using the user's input. It
        processes the response, handling network timeouts, invalid parameter
        errors, and custom retry logic specific to different functions. If the
        response suggests a function call, it dispatches the processing to that
        function. The method returns the name of the function that handled the
        response, or None if no specific function was involved.

        Args:
            user_request (str): A free-form string containing the user's command.
            callback_result (dict, None): The result of an asynchronous function.

        Returns:
            True on success, False if cancelled, None if failed.
        '''
        timeout = self.requests_timeout

        # Construct the message to send out.
        if callback_result:
            current_message = {
               _role: _function,
               _name: callback_result.pop(_function),
               _content: str(callback_result)
            }
            # Do not use functions when returning the result of a function call
            funcs = None

        else:
            current_message = {
                _role: _user,
                _content: user_request,
            }
            funcs = _FUNCTIONS

        token_limit = int(get_token_limit(self.model) * 0.85)

        for retry_count in range(self.retry_count):
            messages = self._ctxt.messages(
                current_message,
                app=self._app,
                model=self.model,
                functions=funcs,  # for get_token_count
                token_limit=token_limit
            )
            # Dump pretty-printed messages to log.
            Logger.debug(f'{_assistant}: messages=\n{json.dumps(messages, indent=2)}')

            # Post the request and dispatch the response.
            func_name, func_result = self._completion_request(
                user_request, messages, functions=funcs, timeout=timeout)

            if func_result.response == AppLogic.CANCELLED:
                return False

            # Handle the case of functions being called with invalid args.
            if func_result.response == AppLogic.INVALID:
                if retry_count == 0:
                    current_message = {
                        _role: _function,
                        _name: func_name,
                        _content: f'{_error}: invalid parameters',
                    }
                else:
                    funcs = remove_func(funcs, func_name)

            elif func_result.response == AppLogic.RETRY:
                if func_result.data:
                    content = f'{_retry}: use different arguments. {func_result.data}'
                    if func_name:
                        current_message = {
                            _role: _function,
                            _name: func_name,
                            _content: content
                        }
                    else:
                        current_message = {_role: _user, _content: content}
                else:
                    timeout *= 1.5  # Handle network timeouts.

            else:
                return True  # Success

        Logger.error(f'{_assistant}: request failed:\n{json.dumps(messages, indent=2)}')


    def _complete_on_same_thread(self, user_request, function, result=None):
        ''' Call the AI synchronously to return the results of a function call.
        This is useful for the AI to understand the most recent state of the game.

        Args:
            user_request (str): User input that trigger the function call returning results.
            function (str): The name of the function returning the results.
            result (any): The results.

        Returns:
            FunctionResult
        '''
        status = self._call_on_same_thread(
            user_request,
            callback_result=self.format_result(function, result)
        )
        if status:
            return FunctionResult(AppLogic.OK)

        if status is None:
            return FunctionResult(AppLogic.CANCELLED)

        return FunctionResult()


    def complete_on_main_thread(self, user_request, function, *, result=None, resume=False):
        ''' Call the backend to notify that a function call has completed.

        Args:
            user_request (str): User input that triggered the function call.
            function (str): The name of the function that has completed.
            result (any): The result of the function call.
            resume (bool): True if the engine needs to be resumed.
        '''
        def callback(*_):
            if resume:
                self._app.set_study_mode(False)  # Start the engine.

            if resume and (self._app.engine.busy or self._app.engine.is_own_turn()):
                # Wait for the engine to make its move.
                Clock.schedule_once(callback)

            else:
                callback_result = self.format_result(function, result)

                self.call(user_request, callback_result=callback_result)

        if self._app.engine.is_game_over():
            resume = False

        Clock.schedule_once(callback)


    def format_result(self, function, result=None):
        ''' Format and "decorate" the results of a function call with
        GameState information.
        Args:
            function (str): The name of the function that has completed.
            result (any): The result of the function call.
        Returns:
            dict: A dictionary containing the result and the game state.
        '''
        # Always include the name of the function and the current state.
        formatted_result = GameState(self._app).to_dict()
        formatted_result[_function] = function

        if result is not None:
            formatted_result[_result] = str(result)

        return formatted_result


    # -------------------------------------------------------------------
    #
    # FunctionCall handlers.
    #
    # -------------------------------------------------------------------

    def _handle_analysis(self, user_request, inputs):
        ''' Handle function call from the AI requesting game analysis.

        Args:
            user_request (str): user input that triggered the function call.
            inputs (dict): parameters as per _FUNCTIONS schema.
        Returns:
            FunctionResult:
        '''
        # Handle the "game over" edge case.
        if self._app.engine.is_game_over():
            return self._complete_on_same_thread(user_request, _analyze_position)

        # Do not provide analysis in puzzle mode. Let the user figure it out.
        if self._app.puzzle:
            return self._complete_on_same_thread(
                user_request, _analyze_position, 'User should solve puzzles unassisted.'
            )

        # Do not provide analysis on the engine's turn
        if self._app.engine.is_own_turn():
            return self._complete_on_same_thread(
                user_request, _analyze_position, 'It is not the user\'s turn.'
            )

        # Start analysing asynchronously; will call back when finished.
        self._app.analyze(assist=(user_request, _analyze_position))

        return FunctionResult(AppLogic.OK)


    def _handle_lookup_openings(self, user_request, inputs):
        ''' Lookup a list of chess openings in the ECO.

        Args:
            user_request (str): The user input associated with this function.
            inputs (dict): function inputs as per the _FUNCTIONS schema.

        Returns:
            FunctionResult
        '''
        requested_openings = inputs.get(_openings)
        if not requested_openings:
            return FunctionResult(AppLogic.INVALID)

        # Return a list of matches, or just the best one?
        max_results = inputs.get(_limit, 1)

        def annotate_search_result(search_result):
            if isinstance(search_result, Opening):
                return {
                    _name: search_result.name,
                }
            else:
                return search_result

        results = []

        for name in requested_openings:
            args = {
                _name: name,
                _eco: inputs.get(name, None)
            }
            search_result = self._search_opening(args, max_results=max_results)

            if not search_result:
                Logger.warning(f'{_assistant}: Not found: {str(inputs)}')

            elif isinstance(search_result, list):
                results += [annotate_search_result(match) for match in search_result]

            else:
                assert isinstance(search_result, Opening)
                best_match = annotate_search_result(search_result)

                # Include more details if a single opening was requested.
                if len(requested_openings) == 1:
                    best_match[_eco] = search_result.eco
                    best_match[_pgn] = search_result.pgn

                results.append(best_match)

        results = {
            _result: 'ok' if results else 'no match',
            _limit: len(results[:max_results]),
            _return: results[:max_results]
        }
        return self._complete_on_same_thread(user_request, _lookup_openings, results)


    def _handle_play_opening(self, user_request, inputs):
        ''' Handle the call to play a specific chess opening.

        Args:
            user_request (str): The user request that triggered this function call.
            inputs (dict): parameters as per _FUNCTION schema.

        Returns:
            FunctionResult
        '''
        if _name not in inputs:
            Logger.error(f'{_assistant}: invalid inputs: {inputs}')
            return FunctionResult(AppLogic.INVALID)

        opening = self._search_opening(inputs)
        color = _get_color(inputs.get(_user))  # Preferred perspective.

        if not opening:
            Logger.warning(f'{_assistant}: opening not found: {inputs}')
            return self._complete_on_same_thread(user_request, _play_opening, 'Opening not found.')

        else:
            on_done = partial(
                self.complete_on_main_thread,
                user_request,
                _play_opening,
                result='Success.',
                resume=True
            )
            def play_opening():
                status = self._app.play_opening(opening, callback=on_done, color=color)
                if not status:
                    self.complete_on_main_thread(
                        user_request,
                        _play_opening,
                        result=f'{_error}: opening may already be in play'
                    )
            self._schedule_action(play_opening)
            return FunctionResult(AppLogic.OK)


    def _handle_puzzle_request(self, user_request, inputs):
        '''
        Handle the request to select a puzzle by given theme.
        Filter all puzzles by theme and select one at random.
        '''
        theme = inputs.get(_theme)
        if not theme:
            return FunctionResult(AppLogic.INVALID)

        puzzles = PuzzleCollection().filter(theme)
        if not puzzles:
            return FunctionResult(AppLogic.INVALID)  # invalid theme

        # Choose puzzle at random from the subset that matches the theme.
        selection = random.choice(puzzles)

        def play_puzzle(puzzle):
            ''' Called after the user confirms the puzzle. '''
            self._app.selected_puzzle = puzzle[3]
            self._app.load_puzzle(puzzle)

            msg = f'Loaded puzzle with theme: {Context.describe_theme(theme)}'
            self.complete_on_main_thread(user_request, _load_puzzle, result=msg)

        # Schedule running the puzzle (may ask the user for confirmation).
        self._schedule_action(
            partial(
                self._app.new_action,
                'practice: ' + Context.describe_theme(theme),
                partial(play_puzzle, selection)
            )
        )
        return FunctionResult(AppLogic.OK)


    def _handle_make_moves(self, user_request, inputs):
        ''' Apply position and moves from PGN.
        Args:
            user_request (str): user request that ended up triggering this function call.
            inputs (dict): dictionary of parameters as decribed in _FUNCTIONS schema.

        Returns:
            FunctionResult
        '''
        if self._app.engine.is_game_over():
            return FunctionResult(AppLogic.INVALID)

        pgn = inputs.get(_pgn)
        if not pgn:
            return FunctionResult(AppLogic.INVALID)

        # Get the optional params.
        animate = inputs.get(_animate)
        color = _get_color(inputs.get(_user))

        opening = None

        game = chess.pgn.read_game(StringIO(pgn))  # Parse the PGN for validation.
        if game:
            opening = game.headers.get('Opening')  # Retain the name of the opening.

            # Strip out everything but the moves.
            exporter = chess.pgn.StringExporter(columns=None, headers=False, variations=False, comments=False)

            pgn = game.accept(exporter).rstrip(' *')

        else:
            pgn = None  # invalid

        if not pgn:
            retry_message = f'The PGN input is invalid, run {_analyze_position}.'
            return FunctionResult(AppLogic.RETRY, retry_message)

        # Completion callback.
        on_done = partial(self.complete_on_main_thread, user_request, _make_moves, resume=True)

        def make_moves():
            status = self._app.play_pgn(pgn, animate=animate, callback=on_done, color=color, name=opening)
            if not status:
                retry_message = f'There was an error making the moves, run {_analyze_position}.'
                # At this point we're in a asynchronous callback, can't use AppLogic.RETRY
                return self.complete_on_main_thread(user_request, _make_moves, result=retry_message)

        self._schedule_action(make_moves)
        return FunctionResult(AppLogic.OK)


    def _handle_make_one_move(self, user_request, inputs):
        san = inputs.get(_move)
        if not san:
            return FunctionResult(AppLogic.INVALID)

        try:
            move = self._app.engine.board.parse_san(san)
        except ValueError:
            return FunctionResult(AppLogic.INVALID)

        self._app.speak_move_description(move)

        def make_move(*_):
            if tts.is_speaking():
                Clock.schedule_once(make_move, 0.25)
            else:
                self._app.engine.input(move)

        make_move()
        return FunctionResult(AppLogic.OK)


    def _register_handlers(self):
        '''
        "Backup" handlers for parsing the rare and accidental malformed responses.
        '''
        self._handlers[_openings] = self._handle_lookup_openings
        self._handlers[_move] = self._handle_make_one_move
        self._handlers[_name] = self._handle_play_opening
        self._handlers[_pgn] = self._handle_make_moves
        self._handlers[_theme] = self._handle_puzzle_request


    def _register_funcs(self):
        FunctionCall.register(_analyze_position, self._handle_analysis)
        FunctionCall.register(_lookup_openings, self._handle_lookup_openings)
        FunctionCall.register(_make_moves, self._handle_make_moves)
        FunctionCall.register(_make_one_move, self._handle_make_one_move)
        FunctionCall.register(_play_opening, self._handle_play_opening)
        FunctionCall.register(_load_puzzle, self._handle_puzzle_request)


    # -------------------------------------------------------------------
    #
    # Miscellaneous helpers.
    #
    # -------------------------------------------------------------------

    def _resolve_intents(self, user_input, intents):
        """ Execute functions associated with the recognized intents, if any. """

        # Add this message into the conversation history if the intent is recognized, for context.
        user_msg = self._ctxt.annotate_user_message(self._app, {_role: _user, _content: user_input})

        search_param = set()

        for i, _ in intents:
            action = i.split(':')
            verb = action[0].strip()
            if verb == 'analyze':
                self._ctxt.add_message(user_msg)
                return self._handle_analysis(user_input, {}).response == AppLogic.OK
            elif verb == 'search':
                if len(action) > 1:
                    search_param.add(tuple(action[1:]))
            elif verb == 'puzzle':
                if len(action) > 1:
                    self._ctxt.add_message(user_msg)
                    param = action[1].strip()
                    return self._handle_puzzle_request(user_input, {_theme: param}).response == AppLogic.OK
            else:
                break

        if search_param:
            self._ctxt.add_message(user_msg)  # Add to conversation.

            args = {_openings: [], _limit: len(search_param)}
            for name, eco in search_param:
                args[_openings].append(name)
                args[name] = eco
            return self._handle_lookup_openings(user_input, args).response == AppLogic.OK


    def respond_to_user(self, response):
        '''
        Present the response to a request back to the user via tts and on-screen text bubble.

        Args:
            text (str): The message to be presented to the user.
        '''
        # Convert list of moves (in short algebraic notation - SAN) to pronounceable text.
        tts_text = substitute_chess_moves(response, ';')

        # Reformat numbered lists if the response does not seem to contain moves.
        if tts_text == response:
            pattern = r'(\d+\.[^\n;]+?)(?:\s|\n|\.)+(?=\s*\d+\.|\s*$)'
            tts_text = re.sub(pattern, r'\1; ', response)

        else:
            # Remove paranthesis enclosing move sequences to prevent reading aloud "smiley face".
            tts_text = re.sub(r'\((.*?)\)', r'\1', tts_text)

        # Remove newlines from the on-screen text, to better fit inside the bubble.
        text = response.replace('\n', ' ')

        # Schedule the bubble to pop up as soon as other modal boxes go away.
        self._schedule_action(lambda *_: self._app.text_bubble(text))

        # Speak the tts_text curated text.
        self._speak_response(tts_text)


    def _search_opening(self, query, max_results=1):
        '''  Lookup opening(s) in the ECO database.
        Args:
            query (dict): Must contain 'eco' or 'name' key.
            max_results (int): maximum number of matches to be returned.

        Returns:
            Opening or list: best match or list of matches.
        '''
        eco = query.get(_eco)
        if eco:
            results = self._app.eco.query_by_eco_code(eco, top_n=max_results)
        else:
            name = query[_name]
            Logger.info(f'query: "{name}"')
            results = self._app.eco.query_by_name(name, top_n=max_results)
            Logger.info(f'query: "{[(r.eco, r.name) for r in results]}"')

        return results[0] if len(results) == 1 else results


    def _schedule_action(self, action, *_):
        '''
        Schedule an action to be executed as soon as all modal popups are dismissed.
        '''
        if self._app.voice_input.is_running():
            self._app.voice_input.stop()

        if self._app.has_modal_views():
            Clock.schedule_once(partial(self._schedule_action, action), 0.1)
        else:
            Clock.schedule_once(lambda *_: action(), 0.1)


    def _speak_response(self, text):

        def speak(*_):
            ''' Wait until finished speaking, then speak the tts_text string. '''
            if tts.is_speaking():
                Clock.schedule_once(speak, 0.25)
            else:
                Clock.schedule_once(partial(self._app.speak, tts_text))

        # Make sure St. George is pronounced Saint George, not Street George
        tts_text = re.sub(r'\bSt\.\b|\bst\.\b', 'Saint', text, flags=re.IGNORECASE)

        if text:
            Logger.debug(f'{_assistant}: {text}')
            speak()


def group_by_prefix(strings, group_hint=None, sort_by_freq=True):
    '''
    Group search results (for openings) by prefix, sort descending by frequency.
    The same effect could probably be achieved by organizing the ECO information
    as graphs or trees of openings with variations. The "flat" way of storing may
    work better with the rapidfuzz name searching though.
    '''
    def generate_prefixes(string, expr_len):
        '''Generate all prefixes up to expr_len terms for a given string.'''
        terms = string.split(',')
        return [' '.join(terms[:i]).rstrip() for i in range(1, min(expr_len+1, len(terms)+1))]

    def get_prefixes(n):
        prefixes = defaultdict(int)
        for s in sorted(strings, reverse=True):
            for p in generate_prefixes(s, n):
                prefixes[p] += 1
        return prefixes

    for n in range(5, 3, -1):
        prefixes = get_prefixes(n)

        if group_hint is None or len(prefixes) == group_hint:
            break

        if len(prefixes) < group_hint:
            prefixes = get_prefixes(n + 1)
            break

    result = prefixes.items()

    if sort_by_freq:
        # Sort by the number of strings containing them
        result = sorted(result, key=lambda kv: kv[1], reverse=True)

    return result


_epd_regex = (
    r'([rnbqkpRNBQKP1-8]+\/){7}[rnbqkpRNBQKP1-8]+'  # Piece placement
    r'\s[bw]'  # Active color
    r'\s[-KQkq]+'  # Castling availability
    r'\s([a-h][1-8]|-)'  # En passant target square
    r'(\s[^\s]+)*'  # Optional fields
)

def contains_epd(text):
    return re.search(_epd_regex, text) is not None

