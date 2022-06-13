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

import subprocess
import threading
from functools import partial

import plyer
from kivy.clock import Clock, ClockEvent
from kivy.logger import Logger
from kivy.utils import platform
from plyer.utils import whereis_exe

'''
Bypass plyer.tts because: it has no stop(); the Android impl is buggy.
'''
_scheduled = [None]


if platform == 'ios':
    def _speak(message):
        plyer.tts.speak(message)

elif platform == 'android':
    '''
    https://developer.android.com/reference/android/speech/tts/TextToSpeech
    '''
    from jnius import PythonJavaClass, autoclass, java_method

    activity = autoclass('org.kivy.android.PythonActivity').mActivity
    Locale = autoclass('java.util.Locale')
    TextToSpeech = autoclass('android.speech.tts.TextToSpeech')

    class OnInitListener(PythonJavaClass):
        __javainterfaces__ = ['android/speech/tts/TextToSpeech$OnInitListener']
        status = None

        @java_method('(I)V')
        def onInit(self, status):
            if status != TextToSpeech.ERROR:
                OnInitListener.status = instance.setLanguage(Locale.forLanguageTag('en-US'))
                Logger.info(f'tts: OnInit status={self.status}')

    listener = OnInitListener()
    instance = TextToSpeech(activity, listener)


    def _speak(message, *_):
        Logger.info(f'tts: _speak OnInitListener.status={OnInitListener.status}')

        if OnInitListener.status is None:
            # initialization pending, retry later
            Logger.info('tts: init pending')
            _scheduled[0] = Clock.schedule_once(partial(_speak, message), 0.1)

        else:
            if OnInitListener.status >= 0:
                status = instance.speak(message, TextToSpeech.QUEUE_FLUSH, None)
                Logger.info(f'tts speak({message})={status}')
            else:
                Logger.error(f'tts: OnInitListener.status={OnInitListener.status}')

            _scheduled[0] = None

else:
    def _subprocess(args):
        p = subprocess.Popen(args)

        def background_wait(p):
            p.wait()
            Logger.info(f'stt: {p}')
            _scheduled[0] = None

        thread = threading.Thread(target=background_wait, args=(p,))
        # exit abnormally if main thread is terminated
        thread.daemon = True

        thread.start()
        return p

    def _speak(message):
        utility = whereis_exe('say') or whereis_exe('espeak')
        if utility:
            _scheduled[0] = _subprocess([utility, message])


def is_speaking():
    if _scheduled[0]:
        return True

    if platform == 'android':
        return instance.isSpeaking()


def speak(message, stt, *_):
    assert(message)

    if is_speaking() or stt.is_listening():
        _scheduled[0] = Clock.schedule_once(partial(speak, message, stt), 0.1)

    else:
        _speak(message)


def stop():
    if s := _scheduled[0]:
        if isinstance(s, ClockEvent):
            s.cancel()

        elif isinstance(s, subprocess.Popen):
            s.terminate()

    elif platform == 'android':
        if instance.isSpeaking():
            instance.stop()
