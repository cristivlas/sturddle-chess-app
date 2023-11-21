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
import chess.pgn
import json
import logging
import os
import random
import re
import requests
import weakref

from collections import namedtuple
from enum import Enum
from functools import partial
from io import StringIO
from gpt_utils import get_token_count
from kivy.clock import Clock, mainthread
from kivy.logger import Logger
from normalize import substitute_chess_moves
from puzzleview import PuzzleCollection
from puzzleview import themes_dict as puzzle_themes
from speech import tts
from worker import WorkerThread

logging.getLogger('urllib3.connectionpool').setLevel(logging.INFO)


_ECO = 'Encyclopedia of Chess Openings'

_valid_puzzle_themes = { k for k in puzzle_themes if PuzzleCollection().filter(k) }

''' Function names. '''
_analyze_position = 'analyze_position'
_get_game_state = 'get_game_state'
_lookup_openings = 'lookup_openings'
_play_opening = 'play_opening'
_select_chess_puzzles = 'select_chess_puzzles'

''' Schema keywords, constants. '''
_arguments = 'arguments'
_assistant = 'assistant'
_array = 'array'
_content = 'content'
_description = 'description'
_eco = 'eco'
_fen = 'FEN'
_function = 'function'
_function_call = 'function_call'
_items = 'items'
_make_moves = 'make_moves'
_object = 'object'
_openings = 'opening_names'
_role = 'role'
_parameters = 'parameters'
_pgn = 'pgn'
_properties = 'properties'
_required = 'required'
_name = 'name'
_response = 'response'
_restore = 'restore'
_result = 'result'
_return = 'return'
_state = 'state'
_string = 'string'
_system = 'system'
_theme = 'theme'
_type = 'type'
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
    # {
    #     _name: _get_game_state,
    #     _description: 'Get game state including FEN, PGN and the side the user is playing.',
    #     _parameters: {
    #         _type: _object,
    #         _properties: {}
    #     }
    # },
    {
        _name: _lookup_openings,
        _description: f'This function searches chess openings by name in the {_ECO}.',
        _parameters: {
            _type: _object,
            _properties : {
                _openings: {
                    _type: _array,
                    _description: 'An array of names to look up.',
                    _items: {
                        _type: _string,
                    }
                },
                _return: {
                    _type: _string,
                    _description: (
                        "Can be either 'all' or 'best'. Indicates if all "
                        "matches should be returned, or just the best one."
                    )
                }
            },
            _required: [_openings, _return]
        }
    },
    {
        _name: _select_chess_puzzles,
        _description: (
            'Select puzzles by theme. Must be called with a valid puzzle theme.'
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
                    _description: 'The name of the opening.'
                },
                _eco: {
                    _type: _string,
                    _description: 'ECO code.'
                },
                _user: {
                    _type: _string,
                    _description: 'The side the user wants to play.'
                }
            },
            _required: [_name, _eco]
        }
    },
    {
        _name: _make_moves,
        _description: (
            'This function makes moves on the board. The moves are specified as PGN.'
        ),
        _parameters: {
            _type: _object,
            _properties: {
                _fen: {
                    _type: _string,
                    _description: 'The FEN of the position on top of which to apply the moves.'
                },
                _pgn: {
                    _type: _string,
                    _description: (
                        'A string containing a PGN snippet. Must contain numbered moves. '
                        'The desired moves must be preceded by the complete game history.'
                    )
                },
                _restore: {
                    _type: 'boolean',
                    _description: (
                        'True if restoring a previous state, False otherwise. False '
                        '(the default) instructs the app to show the moves one by one.'
                    ),
                },
                _user: {
                    _type: _string,
                    _description: 'The side the user wants to play.'
                }
            },
            _required: [_fen, _pgn],
        }
    },
]

