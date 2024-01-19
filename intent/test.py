import unittest
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from intent import IntentClassifier


class TestIntentClassifier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # This is some example synthetic data
        cls.data = [
            ('analyze position', 'analyze'),
            ('good move', 'analyze'),
            ('search openings', 'search_openings'),
            ('puzzle fork theme', 'lookup_puzzle'),
        ]
        cls.model_path = 'test_model'

        cls.classifier = IntentClassifier()
        cls.classifier.train(cls.data)

    @classmethod
    def tearDownClass(cls):
        # Clean up any saved model files
        for file in [
            'dictionary.json',
            'tfidf_idf.npy',
            'annoy_index.ann',
            'index_to_intent.pkl',
        ]:
            os.remove(os.path.join(cls.model_path, file))
        os.rmdir(cls.model_path)

    def test_train(self):
        # Check if model components are correctly initialized
        self.assertIsNotNone(self.classifier.dictionary)
        self.assertIsNotNone(self.classifier.tfidf_model)
        self.assertIsNotNone(self.classifier.annoy_index)
        self.assertEqual(len(self.classifier.index_to_intent), len(self.data))

    def test_save_and_load(self):
        # Save the model
        self.classifier.save(self.model_path)

        # Load the model in a new classifier instance
        new_classifier = IntentClassifier()
        new_classifier.load(self.model_path)

        # Check if the new classifier has correctly loaded components
        self.assertIsNotNone(new_classifier.dictionary)
        self.assertIsNotNone(new_classifier.tfidf_model)
        self.assertIsNotNone(new_classifier.annoy_index)

    def test_classify_intent(self):
        self.assertIsNotNone(self.classifier.dictionary)

        self.classifier.save(self.model_path)
        self.classifier = IntentClassifier()
        self.classifier.load(self.model_path)

        # Test with a known query
        scored_intent = self.classifier.classify_intent('find a good move')
        self.assertIsNotNone(scored_intent)
        intent, distance = scored_intent[0]
        self.assertIsNotNone(intent)
        self.assertLess(distance, 0.8)  # Assuming the threshold is 0.8
        self.assertEqual(intent, 'analyze')

        # Test with an unknown query
        unknown_intent = self.classifier.classify_intent('unknown query')
        self.assertEqual(unknown_intent, [])

    def test_load_nonexistent(self):
        self.classifier.load('bogus')


if __name__ == '__main__':
    unittest.main()
