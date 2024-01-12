import gensim
import os
import re
import pickle

from annoy import AnnoyIndex
from gensim.corpora import Dictionary
from gensim.models import TfidfModel

from metaphone import doublemetaphone


class IntentClassifier:
    def __init__(self, annoy_trees=10):
        self.dictionary = None
        self.tfidf_model = None
        self.annoy_index = None
        self.index_to_intent = None
        self.dim = 0
        self.annoy_trees = annoy_trees

    def preprocess(self, text):
        '''Preprocesses the input text by tokenizing and normalizing.'''
        # return gensim.utils.simple_preprocess(text)
        return custom_preprocess(text)

    def train(self, data):
        '''Trains the classifier with the provided data.'''
        processed_data = [(self.preprocess(text), label) for text, label in data]

        # Feature Extraction
        self.dictionary = Dictionary([text for text, label in processed_data])
        bow_corpus = [self.dictionary.doc2bow(text) for text, label in processed_data]

        # Create a TF-IDF model
        self.tfidf_model = TfidfModel(bow_corpus)
        tfidf_corpus = [self.tfidf_model[doc] for doc in bow_corpus]

        # Convert sparse TF-IDF vectors to dense format
        dense_tfidf_corpus = [gensim.matutils.sparse2full(doc, len(self.dictionary)) for doc in tfidf_corpus]

        # Building an Annoy Index
        self.dim = len(self.dictionary)
        self.annoy_index = AnnoyIndex(self.dim, 'angular')

        for i, vec in enumerate(dense_tfidf_corpus):
            self.annoy_index.add_item(i, vec)

        self.annoy_index.build(self.annoy_trees)

        # Mapping index to intents
        self.index_to_intent = {i: label for i, (_, label) in enumerate(processed_data)}

    def classify_intent(self, query, *, top_n=1, threshold=1.0):
        '''Classifies the intent of a given query.'''
        if self.dictionary:

            # Hack
            keywords = ['find', 'look up', 'lookup', 'search', 'what is']
            for k in keywords:
                if query.startswith(k):
                    query = query[len(k):].strip()
                    break

            preprocessed_query = self.preprocess(query)
            query_bow = self.dictionary.doc2bow(preprocessed_query)
            query_tfidf = gensim.matutils.sparse2full(self.tfidf_model[query_bow], self.dim)

            # Get the nearest neighbor and its distance
            results = self.annoy_index.get_nns_by_vector(query_tfidf, top_n, include_distances=True)
            if results:
                return [(self.index_to_intent[i], d) for i,d in zip(*results) if d < threshold]

    def save(self, path):
        '''Saves the model components to the specified path.'''
        if not os.path.exists(path):
            os.makedirs(path)

        self.dictionary.save(f'{path}/dictionary.pkl')
        self.tfidf_model.save(f'{path}/tfidf_model.pkl')
        self.annoy_index.save(f'{path}/annoy_index.ann')

        with open(f'{path}/index_to_intent.pkl', 'wb') as f:
            pickle.dump(self.index_to_intent, f)

    def load(self, path):
        '''Loads the model components from the specified path.'''

        if os.path.exists(path):
            self.dictionary = Dictionary.load(f'{path}/dictionary.pkl')
            self.tfidf_model = TfidfModel.load(f'{path}/tfidf_model.pkl')

            # Set the correct dimension before initializing AnnoyIndex
            self.dim = len(self.dictionary)

            self.annoy_index = AnnoyIndex(self.dim, 'angular')
            self.annoy_index.load(f'{path}/annoy_index.ann')

            with open(f'{path}/index_to_intent.pkl', 'rb') as f:
                self.index_to_intent = pickle.load(f)


digit_words = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine']

def preprocess_and_mark_digits(token):
    if token.isdigit():
        # Convert each digit in the token to its word equivalent
        return ''.join(digit_words[int(digit)] for digit in token)
    # return token
    return doublemetaphone(token)[0]

def custom_preprocess(text):
    # Tokenize, keep digits and mark them
    tokens = re.findall(r'\b\d+\b|\w+', text)  # Split on word boundaries, keep digits
    return [preprocess_and_mark_digits(token.lower()) for token in tokens]
