import argparse
import win32com.client

def list_voices():
    speaker = win32com.client.Dispatch("SAPI.SpVoice")
    voices = speaker.GetVoices()
    for i, voice in enumerate(voices):
        print(f"Voice {i}: {voice.GetDescription()}")

def speak(text, voice_index=0):
    speaker = win32com.client.Dispatch("SAPI.SpVoice")
    voices = speaker.GetVoices()
    speaker.Voice = voices.Item(voice_index)
    speaker.Speak(text)

def main():
    parser = argparse.ArgumentParser(description="Text-to-Speech using SAPI with selectable voices.")
    parser.add_argument("--list-voices", action="store_true", help="List available voices")
    parser.add_argument("--voice-index", type=int, default=0, help="Index of the voice to use")
    parser.add_argument("text", nargs="*", help="Text to speak")

    args = parser.parse_args()

    if args.list_voices:
        list_voices()
    elif args.text:
        text_to_speak = " ".join(args.text)
        speak(text_to_speak, args.voice_index)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
