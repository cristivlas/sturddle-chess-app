#!/usr/bin/env python3
import argparse
import logging
import tempfile
from gtts import gTTS
import simpleaudio as sa
from pydub import AudioSegment

def play_audio(filepath):
    wave_obj = sa.WaveObject.from_wave_file(filepath)
    play_obj = wave_obj.play()
    play_obj.wait_done()

def main():
    # Set up the argument parser
    parser = argparse.ArgumentParser(description="Text-to-Speech using gTTS")
    parser.add_argument("text", help="Text to convert to speech")
    parser.add_argument("--voice", default="en-au", help="Language code for the voice (default: en-au)")

    # Parse arguments
    args = parser.parse_args()

    # Create a gTTS object
    tts = gTTS(text=args.text, lang=args.voice)

    # Create a temporary MP3 file
    with tempfile.NamedTemporaryFile(delete=True, suffix='.mp3') as mp3_fp, tempfile.NamedTemporaryFile(delete=True, suffix='.wav') as wav_fp:
        # Save the speech to the temporary MP3 file
        tts.save(mp3_fp.name)

        # Convert MP3 to WAV
        audio = AudioSegment.from_mp3(mp3_fp.name)
        audio.export(wav_fp.name, format='wav')

        # Play the WAV file
        play_audio(wav_fp.name)

if __name__ == "__main__":
    main()
