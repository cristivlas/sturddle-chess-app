#!/usr/bin/env python3
import argparse
import logging
import os
import tempfile
from gtts import gTTS
import simpleaudio as sa
from pydub import AudioSegment

def play_audio(filepath):
    try:
        wave_obj = sa.WaveObject.from_wave_file(filepath)
        play_obj = wave_obj.play()
        play_obj.wait_done()
    except Exception as e:
        logging.error(f"Error playing audio: {e}")

def main():
    # Set up logging
    logging.basicConfig(level=logging.INFO)

    # Set up the argument parser
    parser = argparse.ArgumentParser(description="Text-to-Speech using gTTS")
    parser.add_argument("text", help="Text to convert to speech")
    parser.add_argument("--voice", default="en", help="Language code for the voice (default: en)")

    # Parse arguments
    args = parser.parse_args()

    try:
        # Create a gTTS object
        tts = gTTS(text=args.text, lang=args.voice)

        # Create temporary MP3 and WAV files
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as mp3_fp, \
             tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as wav_fp:

            mp3_path = mp3_fp.name
            wav_path = wav_fp.name

            #logging.info(f"Temporary MP3 file path: {mp3_path}")
            #logging.info(f"Temporary WAV file path: {wav_path}")

            # Save the speech to the temporary MP3 file
            tts.save(mp3_path)

            # Convert MP3 to WAV
            audio = AudioSegment.from_mp3(mp3_path)
            audio.export(wav_path, format='wav')

            # Play the WAV file
            play_audio(wav_path)

    except PermissionError as e:
        logging.error(f"PermissionError: {e}")
        logging.error("Please check the file permissions and ensure the directory is writable.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    finally:
        # Clean up temporary files
        try:
            if mp3_path:
                os.remove(mp3_path)
            if wav_path:
                os.remove(wav_path)
        except Exception as e:
            logging.error(f"Error cleaning up temporary files: {e}")

if __name__ == "__main__":
    main()
