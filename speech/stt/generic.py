"""
Sturddlefish Chess App (c) 2022, 2023, 2024 Cristian Vlasceanu
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
import speech_recognition as sr
from kivy.logger import Logger

from .base import STT, load_sound

'''
Generic desktop speech-to-text transcription using Google.
'''
class GenericSTT(STT):
    def __init__(self, **kwargs):
        super().__init__()
        self.failover = kwargs.pop('failover', False)
        self.time_limit = kwargs.pop('time_limit', 5)
        self._sr = sr.Recognizer()
        self._cancel = None
        self._start_sound = load_sound('start.mp3', 0.5)
        self._stop_sound = load_sound('stop.mp3', 0.5)

    def _start(self):
        def callback(recognizer, audio):
            if not self._is_listening():
                return
            try:
                text = recognizer.recognize_google(audio, language=self.language)
                assert text
                self.results_callback([text])
            except sr.UnknownValueError:
                pass
            except sr.RequestError as error:
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
        return False

    def _is_supported(self):
        return True

