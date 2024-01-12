import json
import os
import re
import numpy as np
import pickle

from annoy import AnnoyIndex
from metaphone import doublemetaphone


class Dictionary:
    def __init__(self, documents=[]):
        self.word2idx = {}
        self.idx2word = []
        if documents:
            self.add_documents(documents)

    def add_documents(self, documents):
        for doc in documents:
            for word in doc:
                if word not in self.word2idx:
                    self.idx2word.append(word)
                    self.word2idx[word] = len(self.idx2word) - 1

    def doc2bow(self, document):
        return [self.word2idx[word] for word in document if word in self.word2idx]

    def __len__(self):
        # assert len(self.word2idx) == len(self.idx2word)
        return len(self.idx2word)


class TfidfModel:
    def __init__(self, corpus, dictionary):
        self.dictionary = dictionary
        self.idf = self._calculate_idf(corpus)

    def _calculate_idf(self, corpus):
        num_docs = len(corpus)
        idf = np.zeros(len(self.dictionary.idx2word))
        for word_idx in range(len(self.dictionary.idx2word)):
            df = sum(word_idx in doc for doc in corpus)
            idf[word_idx] = np.log(num_docs / (1 + df)) if df else 0
        return idf

    def transform(self, bow_doc):
        tfidf = np.zeros(len(self.dictionary.idx2word))
        word_counts = np.bincount(bow_doc)
        for word_idx in range(len(word_counts)):
            tf = word_counts[word_idx]
            tfidf[word_idx] = tf * self.idf[word_idx]
        return tfidf


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
        return custom_preprocess(text)

    def train(self, data):
        '''Trains the classifier with the provided data.'''
        processed_data = [(self.preprocess(text), label) for text, label in data]

        # Feature Extraction
        self.dictionary = Dictionary([text for text, label in processed_data])
        bow_corpus = [self.dictionary.doc2bow(text) for text, label in processed_data]

        # Create a TF-IDF model
        self.tfidf_model = TfidfModel(bow_corpus, self.dictionary)

        # Convert sparse TF-IDF vectors to dense format
        dense_tfidf_corpus = [self.tfidf_model.transform(doc) for doc in bow_corpus]

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
            query = query.lower()
            # Hack
            keywords = ['find', 'look up', 'lookup', 'search', 'what is']
            for k in keywords:
                if query.startswith(k):
                    query = query[len(k):].strip()
                    break

            preprocessed_query = self.preprocess(query)
            query_bow = self.dictionary.doc2bow(preprocessed_query)
            query_tfidf = self.tfidf_model.transform(query_bow)

            # Get the nearest neighbor and its distance
            results = self.annoy_index.get_nns_by_vector(query_tfidf, top_n, include_distances=True)
            if results:
                return [(self.index_to_intent[i], d) for i,d in zip(*results) if d < threshold]

    def save(self, path):
        '''Saves the model components to the specified path.'''
        if not os.path.exists(path):
            os.makedirs(path)

        # Save the custom dictionary
        with open(f'{path}/dictionary.json', 'w') as f:
            json.dump(self.dictionary.word2idx, f)

        # Save TF-IDF idf values
        np.save(f'{path}/tfidf_idf.npy', self.tfidf_model.idf)

        # Save Annoy index
        self.annoy_index.save(f'{path}/annoy_index.ann')

        # Save index to intent mapping
        with open(f'{path}/index_to_intent.pkl', 'wb') as f:
            pickle.dump(self.index_to_intent, f)

    def load(self, path):
        '''Loads the model components from the specified path.'''
        if os.path.exists(path):
            # Load the custom dictionary
            with open(f'{path}/dictionary.json', 'r') as f:
                word2idx = json.load(f)
                self.dictionary = Dictionary()
                self.dictionary.word2idx = word2idx
                self.dictionary.idx2word = [None] * len(word2idx)
                for word, idx in word2idx.items():
                    self.dictionary.idx2word[idx] = word

            # Load TF-IDF idf values
            idf = np.load(f'{path}/tfidf_idf.npy')
            self.tfidf_model = TfidfModel([], self.dictionary)
            self.tfidf_model.idf = idf

            # Load Annoy index
            self.dim = len(self.dictionary.idx2word)
            self.annoy_index = AnnoyIndex(self.dim, 'angular')
            self.annoy_index.load(f'{path}/annoy_index.ann')

            # Load index to intent mapping
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
