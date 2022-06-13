#! /usr/bin/env python3

# Generate text data for custom deepspeech scorer.
# https://deepspeech.readthedocs.io/en/v0.9.3/Scorer.html
#
from itertools import chain

import chess

import phonetic

rank = [ 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight' ]

def square_name(square, phonetic_var=0):
    if isinstance(square, str):
        name = square
    else:
        name = chess.square_name(square)
    return phonetic.file_mapping[name[0]][phonetic_var] + ' ' + rank[int(name[1])-1]


def gen_captures():
    return [(f'{x} takes {y}') for x in chess.PIECE_NAMES[1:] for y in chess.PIECE_NAMES[1:6]]


def gen_piece_to_square():
    return [(f'{x} to {square_name(y)   }') for x in chess.PIECE_NAMES[1:] for y in chess.SQUARES]


def gen_castling():
    yield('castle')
    yield('castle king side')
    yield('castle queen side')


def gen_promotions():
    for name in chess.PIECE_NAMES[2:6]:
        yield f'promote to {name}'

    for f in 'abcdefgh':
        for r in [0,7]:
            for piece in chess.PIECE_NAMES[2:6]:
                yield(f'{f} {rank[r]} promote to {piece}')
                yield(f'pawn to {f} {rank[r]} promote to {piece}')


def gen_moves():
    board = chess.Board()
    for piece in chess.PIECE_TYPES:
        for square in chess.SQUARES:
            for color in chess.COLORS:
                piece_name = chess.piece_name(piece)
                board.set_piece_at(square, chess.Piece(piece, color))
                for move in board.generate_pseudo_legal_moves():
                    uci = move.uci()
                    to_square = square_name(uci[2:4])
                    yield(f'{square_name(uci[:2])} to {to_square}')
                    yield(f'{piece_name} from {square_name(square)} to {to_square}')
                    yield(f'{piece_name} to {to_square}')
                    yield(f'{piece_name} captures on {to_square}')
                    yield(f'{piece_name} takes at {to_square}')

                    for victim in chess.PIECE_NAMES[1:]:
                        yield(f'{piece_name} takes {victim} at {to_square}')

                board.clear()


def gen_square_names():
    for square in chess.SQUARES:
        yield(square_name(square, phonetic_var=-1))


def main():
    for phrase in sorted(set(chain(
        gen_promotions(),
        gen_captures(),
        gen_castling(),
        gen_piece_to_square(),
        gen_moves(),
        gen_square_names(),
    ))):
        print(phrase)



if __name__ == '__main__':
    main()
