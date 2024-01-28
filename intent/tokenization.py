# https://huggingface.co/learn/nlp-course/chapter6/5?fw=pt

from collections import defaultdict
from metaphone import doublemetaphone
import pickle
import re

DIGIT_WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine']

def preprocess_digits(token):
    ''' Convert each digit in the token to its word equivalent. '''
    if token.isdigit():
        return ''.join(DIGIT_WORDS[int(digit)] for digit in token)
    return token

class BytePairEncoding:
    def __init__(self):
        self.merges = None
        self.vocab = None
        self.use_metaphone = False

    def build(self, corpus, *, use_metaphone, vocab_size):
        self.use_metaphone = use_metaphone
        self.merges = {}
        word_freqs = self._build_word_freqs(corpus)
        self.vocab = sorted(list({c for word in word_freqs.keys() for c in word}))
        splits = {word: [c for c in word] for word in word_freqs.keys()}

        while len(self.vocab) < vocab_size:
            pair_freqs = self._compute_pair_freqs(word_freqs, splits)
            best_pair = None
            max_freq = -1
            for pair, freq in pair_freqs.items():
                if max_freq < freq:
                    best_pair = pair
                    max_freq = freq
            self._merge_pair(*best_pair, splits, word_freqs.keys())
            top_2 = best_pair[0] + best_pair[1]
            self.merges[best_pair] = top_2
            self.vocab.append(top_2)

    def save(self, filename):
        with open(filename, 'wb') as file:
            pickle.dump(self, file)

    @staticmethod
    def load(filename):
        with open(filename, 'rb') as file:
            return pickle.load(file)

    def _build_word_freqs(self, corpus):
        freqs = defaultdict(int)
        for word in self._pretokenize(corpus):
            freqs[word] += 1
        return freqs

    @staticmethod
    def _compute_pair_freqs(word_freqs, splits):
        pair_freqs = defaultdict(int)
        for word, freq in word_freqs.items():
            split = splits[word]
            if len(split) == 1:
                continue
            for i in range(len(split) - 1):
                pair = (split[i], split[i + 1])
                pair_freqs[pair] += freq
        return pair_freqs

    @staticmethod
    def _merge_pair(a, b, splits, key_words):
        for word in key_words:
            split = splits[word]
            if len(split) == 1:
                continue
            splits[word] = BytePairEncoding._merge_split(a, b, split)

    @staticmethod
    def _merge_split(a, b, split):
        i = 0
        while i < len(split) - 1:
            if split[i] == a and split[i + 1] == b:
                split = split[:i] + [a + b] + split[i + 2 :]
            else:
                i += 1
        return split

    def _pretokenize(self, text):
        tokenizer_regex = r'\w+|[^\w\s]'
        tokens = re.findall(tokenizer_regex, text)
        tokens = [preprocess_digits(token.lower()) for token in tokens]
        if self.use_metaphone:
            tokens = [m for tok in tokens for m in doublemetaphone(tok)]
        return tokens

    def tokenize(self, text):
        pre_tokenized_text = self._pretokenize(text)
        splits = [[c for c in word] for word in pre_tokenized_text]
        for pair, merge in self.merges.items():
            for i, split in enumerate(splits):
                splits[i] = self._merge_split(pair[0], pair[1], split)
        return sum(splits, [])
