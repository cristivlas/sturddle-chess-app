"""
Sturddlefish Chess App (c) 2022 Cristian Vlasceanu
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
from kivy.logger import Logger

from .base import STT
from .data import phonetic

DEEPSPEECH_MODEL = 'deepspeech-0.9.3-models.tflite'
DEEPSPEECH_SCORER = 'chess.scorer'


class GenericSTT(STT):

    def __init__(self, **kwargs):
        super().__init__()
        self.failover = kwargs.pop('failover', False)
        self.time_limit = kwargs.pop('time_limit', 5)

        self._sr = sr.Recognizer()
        self._cancel = None

        self._model = self._init_deepspeech()


    def _init_deepspeech(self):
        try:
            import deepspeech

        except:
            return

        model_path = os.path.join(os.path.dirname(__file__), DEEPSPEECH_MODEL)

        if not os.path.exists(model_path):
            Logger.warning(f'stt: file not found: {os.path.realpath(model_path)}')
            return

        model = deepspeech.Model(model_path)

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
                self._stop()

            except sr.RequestError as e:
                error = e

            if error:
                self.stop()
                self.error_callback(error)

        with sr.Microphone() as source:
            self._sr.adjust_for_ambient_noise(source)

        self._cancel = self._sr.listen_in_background(sr.Microphone(), callback, self.time_limit)


    def _stop(self):
        if self._cancel:
            self._cancel(wait_for_stop=False)
            self._cancel = None


    def _is_listening(self):
        return bool(self._cancel)


    def _is_offline_supported(self):
        return bool(self._model)


    def _is_supported(self):
        return True