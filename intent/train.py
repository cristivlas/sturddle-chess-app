#!/usr/bin/env python3
import argparse
import itertools
import os
import string
import sys

os.environ['KIVY_NO_ARGS']='1'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from intent import IntentClassifier
from kivy.logger import Logger, LOG_LEVELS
from opening import ECO
from puzzleview import themes_dict as puzzle_themes
from puzzleview import PuzzleCollection

all_puzzle_themes =  { k for k in puzzle_themes if PuzzleCollection().filter(k) }


def alternative_words(word):
    variations = [word]
    return variations


def generate_combinatorial_variations(sentence, *, exceptions=[]):
    # sentence = sentence.translate(str.maketrans('', '', string.punctuation))
    words = sentence.split()
    word_variations = [
        [word] + alternative_words(word) if word.lower() not in exceptions else [word]
        for word in words
    ]
    # Generate all combinatorial variations of the sentence
    sentence_variations = set(
        ' '.join(combination) for combination in itertools.product(*word_variations)
    )
    for s in sentence_variations:
        Logger.debug(f'opening: {s}')

    return list(sentence_variations)


def camel_case_tokenize(string):
    tokens = []
    current_word = ''

    for char in string:
        if (char.isupper() and current_word) or (char.isdigit() and len(current_word) > 1):
            tokens.append(current_word)
            current_word = char
        else:
            current_word += char

    if current_word:
        tokens.append(current_word)

    return [t.lower() for t in tokens]


def generate_synthetic_data(eco):
    sample_phrases = {
        'analyze:': [
            'analyze',
            'run analysis',
            'suggest a move',
            'recommend a move',
            'what is the best move',
        ],
        'play:':[
            'play',
            'play it',
            'play move',
            'play opening',
        ],
        'setup:': [
            'setup',
            'set it up',
            'set up the board',
            'set position',
        ],
    }

    # Add phrases for puzzle themes.
    for theme in all_puzzle_themes:
        key = 'puzzle:' + theme
        theme = ' '.join(camel_case_tokenize(theme))
        sample_phrases[key] = [
            theme,
            f'practice {theme}',
            f'practice {theme}',
            f'solve {theme}',
            f'solve {theme}',
        ]

    # Add phrases for openings.
    unique_names = set()
    for key in eco.by_name:
        for part in eco.by_name[key]['name'].split(':'):
            unique_names.add(part)

    for opening_name in unique_names:
        sample_phrases[f'search:{opening_name}'] = generate_combinatorial_variations(opening_name)

    synthetic_data = []
    for intent, phrases in sample_phrases.items():
        for phrase in phrases:
            synthetic_data.append((phrase, intent))

    Logger.debug(f'Generated {len(synthetic_data)} samples.')
    return synthetic_data


def main():
    parser = argparse.ArgumentParser(description='Train the Intent Classifier')
    parser.add_argument('--model-name', default='intent-model', help='Base name for saving the model')

    args = parser.parse_args()
    Logger.setLevel(LOG_LEVELS['debug'])
    data = generate_synthetic_data(ECO())

    classifier = IntentClassifier()
    classifier.train(data)
    classifier.save(args.model_name)


if __name__ == '__main__':
    main()
