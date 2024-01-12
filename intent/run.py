#!/usr/bin/env python3
import argparse
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from intent import IntentClassifier

def main():
    parser = argparse.ArgumentParser(description='Run the Intent Classifier interactively.')
    parser.add_argument(
        '--model-name',
        type=str,
        default='intent-model',
        help='Name of the model to load',
    )
    args = parser.parse_args()

    # Load the model
    classifier = IntentClassifier()
    classifier.load(args.model_name)

    print('Type a query to get its intent. Type "quit" to quit.')

    while True:
        query = input('Enter your query: ')
        if query.lower() == 'quit':
            break
        try:
            print(classifier.classify_intent(query, top_n=3, threshold=1.0))

        except IndexError as e:
            print(f'An error occurred: {e}')
            print("This may be due to a term in the query that wasn't seen during training.")

if __name__ == '__main__':
    main()
