'''
Offline-only voice recognitiona with OpenAi-Whisper.
'''
import os
import openai
import speech_recognition as sr
import whisper
from kivy.core.audio import SoundLoader
from kivy.logger import Logger
from .base import STT

# tiny.en, base.en and small.en seems to perform well-enough
# https://github.com/openai/whisper
MODEL = 'tiny.en'

'''
Implement voice recognition using OpenAI-Whisper.
'''
class WhisperSTT(STT):
    def __init__(self, **kwargs):
        super().__init__()
        self.ask_mode = False
        self._cancel = None
        self._model = whisper.load_model(MODEL)
        self._start_sound = self._load_sound('start.mp3', 0.5)
        self._stop_sound = self._load_sound('stop.mp3', 0.5)
        self._sr = sr.Recognizer()
        self.time_limit = kwargs.pop('time_limit', 5)

    def _start(self):
        def on_result(text):
            if text:
                Logger.debug(f'whisper: {text}')
                self.results_callback([text.strip()])
            else:
                self.stop()

        def callback(_, audio):
            assert self._is_listening()

            api_key = None if self.prefer_offline else os.environ.get('OPENAI_API_KEY')

            if api_key and not self.ask_mode:
                # Have API key, and not answering a simple yes/no question?
                # Use the Whisper API to generate a transcript.
                result = self._sr.recognize_whisper_api(audio, api_key=api_key)

                # Run the result through ChatGPT to improve it.
                # See: https://platform.openai.com/docs/guides/speech-to-text/improving-reliability

                system_prompt = (
                    "You sanitize user-spoken commands directed to a chess playing program. "
                    "The program recognizes 'play [OPENING_NAME]' commands. If you recognize this "
                    "intent in the input, clean it up to match the recognized syntax; replace [OPENING_NA0ME] "
                    "with just the matching variation part from the Encyclopedia of Chess Openings "
                    "(and do retain the 'play' word so that the downstream program recognizes the command). "
                    "If OPENING_NAME isn't recognized, or the command does not follow the pattern, "
                    "echo the command back unchanged, so it can be forwarded to the chess program."
                )

                try:
                    model = 'gpt-4-1106-preview'
                    response = openai.ChatCompletion.create(
                        model=model,
                        temperature=0,
                        messages=[
                            {
                                'role': 'system',
                                'content': system_prompt
                            },
                            {
                                'role': 'user',
                                'content': result,
                            }
                        ]
                    )
                    Logger.debug(f'{model}: {response}')
                    response = response['choices'][0]['message']['content']
                    Logger.debug(f'{model}: {response}')
                    if response:
                        result = response
                except:
                    Logger.exception('OpenAI exception')
            else:
                # Offline mode, using locally downloaded model.

                model, lang = MODEL.split('.')
                prompt = 'the transcript contains a chess move, chess opening, or user interface command'
                result = self._sr.recognize_whisper(
                    audio,
                    model=model,
                    language=lang,
                    prompt=prompt,
                    suppress_blank=False,
                    temperature=0.01,
                )
            on_result(result)

        with sr.Microphone() as source:
            self._sr.adjust_for_ambient_noise(source, duration=1)
            self._cancel = self._sr.listen_in_background(sr.Microphone(), callback, self.time_limit)

        if self._start_sound:
            self._start_sound.play()

    def _stop(self):
        if self._cancel:
            # wait_for_stop=False: cannot join current thread
            self._cancel(wait_for_stop=False)
            self._cancel = None

            if self._stop_sound:
                self._stop_sound.play()

    def _is_listening(self):
        return bool(self._cancel)

    def _is_offline_supported(self):
        return bool(self._model)

    def _is_supported(self):
        return self._is_offline_supported()

    def _load_sound(self, filename, volume=1):
        sound = SoundLoader.load(os.path.join(os.path.dirname(__file__), filename))
        if sound:
            sound.volume = volume
            return sound
