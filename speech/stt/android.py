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
from jnius import PythonJavaClass, autoclass, java_method
from kivy.logger import Logger

from android.runnable import run_on_ui_thread

from .base import STT

activity = autoclass('org.kivy.android.PythonActivity').mActivity
android_api_version = autoclass('android.os.Build$VERSION')

ArrayList = autoclass('java.util.ArrayList')
Bundle = autoclass('android.os.Bundle')
Context = autoclass('android.content.Context')
Intent = autoclass('android.content.Intent')
RecognizerIntent = autoclass('android.speech.RecognizerIntent')
RecognitionListener = autoclass('android.speech.RecognitionListener')
SpeechRecognizer = autoclass('android.speech.SpeechRecognizer')
SpeechResults = SpeechRecognizer.RESULTS_RECOGNITION


_error_message = {
    SpeechRecognizer.ERROR_AUDIO: 'audio',
    SpeechRecognizer.ERROR_CLIENT: 'client',
    SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS: 'insufficient permissions',
    SpeechRecognizer.ERROR_NETWORK: 'network',
    SpeechRecognizer.ERROR_NETWORK_TIMEOUT: 'network timeout',
    SpeechRecognizer.ERROR_NO_MATCH: 'no match',
    SpeechRecognizer.ERROR_RECOGNIZER_BUSY: 'recognizer busy',
    SpeechRecognizer.ERROR_SERVER: 'server',
    SpeechRecognizer.ERROR_SPEECH_TIMEOUT: 'speech timeout',
}


class SpeechListener(PythonJavaClass):
    '''
    Implement RecognitionListener interface.

    https://developer.android.com/reference/android/speech/RecognitionListener
    '''
    __javainterfaces__ = ['android/speech/RecognitionListener']

    def __init__(self):
        super().__init__()
        self._error_callback = lambda *_: None
        self._results_callback = lambda *_: None
        self._end_of_speech = lambda *_: None
        self.results = []

        # prevent callbacks while stopping
        self.is_stopping = False


    @java_method('()V')
    def onBeginningOfSpeech(self):
        pass


    @java_method('([B)V')
    def onBufferReceived(self, buffer):
        pass


    @java_method('()V')
    def onEndOfSpeech(self):
        self._end_of_speech()


    @java_method('(I)V')
    def onError(self, error):
        msg = _error_message.get(error, 'unknown')
        Logger.error(f'stt: onError({msg}) stop={self.is_stopping}')

        if not self.is_stopping:
            self._error_callback(error)


    @java_method('(ILandroid/os/Bundle;)V')
    def onEvent(self, event_type, params):
        pass


    @java_method('(Landroid/os/Bundle;)V')
    def onPartialResults(self, results):
        self._on_results(results, done=False)


    @java_method('(Landroid/os/Bundle;)V')
    def onReadyForSpeech(self, params):
        pass


    @java_method('(Landroid/os/Bundle;)V')
    def onResults(self, results):
        self._on_results(results, done=True)


    @java_method('(F)V')
    def onRmsChanged(self, rmsdB):
        pass


    def _on_results(self, results, done):
        '''
        Shared implementation for onPartialResults, onResults.
        '''
        if self.is_stopping:
            return

        matches = results.getStringArrayList(SpeechResults)
        for match in matches.toArray():
            if isinstance(match, bytes):
                match = match.encode().decode('utf-8')

            if not self.results or self.results[-1] != match:
                self.results.append(match)

        self._results_callback(self.results, done)


class AndroidSTT(STT):
    '''
    Android speech-to-text.

    https://developer.android.com/reference/android/speech/RecognizerIntent
    '''
    def __init__(self, **kwargs):
        super().__init__()
        self.speech = None
        self.listener = None
        self._listening = False


    def _end(self, error = 0):
        '''
        End-of-speech detected, or some error occurred.
        '''
        if error == SpeechRecognizer.ERROR_RECOGNIZER_BUSY:
            return

        if error:
            self.error_callback(_error_message.get(error, 'unknown'))
            self.stop()

        self._listening = False


    @run_on_ui_thread
    def _start(self):
        assert not self.speech
        intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)

        # language preferences
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, self.language)
        intent.putExtra(RecognizerIntent.EXTRA_ONLY_RETURN_LANGUAGE_PREFERENCE, True)
        intent.putExtra(
            RecognizerIntent.EXTRA_LANGUAGE_MODEL,
            RecognizerIntent.LANGUAGE_MODEL_FREE_FORM
        )

        # results settings
        intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1000)
        intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, True)

        if self.is_offline_supported():
            intent.putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, self.prefer_offline)
            Logger.debug(f'stt: prefer_offline={self.prefer_offline}')

        # listener and callbacks
        self.listener = SpeechListener()

        self.listener._end_of_speech = self._end
        self.listener._error_callback = self._end
        self.listener._results_callback = self.results_callback

        # create recognizer and start
        self.speech = SpeechRecognizer.createSpeechRecognizer(activity)
        self.speech.setRecognitionListener(self.listener)
        self.speech.startListening(intent)

        self._listening = True


    @run_on_ui_thread
    def _stop(self):
        if not self.speech:
            return

        self.listener.is_stopping = True
        self.speech.cancel()

        # free object
        self.speech.destroy()
        self.speech = None

        self.listener = None


    def _is_listening(self):
        return self.listener and self._listening


    def _is_supported(self):
        return bool(SpeechRecognizer.isRecognitionAvailable(activity))


    def _is_offline_supported(self):
        return android_api_version.SDK_INT >= 23