_system_prompt = (
    f"You are a chess tutor within a chess app, guiding on openings, puzzles, and game analysis. "
    f"You can demonstrate openings with {_play_opening}, and make moves with {_make_moves}. Use "
    f"the latter to play out PVs returned by {_analyze_position}. Always use {_analyze_position} "
    f"when asked to suggest moves. If the user asks for help with puzzles, do not recommend moves "
    f"nor solutions, but respond instead with koans or quotes from famous chess masters."
)

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
    if name is not None:
        return _colors.get(name.lower())


class GameState:
    def __init__(self, app=None):
        self.valid = False
        if app:
            self.epd = app.engine.board.epd()
            self.pgn = app.transcribe(engine=False)[1]
            self.user_color = _get_user_color(app)
            self.valid = True

    def to_dict(self):
        return {
            _fen: self.epd,
            _pgn: self.pgn,
            _user: self.user_color,
        }

    def __str__(self):
        return str(self.to_dict()) if self.valid else 'invalid'

    def __eq__(self, other):
        return str(self) == str(other)


class Context:
    ''' Keeps track of the conversation history '''

    def __init__(self):
        self.history = []
        self.user = None  # The side the user is playing

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
        Modify the content of user messages when the user is solving puzzles
        of when the side played by the user has changed from the last exchange.
        This helps the backend AI better understand the context.

        Args:
            app (object): A weak proxy to the application.
            message (dict): The message to be sent to the AI.

        Returns:
            dict: The input message unchanged, or the modified message.
        '''
        user_color = _get_user_color(app)

        if message[_role] == _user:
            content = message[_content]

            if app.puzzle:
                content = f'I am solving puzzle. {content}'

            elif self.user != user_color:
                content = f'I am now playing as {user_color}. {content}'

            message = {_role: _user, _content: content}

        self.user = user_color  # Keep track of the side played by the user.
        return message


    def messages(self, current_msg, *, app, model, functions, token_limit):
        '''
        Construct a list of messages for the OpenAI API.

        Prepend the system prompt and the conversation history, while keeping
        the overall size of the payload under the token_limit.
        '''
        current_msg = self.annotate_user_message(app, current_msg)

        while True:
            # Prefix messages with the system prompt.
            msgs = [{_role: 'system', _content: _system_prompt}] + self.history + [current_msg]

            if not self.history:
                break

            token_count = get_token_count(model, msgs, functions)

            if token_count <= token_limit:
                Logger.debug(f'{_assistant}: token_count={token_count}')
                break

            self.history.pop(0)  # Remove the oldest message.

        return msgs


    @staticmethod
    def describe_theme(theme):
        ''' Return English description of a puzzle theme.'''
        return puzzle_themes.get(theme, theme).rstrip(',.:')


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
        self._cached_openings = {}
        self._register_funcs()
        self._register_handlers()
        self.endpoint = 'https://api.openai.com/v1/chat/completions'
        self.model = 'gpt-3.5-turbo-1106'
        self.retry_count = 5
        self.requests_timeout = 3.0
        self.temperature = 0.01
        self.token_limit = 3072
        self._worker = WorkerThread()


    @property
    def busy(self):
        return self._busy


    def cancel(self):
        if self._busy:
            self._app.stop_spinner()
            self._busy = False
            self._cancelled = True


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

            response = requests.post(
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

                return self._handle_api_response(user_request, parse_json(response.content))

            else:
                Logger.error(f'{_assistant}: {parse_json(response.content)}')

        except requests.exceptions.ReadTimeout as e:
            Logger.warning(f'{_assistant}: request failed: {e}')
            return None, FunctionResult(AppLogic.RETRY)

        except:
            Logger.exception('Assistant: Error generating API response.')

        return None, FunctionResult()


    def _handle_api_response(self, user_request, response):
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

                return None, self._handle_non_function(reason, user_request, message)

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


    def _handle_non_function(self, reason, user_request, message):
        content = message[_content]

        # Handle both plain text and JSON-formatted responses.
        for retry in range(3):
            if not content:
                break
            try:
                response = json.loads(content)

                for k,h in self._handlers.items():
                    if k in response:
                        Logger.info(f'{_assistant}: handler={k}')
                        return h(user_request, response)
                break

            except json.decoder.JSONDecodeError as e:
                content = content[:e.pos]

        response = message[_content]

        self._ctxt.add_response(response)  # Save response into conversation history.

        self._respond_to_user(response)

        return FunctionResult()


    @staticmethod
    def _create_function_call(response):
        if call := response.get(_function_call):
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

        def run_in_background():
            status = self._call_on_same_thread(user_input, callback_result)

            self._busy = False
            self._cancelled = False
            self._app.update()

            if status is None:
                self._respond_to_user('Sorry, I cannot complete your request at this time.')

        self._busy = True
        self._app.start_spinner()
        self._worker.send_message(run_in_background)

        return True


    def _call_on_same_thread(self, user_request, callback_result=None):
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

            # Do not use functions when returning the result of a function call.
            funcs = None

        else:
            current_message = {
                _role: _user,
                _content: user_request,
            }
            funcs = _FUNCTIONS

        for retry_count in range(self.retry_count):
            # Append the message to the historical conversation context.
            messages = self._ctxt.messages(
                current_message,
                app=self._app,
                model=self.model,
                functions=funcs,  # for get_token_count
                token_limit=self.token_limit
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
                        _content: 'invalid parameters'
                    }
                else:
                    funcs = remove_func(funcs, func_name)

            elif func_result.response == AppLogic.RETRY:
                if func_result.data:
                    # Handle function-specific retry logic.
                    current_message = {
                        _role: _user,
                        _content: func_result.data
                    }
                else:
                    timeout *= 1.5  # Handle network timeouts.

            else:
                return True  # Success

        Logger.error(f'{_assistant}: request failed:\n{json.dumps(messages, indent=2)}')


    def _complete_on_same_thread(self, user_request, function, result=None):
        ''' Call the AI synchronously to return the results of a function call.

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
            if self._app.engine.busy:
                Clock.schedule_once(callback)
            else:
                if resume:
                    self._app.set_study_mode(False)  # Start the engine.

                self.call(user_request, callback_result=self.format_result(function, result))

        Clock.schedule_once(callback)


    def format_result(self, function, result=None):
        ''' Format the results of a function call.

        Args:
            function (str): The name of the function that has completed.
            result (any): The result of the function call.
        Returns:
            dict: A dictionary containing the result and the game state.
        '''

        # Always include the name of the function and the current state.
        formatted_result = {
            _function: function,
            _state: str(GameState(self._app))
        }

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
                user_request,
                _analyze_position,
                'User should solve puzzles unassisted.'
            )

        # Start analysing asynchronously; will call back when finished.
        self._app.analyze(assist=(user_request, _analyze_position))

        return FunctionResult(AppLogic.OK)


    def _handle_get_state(self, user_request, inputs):
        return self._complete_on_same_thread(user_request, _get_game_state)


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

        # Return all matches, or just the best one?
        all = inputs.get('return', 'best') == 'all'

        def annotate_search_result(search_result):
            return {
                _name: search_result.name,
                'matched_by': search_result.match,
                'search_score': search_result.score,
            }

        results = []

        for name in requested_openings:
            search_result = self._search_opening({_name: name}, return_all_matches=all)
            if not search_result:
                Logger.warning(f'{_assistant}: Not found: {str(inputs)}')

            elif isinstance(search_result, list):
                results += [annotate_search_result(match) for match in search_result]

            else:
                best_match = annotate_search_result(search_result)

                # Include more details if a single opening was requested.
                if len(requested_openings) == 1:
                    best_match[_eco] = search_result.eco
                    best_match[_pgn] = search_result.pgn

                results.append(best_match)

        if not results:
            return FunctionResult(AppLogic.RETRY, (
                'No matches. Try alternative spellings, or use your own knowledge.'
            ))

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
            Logger.error(f'{_assistant}: opening not found: {inputs}')

            return FunctionResult(AppLogic.RETRY, (
                f'The opening was not found. Use {_play_opening} '
                f'with another name that "{inputs[_name]}" is known as.'
            ))
        else:
            current = self._app.get_current_play()

            if current.startswith(opening.pgn):
                return self._complete_on_same_thread(
                    user_request,
                    _play_opening,
                    f'{opening.name} is already in progress. Select another variation.'
                )
            on_done = partial(
                self.complete_on_main_thread, user_request, _play_opening, resume=True
            )
            self._schedule_action(
                lambda *_: self._app.play_opening(opening, callback=on_done, color=color)
            )
            return FunctionResult(AppLogic.OK)


    def _handle_puzzle_theme(self, user_request, inputs):
        '''
        Handle the request to select a puzzle by given theme.
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
            self.complete_on_main_thread(user_request, _select_chess_puzzles, result=msg)

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
        pgn = inputs.get(_pgn)
        if not pgn:
            return FunctionResult(AppLogic.INVALID)

        fen = inputs.get(_fen)
        Logger.debug(fen)
        Logger.debug(self._app.engine.board.epd())

        # Get the optional params.
        animate = not inputs.get(_restore)
        color = _get_color(inputs.get(_user))

        opening = None

        game = chess.pgn.read_game(StringIO(pgn))
        if game:
            opening = game.headers.get('Opening')  # Retain the name of the opening.

            # Strip out headers and other info.
            exporter = chess.pgn.StringExporter(headers=False, variations=False, comments=False)
            pgn = game.accept(exporter)

        # Do not resume upon completing the request, to avoid confusion over the side to move.
        on_done = partial(self.complete_on_main_thread, user_request, _make_moves)

        self._schedule_action(lambda *_:
            self._app.play_pgn(pgn, animate=animate, callback=on_done, color=color, name=opening)
        )
        return FunctionResult(AppLogic.OK)


    def _register_handlers(self):
        '''
        Backup handlers for parsing the rare and accidental malformed responses.
        '''
        self._handlers[_openings] = self._handle_lookup_openings
        self._handlers[_name] = self._handle_play_opening
        self._handlers[_pgn] = self._handle_make_moves
        self._handlers[_theme] = self._handle_puzzle_theme


    def _register_funcs(self):
        FunctionCall.register(_analyze_position, self._handle_analysis)
        FunctionCall.register(_get_game_state, self._handle_get_state)
        FunctionCall.register(_lookup_openings, self._handle_lookup_openings)
        FunctionCall.register(_make_moves, self._handle_make_moves)
        FunctionCall.register(_play_opening, self._handle_play_opening)
        FunctionCall.register(_select_chess_puzzles, self._handle_puzzle_theme)


    # -------------------------------------------------------------------
    #
    # Miscellaneous helpers.
    #
    # -------------------------------------------------------------------

    def _flip_board(self, on_done_callback=None, *_):
        if self._busy:
            Clock.schedule_once(partial(self._flip_board, on_done_callback), 0.1)

        else:
            self._app.flip_board()

            if on_done_callback:
                on_done_callback()


    def _respond_to_user(self, response):
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


    def _search_opening(self, choice, confidence=90, return_all_matches=False):
        '''
        Lookup opening(s) in the ECO "database", using minimum confidence score threshold.
        '''
        assert self._app.eco
        db = self._app.eco

        name, eco = choice[_name], choice.get(_eco)  # search criteria, from user inputs

        if return_all_matches:
            return db.lookup_all_matches(name, eco, confidence=85)

        else:
            result = self._cached_openings.get(name)

            if not result:
                result = db.lookup_best_matching_name(name, eco, confidence=confidence)

                if not result:
                    result = db.phonetical_lookup(name)

                if result:
                    self._cached_openings[result.name] = result

        return result


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
