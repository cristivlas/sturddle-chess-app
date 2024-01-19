#!/usr/bin/env python3
import argparse
import os
os.environ['KIVY_NO_ARGS'] = '1'
import jstyleson as json
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from intent import IntentClassifier


def load_test_data(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

def run_tests(model_path, test_data_path):
    # Load model
    classifier = IntentClassifier()
    classifier.load(model_path)

    # Load test data
    test_cases = load_test_data(test_data_path)

    # Run tests
    for case in test_cases:
        input_text = case['input']
        expected = case['expected']
        result = classifier.classify_intent(input_text)
        result = ':'.join(result[0][0].split(':')[:2]) if result else 'None'
        assert result == expected, f'Failed test for input: "{input_text}". Expected: "{expected}", Got: "{result}"'

    print('All tests passed successfully.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Test IntentClassifier models')
    parser.add_argument('model', help='Path to the IntentClassifier model')
    parser.add_argument('--expected', required=True, help='Path to the test data file')
    
    args = parser.parse_args()
    run_tests(args.model, args.expected)
