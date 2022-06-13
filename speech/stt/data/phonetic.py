# phonetic alternatives for chessboard file names
file_mapping = {
    'a': ['ay', 'alpha'],
    'b': ['bee', 'bravo'],
    'c': ['cee', 'charlie'],
    'd': ['dee', 'delta'],
    'e': ['ee', 'eey', 'echo'],
    'f': ['ef', 'eff', 'foxtrot'],
    'g': ['gee', 'golf'],
    'h': ['aitch', 'hotel'],
}

file_reverse = {y:x for x in file_mapping.keys() for y in file_mapping[x]}
