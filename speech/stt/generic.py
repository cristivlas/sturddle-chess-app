"""
Sturddlefish Chess App (c) 2022, 2023 Cristian Vlasceanu
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
import os
import re

import numpy as np
import speech_recognition as sr
import wget
from kivy.core.audio import SoundLoader
from kivy.logger import Logger

from . import phonetic
from .base import STT

DEEPSPEECH_URL = (
'https://github.com/mozilla/DeepSpeech/releases/download/v0.9.3/deepspeech-0.9.3-models.tflite'
)

DEEPSPEECH_MODEL = 'deepspeech-0.9.3-models.tflite'
DEEPSPEECH_SCORER = 'chess.scorer'


class GenericSTT(STT):

    def __init__(self, **kwargs):
        super().__init__()
        self.failover = kwargs.pop('failover', False)
        self.time_limit = kwargs.pop('time_limit', 5)

        self._sr = sr.Recognizer()
        self._cancel = None

        self._model = self._init_offline()

        self._start_sound = self._load_sound('start.mp3', 0.5)
        self._stop_sound = self._load_sound('stop.mp3', 0.5)


    def _init_offline(self):
        import importlib.util
        # use STT (coqui.ai) as failover TODO: deprecate/remove deepspeech
        if stt := [name for name in ['deepspeech', 'stt'] if importlib.util.find_spec(name)]:
            stt = importlib.import_module(stt[0])
        else:
            return

        model_path = os.path.join(os.path.dirname(__file__), DEEPSPEECH_MODEL)

        if not os.path.exists(model_path):
            Logger.info(f'stt: file not found: {os.path.realpath(model_path)}')
            try:
                Logger.info(f'stt: downloading {DEEPSPEECH_URL}')
                wget.download(DEEPSPEECH_URL, out=model_path)
                print()
            except Exception as e:
                Logger.error(f'stt: download failed: {e}')
                return

        model = stt.Model(model_path)

        scorer_path = os.path.join(os.path.dirname(__file__), DEEPSPEECH_SCORER)

        if os.path.exists(scorer_path):
            model.enableExternalScorer(scorer_path)

        else:
            Logger.warning(f'stt: file not found: {os.path.realpath(model_path)}')

        return model


    def _recognize_deepspech(self, audio):
        '''
        offline recognition using deepspeech model
        '''
        assert self._is_listening()

        buffer = np.frombuffer(audio.get_wav_data(convert_rate=16000, convert_width=2), np.int16)

        if text := self._model.stt(buffer):
            for p, letter in phonetic.file_reverse.items():
                text = re.sub(fr'\b{p}\b', letter, text)

            self.results_callback([text.strip()])
            return True

        return False


    def _start(self):

        def callback(recognizer, audio):
            if  not self._is_listening():
                return

            if self.prefer_offline:
                if self._recognize_deepspech(audio) or not self.failover:
                    return

            error = None
            try:
                text = recognizer.recognize_google(audio, language=self.language)
                assert text
                self.results_callback([text])

            except sr.UnknownValueError:
                pass

            except sr.RequestError as e:
                error = e

            if error:
                self.stop()
                self.error_callback(error)

        with sr.Microphone() as source:
            self._sr.adjust_for_ambient_noise(source)

        self._cancel = self._sr.listen_in_background(sr.Microphone(), callback, self.time_limit)

        if self._start_sound:
            self._start_sound.play()


    def _stop(self):
        if self._cancel:
            self._cancel(wait_for_stop=False)
            self._cancel = None

            if self._stop_sound:
                self._stop_sound.play()


    def _is_listening(self):
        return bool(self._cancel)


    def _is_offline_supported(self):
        return bool(self._model)


    def _is_supported(self):
        return True


    def _load_sound(self, filename, volume=1):
        try:
            if sound := SoundLoader.load(os.path.join(os.path.dirname(__file__), filename)):
                sound.volume = volume
                return sound
        except:
            pass
