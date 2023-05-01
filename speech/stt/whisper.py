'''
Offline-only voice recognitiona with OpenAi-Whisper.
'''
import os

import ffmpeg
import numpy as np
import speech_recognition as sr
import whisper
from kivy.core.audio import SoundLoader

from .base import STT

MODEL = 'tiny.en'

# https://github.com/openai/whisper/discussions/380
def load_audio(file: (str, bytes), sr: int = 16000):
    if isinstance(file, bytes):
        inp = file
        file = 'pipe:'
    else:
        inp = None

    try:
        # This launches a subprocess to decode audio while down-mixing and resampling as necessary.
        # Requires the ffmpeg CLI and `ffmpeg-python` package to be installed.
        out, _ = (
            ffmpeg.input(file, threads=0)
            .output('-', format='s16le', acodec='pcm_s16le', ac=1, ar=sr)
            .run(cmd='ffmpeg', capture_stdout=True, capture_stderr=True, input=inp)
        )
    except ffmpeg.Error as e:
        raise RuntimeError(f'Failed to load audio: {e.stderr.decode()}') from e

    return np.frombuffer(out, np.int16).flatten().astype(np.float32) / 32768.0

'''
Implement voice recognition using OpenAI-Whisper.
'''
class WhisperSTT(STT):
    def __init__(self, **kwargs):
        super().__init__()
        self._cancel = None
        self._start_sound = self._load_sound('start.mp3', 0.5)
        self._stop_sound = self._load_sound('stop.mp3', 0.5)
        self._sr = sr.Recognizer()
        self.time_limit = kwargs.pop('time_limit', 5)
        self._model = whisper.load_model(MODEL)

    def _start(self):
        def callback(_, audio):
            if not self._is_listening():
                return

            # In the context of the SpeechRecognition library, the convert_width parameter
            # is used in the get_wav_data method to set the desired number of bytes per sample
            # in the output WAV data. Essentially, it defines the sample width, or bit depth,
            # of the audio data in the output WAV file.
            # The possible values for convert_width are:
            # 1: For 8-bit audio samples, where each sample is stored as an 8-bit (1-byte) integer.
            # 2: For 16-bit audio samples, where each sample is stored as a 16-bit (2-byte) integer.
            # 4: For 32-bit audio samples, where each sample is stored as a 32-bit (4-byte) integer.
            wav = audio.get_wav_data(convert_rate=16000, convert_width=2)

            result = self._model.transcribe(load_audio(wav), fp16=False, initial_prompt='my chess move:')
            text = result['text']
            if text:
                self.results_callback([text.strip()])
            else:
                self.stop()

        with sr.Microphone() as source:
            self._sr.adjust_for_ambient_noise(source)

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
