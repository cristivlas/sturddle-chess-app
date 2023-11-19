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
import re
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
from worker import WorkerThread

logging.getLogger('urllib3.connectionpool').setLevel(logging.INFO)


_ECO = 'Encyclopedia of Chess Openings'

_valid_puzzle_themes = { k for k in puzzle_themes if PuzzleCollection().filter(k) }

''' Function names. '''
_analyze_position = 'analyze_position'
_get_game_transcript = 'get_pgn'
_lookup_openings = 'lookup_openings'
_play_chess_opening = 'play_chess_opening'
_select_chess_puzzles = 'select_chess_puzzles'

''' Schema keywords, constants. '''
_arguments = 'arguments'
_array = 'array'
_content = 'content'
_description = 'description'
_eco = 'eco'
_function = 'function'
_function_call = 'function_call'
_items = 'items'
_object = 'object'
_openings = 'opening_names'
_role = 'role'
_parameters = 'parameters'
_properties = 'properties'
_required = 'required'
_name = 'name'
_response = 'response'
_return = 'return'
_string = 'string'
_system = 'system'
_theme = 'theme'
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
        _description: f'This function searches chess openings by name in the {_ECO}.',
        _parameters: {
            _type: _object,
            _properties : {
                _openings: {
                    _type: _array,
                    _description: 'The names to look up.',
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
        _description: ('Play the specified opening.'),
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
    f"You are a chess tutor within a chess app, guiding on openings, puzzles, "
    f"and game analysis. Use {_analyze_position} for analyzing the board, and "
    f"for recommending moves to the user. Consult {_get_game_transcript} for the "
    f"PGN transcript. Use {_play_chess_opening} for setting up the board with a "
    f"specific chess opening. Use {_lookup_openings} to search for chess opening "
    f"information. Select puzzles with {_select_chess_puzzles} based on the theme "
    f"specified by the user. Autocorrect famous chess player names in your replies."
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
        Logger.error(f'Assistant: {e} {text}')


class FunctionCall:
    dispatch = {}

    def __init__(self, name, arguments):
        self.name = name
        self.arguments = parse_json(arguments)

    def execute(self, user_request):
        Logger.info(f'Assistant: FunctionCall={self.name}({self.arguments})')
        if self.name in FunctionCall.dispatch:
            return FunctionCall.dispatch[self.name](user_request, self.arguments)

    @staticmethod
    def register(name, func):
        FunctionCall.dispatch[name] = func


def _get_pgn(app):
    return app.transcribe(engine=False)[1]  # Do not show engine name and version.


class GameState:
    def __init__(self, app=None):
        self.valid = False
        if app:
            self.epd = app.engine.board.epd()
            self.pgn = _get_pgn(app)
            self.user_color = ['Black', 'White'][app.engine.opponent]
            self.valid = True

    def __str__(self):
        if not self.valid:
            return 'invalid state'
        return str({'FEN': self.epd, 'pgn': self.pgn, 'user_color': self.user_color})

    def __eq__(self, other):
        return str(self) == str(other)


class Context:
    def __init__(self):
        self.history = []
        self.game_state = GameState()

    def add_message(self, message):
        self.history.append(message)

    def add_response(self, response):
        self.add_message({_role: 'assistant', _content: response})

    def add_function_call(self, function):
        message = {
            _role: 'assistant',
            _content: None,
            _function_call: {
                _name: function.name,
                _arguments: json.dumps(function.arguments)
            }
        }
        self.add_message(message)

    def messages(self, current_msg, *, app, model, functions, token_limit):
        '''
        Construct a list of messages to be passed to the OpenAI API call.

        Prepend the system prompt and the conversation history, while keeping
        the overall size of the payload under the token_limit.
        '''
        msg = current_msg.copy()
        if msg['role'] == 'user':
            # Append a note about the state of the game having changed.
            msg['content'] += self.update_game_state(app)

        while True:
            # Prefix messages with the system prompt.
            msgs = [{_role: 'system', _content: _system_prompt}] + self.history + [msg]

            if not self.history:
                break

            token_count = get_token_count(model, msgs, functions)

            if token_count <= token_limit:
                Logger.debug(f'Assistant: token_count={token_count}')
                break

            self.history.pop(0)  # Remove the oldest message.

        return msgs

    @staticmethod
    def describe_theme(theme):
        ''' Return English description of a puzzle theme.'''
        return puzzle_themes.get(theme, theme).rstrip(',.:')

    def update_game_state(self, app):
        msg = ''
        current_state = GameState(app)
        if current_state != self.game_state:
            msg = f'; the board state has changed; the current state is: {current_state}.'
            self.game_state = current_state

        return msg


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
        self.retry_count = 3
        self.requests_timeout = 3.0
        self.temperature = 0.01
        self.token_limit = 3072
        self._worker = WorkerThread()


    def cancel(self):
        if self._busy:
            self._app.stop_spinner()
            self._busy = False
            self._cancelled = True


    @property
    def busy(self):
        return self._busy


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
            Logger.info(f'Assistant: posting request to {self.endpoint}')

            response = requests.post(
                self.endpoint,
                headers=headers,
                json=json_data,
                timeout=timeout,
            )
            if self._cancelled:
                Logger.info(f'Assistant: response cancelled')
                return None, FunctionResult(AppLogic.CANCELLED)

            if response:
                self._ctxt.add_message(messages[-1])  # outgoing message posted successfully

                return self._handle_api_response(user_request, parse_json(response.content))

            else:
                Logger.error(f'Assistant: {parse_json(response.content)}')

        except requests.exceptions.ReadTimeout as e:
            Logger.warning(f'Assistant: request failed: {e}')
            return None, FunctionResult(AppLogic.RETRY)

        except:
            Logger.exception('Assistant: Error generating API response.')

        return None, FunctionResult()


    def _handle_api_response(self, user_request, response):
        '''
        Handle response from the OpenAI API call, dispatch function calls as needed.
        '''
        try:
            Logger.debug(f'Assistant: response={response}')
            top = response['choices'][0]
            message = top['message']
            reason = top['finish_reason']

            if reason != _function_call:
                Logger.info(f'Assistant: {reason}')

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
        Entry point for calling the AI. Initiates an asynchronous task and returns immediately.

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
            status = self._call_ai(user_input, callback_result)

            self._busy = False
            self._cancelled = False
            self._app.update()

            if status is None:
                self._respond_to_user('Sorry, I cannot help you with your request at this time.')

        self._busy = True
        self._app.start_spinner()
        self._worker.send_message(run_in_background)

        return True


    def _call_ai(self, user_request, callback_result=None):
        '''
        Calls the OpenAI model in the background, handles the response, and
        dispatches further processing.

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
               _content: json.dumps(callback_result)
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
            Logger.debug(f'Assistant: messages=\n{json.dumps(messages, indent=2)}')

            # Post the request and dispatch the response.
            func_name, func_result = self._completion_request(user_request, messages, functions=funcs, timeout=timeout)

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
                    timeout *= 2  # Handle network timeouts.

            else:
                return True  # Success


    def _call_ai_with_results(self, user_request, func_name, results):
        '''
        Call the AI to return the results of a function call synchronously.

        Args:
            user_request (str): User input that trigger the function call returning results.
            func_name (str): The name of the function returning the results.
            results (any): The results.

        Returns:
            FunctionResult
        '''
        status = self._call_ai(user_request, callback_result={_function: func_name, _return: results})

        if status:
            return FunctionResult(AppLogic.OK)

        if status is None:
            return FunctionResult(AppLogic.CANCELLED)

        return FunctionResult()


    # -------------------------------------------------------------------
    #
    # FunctionCall handlers.
    #
    # -------------------------------------------------------------------

    def _handle_analysis(self, user_request, inputs):
        '''
        Handle function call from the AI that requests analysis.
        Args:
            user_request (str): user input that triggered the function call.
            inputs (dict): parameters as per _FUNCTIONS schema.
        Returns:
            FunctionResult:
        '''
        # Handle the edge case where the game is over.
        if self._app.engine.is_game_over():
            return self._call_ai_with_results(
                user_request,
                _analyze_position,
                {
                    'pgn': _get_pgn(self._app),
                    'result': self._app.engine.result()
                }
            )

        # Do not provide analysis in puzzle mode. Let the user figure it out.
        if self._app.puzzle:
            return self._call_ai_with_results(
                user_request,
                _analyze_position,
                'User should solve puzzles unassisted.'
            )

        # Start analysing, will call back when finished.
        self._app.analyze(assist=(_analyze_position, user_request))
        return FunctionResult(AppLogic.OK)


    def _handle_get_transcript(self, user_request, inputs):
        pgn = _get_pgn(self._app)
        return self._call_ai_with_results(user_request, _get_game_transcript, pgn)


    def _handle_lookup_openings(self, user_request, inputs):
        '''
        Handle the call from the AI to lookup a list of chess openings in the ECO.

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
                Logger.warning(f'Assistant: Not found: {str(inputs)}')

            elif isinstance(search_result, list):
                results += [annotate_search_result(match) for match in search_result]

            else:
                best_match = annotate_search_result(search_result)

                # Include more details if a single opening was requested.
                if len(requested_openings) == 1:
                    best_match['eco'] = search_result.eco
                    best_match['pgn'] = search_result.pgn

                results.append(best_match)

        # Send the results back to the AI.
        return self._call_ai_with_results(user_request, _lookup_openings, results)


    def _handle_chess_opening(self, user_request, inputs):
        '''
        Handle the call from the AI to play a specific chess opening.
        Args:
            user_request (str): The user request that triggered this function call.
            inputs (dict): parameters as per _FUNCTION schema.

        Returns:
            FunctionResult
        '''
        if _name not in inputs:
            Logger.error(f'Assistant: invalid inputs: {inputs}')
            return FunctionResult(AppLogic.INVALID)

        opening = self._search_opening(inputs)

        if not opening:
            Logger.error(f'Assistant: opening not found: {inputs}')

            # Send back some hints about how to try again.
            return FunctionResult(AppLogic.RETRY, (
                f'The opening was not found. Use {_play_chess_opening} '
                f'with another name that "{inputs[_name]}" is known as.'
            ))
        else:
            current = self._app.get_current_play()

            if current.startswith(opening.pgn):
                return self._call_ai_with_results(
                    user_request,
                    _play_chess_opening,
                    f'{opening.name} is already in progress.'
                )

            def on_play():
                # Call back into the AI to confirm the opening is set up.
                # callback_result = {
                #     _function: _play_chess_opening,
                #     _return: f'The {opening.name} is set up.'
                # }
                # self.call(user_request, callback_result=callback_result)
                self._call_ai_with_results(user_request, _play_chess_opening, f'The {opening.name} is set up.')

            self._schedule_action(lambda *_: self._app.play_opening(opening, callback=on_play))
            return FunctionResult(AppLogic.OK)


    def _handle_puzzle_theme(self, user_request, inputs):
        '''
        Handle the function call that requests the selection of a puzzle.
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
            '''
            Callback function that gets called after the user confirms the puzzle.
            '''
            self._app.selected_puzzle = puzzle[3]
            self._app.load_puzzle(puzzle)

            # Confirm that the user has accepted the puzzle.
            callback_result = {
                _function: _select_chess_puzzles,
                _return: f'Loaded puzzle with theme: {Context.describe_theme(theme)}'
            }
            self.call(user_request, callback_result=callback_result)

        # Schedule running the puzzle (may ask the user for confirmation).
        self._schedule_action(
            partial(
                self._app.new_action,
                'practice: ' + Context.describe_theme(theme),
                partial(play_puzzle, selection)
            )
        )
        return FunctionResult(AppLogic.OK)


    def _register_handlers(self):
        self._handlers[_openings] = self._handle_lookup_openings
        self._handlers[_name] = self._handle_chess_opening
        self._handlers[_theme] = self._handle_puzzle_theme


    def _register_funcs(self):
        FunctionCall.register(_analyze_position, self._handle_analysis)
        FunctionCall.register(_lookup_openings, self._handle_lookup_openings)
        FunctionCall.register(_play_chess_opening, self._handle_chess_opening)
        FunctionCall.register(_select_chess_puzzles, self._handle_puzzle_theme)
        FunctionCall.register(_get_game_transcript, self._handle_get_transcript)


    # -------------------------------------------------------------------
    #
    # Miscellaneous helpers.
    #
    # -------------------------------------------------------------------

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


    def _respond_to_user(self, response):
        '''
        Present the response to a request back to the user via tts and on-screen text bubble.

        Args:
            text (str): The message to be presented to the user.

        '''
        # Convert list of moves (in short algebraic notation - SAN) to pronounceable text.
        tts_text = substitute_chess_moves(response, ';', True)

        # Reformat numbered lists if the response does not seem to contain moves.
        if tts_text == response:
            pattern = r'(\d+\.[^\n;]+?)(?:\s|\n|\.)+(?=\s*\d+\.|\s*$)'
            tts_text = re.sub(pattern, r'\1; ', response)

        text = response.replace('\n', ' ')  # Remove newlines, to better fit the bubble.

        self._schedule_action(lambda *_: self._app.text_bubble(text))

        self._speak_response(tts_text)


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
        # Make sure St. George is pronounced Saint George, not Street George
        tts_text = re.sub(r'\bSt\.\b|\bst\.\b', 'Saint', text, flags=re.IGNORECASE)

        if text:
            Logger.debug(f'Assistant: {text}')
            Clock.schedule_once(partial(self._app.speak, tts_text))
