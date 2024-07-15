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
from kivy.core.audio import SoundLoader

class STT:
    '''
    Speech-to-text base class
    '''
    language = 'en-US'

    def __init__(self):
        self.results_callback = lambda *_: None
        self.error_callback = lambda *_: None
        self._prefer_offline = True

    def start(self):
        self._start()

    def stop(self):
        self._stop()

    def is_listening(self):
        return self._is_listening()

    def is_supported(self):
        return self._is_supported()

    def is_offline_supported(self):
        return self._is_supported() and self._is_offline_supported()

    @property
    def prefer_offline(self):
        if not self._is_supported():
            return True
        if self._is_offline_supported():
            return self._prefer_offline
        return False

    @prefer_offline.setter
    def prefer_offline(self, prefer_offline):
        # set it, will ignore if not supported
        self._prefer_offline = prefer_offline

    def _start(self):
        pass

    def _stop(self):
        pass

    def _is_listening(self):
        return False

    def _is_supported(self):
        return False

    def _is_offline_supported(self):
        return False


def load_sound(filename, volume=1):
    """Support utility for chimes."""
    if sound := SoundLoader.load(os.path.join(os.path.dirname(__file__), filename)):
        sound.volume = volume
        return sound
