import json
import logging
import os
import re
import numpy as np
import pickle

from annoy import AnnoyIndex
from metaphone import doublemetaphone
from .tokenization import BytePairEncoding

ANNOY_INDEX_FILE = 'annoy_index.ann'
DICTIONARY_FILE = 'dict.json'
TDIDF_FILE = 'tfidf-idf.npy'
TOKENIZER_FILE = 'tokenizer.pkl'

class Dictionary:
    def __init__(self, documents=[], min_word_freq=1):
        self.word2idx = {}
        self.idx2word = []
        self.word_freq = {}
        self.min_word_freq = min_word_freq
        if documents:
            self.add_documents(documents)

    def add_documents(self, documents):
        for doc in documents:
            for word in doc:
                self.word_freq[word] = self.word_freq.get(word, 0) + 1

        for word, freq in self.word_freq.items():
            if freq >= self.min_word_freq:
                self.idx2word.append(word)
                self.word2idx[word] = len(self.idx2word) - 1

    def doc2bow(self, document):
        return [self.word2idx[word] for word in document if word in self.word2idx]

    def __len__(self):
        assert len(self.word2idx) == len(self.idx2word)
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

    def transform(self, bow_doc, min_tfidf=0.01):
        tfidf = np.zeros(len(self.dictionary.idx2word))
        word_counts = np.bincount(bow_doc, minlength=len(self.dictionary.idx2word))
        for word_idx in range(len(word_counts)):
            tf = word_counts[word_idx]
            tfidf_val = tf * self.idf[word_idx]
            if tfidf_val >= min_tfidf:
                tfidf[word_idx] = tfidf_val
        return tfidf


class IntentClassifier:
    def __init__(self, annoy_trees=32, min_word_freq=1):
        self.dictionary = None
        self.tfidf_model = None
        self.annoy_index = None
        self.index_to_intent = None
        self.dim = 0
        self.annoy_trees = annoy_trees
        self.min_word_freq = min_word_freq
        self.tokenizer = BytePairEncoding()

    def preprocess(self, text, phonetic=True):
        '''Preprocesses the input text by tokenizing and normalizing.'''

        normalizations = {
            # Compounded words and corrections.
            r'counter[-\s]?gambit': 'countergambit',
            r'hyper[-\s]?accelerated': 'hyperaccelerated',
            r'end[-\s]?games?': 'endgame',
            r'ortho[ -](\w+)': r'ortho\1',
            r'orto[ -](\w+)': r'ortho\1',
            r'look[-\s]?up': 'lookup',
            r'set[-\s]?up': 'setup',

            # Contractions.
            r"what's": "what is",
            r"who's": "who is",
            r"where's": "where is",
            r"when's": "when is",
            r"how's": "how is",
            r"there's": "there is",
            r"it's": "it is",
            r"he's": "he is",
            r"she's": "she is",
            r"that's": "that is",
            r"I'd": "I would",
            r"let's": "let us",
            r"'s": "",
        }
        for pattern, replacement in normalizations.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        return self.tokenizer.tokenize(text)

    def train(self, data):
        self.tokenizer.build(corpus=''.join([text for text, _ in data]), use_metaphone=True, vocab_size=800)
        processed_data = [(self.preprocess(text), label) for text, label in data]

        # Feature Extraction
        self.dictionary = Dictionary([text for text, label in processed_data], min_word_freq=self.min_word_freq)
        bow_corpus = [self.dictionary.doc2bow(text) for text, label in processed_data]

        # Create a TF-IDF model
        self.tfidf_model = TfidfModel(bow_corpus, self.dictionary)

        # Convert sparse TF-IDF vectors to dense format
        dense_tfidf_corpus = [self.tfidf_model.transform(doc) for doc in bow_corpus]

        # Build an Annoy Index
        self.dim = len(self.dictionary)
        self.annoy_index = AnnoyIndex(self.dim, 'angular')

        for i, vec in enumerate(dense_tfidf_corpus):
            self.annoy_index.add_item(i, vec)

        self.annoy_index.build(self.annoy_trees)

        # Map index to intents
        self.index_to_intent = {i: label for i, (_, label) in enumerate(processed_data)}

    def classify_intent(self, query, *, top_n=1, threshold=1.0):
        '''Classifies the intent of a given query.'''
        if self.dictionary:
            preprocessed_query = self.preprocess(query)
            query_bow = self.dictionary.doc2bow(preprocessed_query)
            query_tfidf = self.tfidf_model.transform(query_bow)

            # Get the nearest neighbor and its distance
            k = max(10000, top_n * self.annoy_index.get_n_trees())
            results = self.annoy_index.get_nns_by_vector(query_tfidf, top_n, search_k=k, include_distances=True)
            if results:
                return [(self.index_to_intent[i], d) for i,d in zip(*results) if d < threshold]
        return []

    def save(self, path):
        '''Saves the model components to the specified path.'''
        if not os.path.exists(path):
            os.makedirs(path)

        with open(os.path.join(path, DICTIONARY_FILE), 'w') as f:
            json.dump(self.dictionary.word2idx, f)

        np.save(os.path.join(path, TDIDF_FILE), self.tfidf_model.idf)

        self.annoy_index.save(os.path.join(path, ANNOY_INDEX_FILE))
        with open(os.path.join(path, 'index_to_intent.pkl'), 'wb') as f:
            pickle.dump(self.index_to_intent, f)

        self.tokenizer.save(os.path.join(path, TOKENIZER_FILE))

    def load(self, path):
        '''Loads the model components from the specified path.'''
        if not os.path.exists(path):
            logging.warning(f'intent-model: "{path}" does not exist')
        else:
            with open(os.path.join(path, DICTIONARY_FILE), 'r') as f:
                word2idx = json.load(f)
                self.dictionary = Dictionary()
                self.dictionary.word2idx = word2idx
                self.dictionary.idx2word = [None] * len(word2idx)
                for word, idx in word2idx.items():
                    self.dictionary.idx2word[idx] = word

            idf = np.load(os.path.join(path, TDIDF_FILE))
            self.tfidf_model = TfidfModel([], self.dictionary)
            self.tfidf_model.idf = idf

            self.dim = len(self.dictionary.idx2word)
            self.annoy_index = AnnoyIndex(self.dim, 'angular')
            self.annoy_index.load(os.path.join(path, ANNOY_INDEX_FILE))

            with open(os.path.join(path, 'index_to_intent.pkl'), 'rb') as f:
                self.index_to_intent = pickle.load(f)

            self.tokenizer = BytePairEncoding.load(os.path.join(path, TOKENIZER_FILE))
