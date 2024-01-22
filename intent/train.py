#!/usr/bin/env python3
"""
Generate syntehtic data and train an IntentClassifier.
Data is specific to the Chess App.
Save the model to a specified folder (default is 'intent-model').

TODO: Compress the model by using embeddings.
"""
import argparse
import itertools
import numpy as np
import os
import sys

os.environ['KIVY_NO_ARGS']='1'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from intent import IntentClassifier
from kivy.logger import Logger, LOG_LEVELS
from opening import ECO
from puzzleview import themes_dict as puzzle_themes, PuzzleCollection

all_puzzle_themes =  { k for k in puzzle_themes if PuzzleCollection().filter(k) }


alt_word_forms = {
    "search": ["what is", "lookup" ],
}

def alternative_words(word):
    variations = []
    if word in alt_word_forms:
        variations += alt_word_forms[word]

    return variations


def generate_combinatorial_variations(sentence):

    words = sentence.split()
    word_variations = [[word] + alternative_words(word) for word in words]

    # Generate combinatorial variations of the sentence
    sentence_variations = set(
        ' '.join(combination) for combination in itertools.product(*word_variations)
    )
    for s in sentence_variations:
        Logger.debug(f'search: {s}')

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


def check_capitalized_words(s, except_words):
    for word in s.split():
        if word[0].isupper() and word not in except_words:
            return True
    return False


def generate_synthetic_data(eco):
    sample_phrases = {
        'analyze': [
            'analyze',
            'run analysis',
            'suggest a move',
            'recommend a move',
            'recommend a good move',
            'what is the best move',
            'what is a good move',
            'what is a good move in the current situation',
            'what is a good move in this position?',
            'what is the danger',
            'move recommendation?',
            'recommendation',
            'make a recommendation',
            'find the best move',
            'find me a good move',
            'help me find a move',
            'move suggestion',
            'good move suggestion',
            'good move recommendation',
            'good move ideas',
            'suggest a good move',
            'suggest the best move',
            'suggest an idea',
            'make a move suggestion',
            'recommendations, please',
            'suggestions?',
            'any suggestions?',
            'any ideas?',
            'suggestion please',
            'what would Bobby do',
            'what would Magnus do',
            'ideas, please',
            'have any ideas?',
            'do you have any good ideas',
            'give me an idea',
            'give me some ideas',
            'do you have any idea for what to do',
        ],
        # Examples of unhandled / unknown intents:
        'None':[
            'any other idea',
            'any more ideas',
            'anyhow',
            'anyone',
            'anything',
            'anything else',
            'anywhere',
            'anywho',
            'greetings and salutations',
            'good bye',
            'bye',
            'buy me a coffee and a sandwich',
            'hold that thought',
            "Albert's Hall",
            'halloween',
            'hall of fame',
            'hello',
            'hello hello',
            'hello world',
            'hell of a move',
            'hello world',
            'like that',
            'like to see',
            'list variations',
            'show',
            'show the move',
            'show variations',
            'what',
            'what are',
            'what other',
            'what move',
            'what opening',
            'what is',
            'where',
            'why',
            'who',
            'where is',
            'why is',
            'who is',
            'where is this',
            'why is this',
            'who is this',
            'where is that',
            'why is that',
            'who is that',
            'where are',
            'why are',
            'who are',
            'recommend a puzzle',
            'recommend what to practice',
            'recommend a good puzzle',
            'any fun puzzle',
            'suggest a fun puzzle',
            'give me a problem',
            'show me a problem or a puzzle',
            'load it up',
            'let us see that',
            #'I would like to see',
            'lucky move',
            'recommend to study',
            'make the move',
            'make that move',
            'move it',
            'play',
            'play it',
            'play move',
            'play opening',
        ],
    }

    # Add phrases for puzzle themes.
    for theme in all_puzzle_themes:
        key = 'puzzle:' + theme
        description = puzzle_themes[theme].lower()
        theme = ' '.join(camel_case_tokenize(theme))

        sample_phrases[key] = [
            theme,
            f"{description} puzzle",
            f"practice {description}",
            f"study {description}",
            f"I want to practice {theme}",
            f"I would like to practice {theme}",
            f"practice {theme}",
            f"study {theme}",
            f"let us solve {theme}",
            f"let us practice {theme}",
        ]
    for k, phrases in sample_phrases.items():
        if k.startswith('puzzle:'):
            for p in phrases:
                Logger.debug(f'puzzle: {p}')

    # Add phrases for openings.
    unique_names = {}
    except_words = {
        'Classical',
        'Closed',
        'Line',
        'Neo-Classical',
        'Orthodox',
        'System',
        'Traditional',
        'Variation',
    }
    def split_and_flatten(s):
        return [item.strip() for part in s.split(':') for item in part.split(',')]

    for eco, rows in eco.by_eco.items():
        for r in rows:
            # for part in r['name'].split(':'):
            for part in split_and_flatten(r['name']):
                if not check_capitalized_words(part, except_words):
                    continue
                unique_names[part.strip().lower()] = eco

    for name, eco in unique_names.items():
        key = f'search:{name}:{eco}'
        sample_phrases[key] = (
            generate_combinatorial_variations(name) +
            generate_combinatorial_variations('search ' + name)
        )
        if not 'variations' in name:
            sample_phrases[key] += generate_combinatorial_variations('variations of ' + name)

        key = f'open:{name}:{eco}'
        sample_phrases[key] = (
            generate_combinatorial_variations("let's play " + name) +
            generate_combinatorial_variations("I'd like to play " + name) +
            generate_combinatorial_variations("Set up the " + name)
        )

    synthetic_data = []
    for intent, phrases in sample_phrases.items():
        for phrase in phrases:
            synthetic_data.append((phrase, intent))

    Logger.debug(f'generated: {len(synthetic_data)} samples.')
    return synthetic_data


def main():
    parser = argparse.ArgumentParser(description='Train the Intent Classifier')
    parser.add_argument('--model-name', default='intent-model', help='Base name for saving the model')

    args = parser.parse_args()
    Logger.setLevel(LOG_LEVELS['debug'])
    data = generate_synthetic_data(ECO())

    classifier = IntentClassifier(annoy_trees=8, min_word_freq=3)
    classifier.train(sorted(set(data)))
    classifier.save(args.model_name)


if __name__ == '__main__':
    main()
