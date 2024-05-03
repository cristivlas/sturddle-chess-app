#!/usr/bin/env python3
import argparse
import logging
import tempfile
from gtts import gTTS
	
# Disable warning messages from the 'playsound' module
logging.getLogger('playsound').setLevel(logging.ERROR)
from playsound import playsound

def main():

	# Set up the argument parser
	parser = argparse.ArgumentParser(description="Text-to-Speech using gTTS")
	parser.add_argument("text", help="Text to convert to speech")
	parser.add_argument("--voice", default="en-au", help="Language code for the voice (default: en-au)")

	# Parse arguments
	args = parser.parse_args()

	# Create a gTTS object
	tts = gTTS(text=args.text, lang=args.voice)

	# Create a temporary file
	with tempfile.NamedTemporaryFile(delete=True, suffix='.mp3') as fp:
		# Save the speech to the temporary MP3 file
		tts.save(fp.name)

		# Play the MP3 file
		playsound(fp.name)

if __name__ == "__main__":
	main()
