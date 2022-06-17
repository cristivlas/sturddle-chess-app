#
# NLP Tests
#
from collections import namedtuple
from kivy.logger import Logger
import chess

from nlp import NLP

Test = namedtuple('Test', ['fen', 'text', 'moves'])


autocorrect_test_cases = [
    [ 'age 1 to h4', 'h1 to h4' ],
    [ 'be 2 bee 4', 'b2 b4' ],
    [ 'see two to c four', 'c2 to c4'],
    [ 'see 2 to see 4', 'c2 to c4'],
    [ 'the one', 'd1' ],
    [ 'porn to the sex', 'pawn to d6'],
    [ 'might take screen', 'knight takes queen'],
    [ 'e22 e4', 'e2 to e4'],
    [ 'promote the broke', 'promote to rook'],
    [ 'might at see four cakes on every', 'knight at c4 takes on f3'],
    [ 'pornsticks at bee ate', 'pawn takes at b8'],
    [ 'jiwon to esex', 'g1 to e6'],
    [ 'eat  3', 'e3']
]


grammar_test_cases = [
    Test('5rk1/1ppbP2p/p1pb4/6q1/3P1p1r/2P1R2P/PP1BQ1P1/5RKN w - -', 'a2 to a4', ['a2a4']),
    Test('5rk1/1ppbP2p/p1pb4/6q1/3P1p1r/2P1R2P/PP1BQ1P1/5RKN w - -', 'a4', ['a2a4']),
    Test('5rk1/1ppbP2p/p1pb4/6q1/3P1p1r/2P1R2P/PP1BQ1P1/5RKN w - -', 'pawn to a4', ['a2a4']),
    Test('5rk1/1ppbP2p/p1pb4/6q1/3P1p1r/2P1R2P/PP1BQ1P1/5RKN w - -', 'rook to f3', ['e3f3', 'f1f3']),
    Test('5rk1/1ppbP2p/p1pb4/6q1/3P1p1r/2P1R2P/PP1BQ1P1/5RKN w - -', 'rook from e3 to f3', ['e3f3']),
    Test('5rk1/1ppbP2p/p1pb4/6q1/3P1p1r/2P1R2P/PP1BQ1P1/5RKN w - -', 'rook at f1 to f3', ['f1f3']),
    Test('5rk1/1ppbP2p/p1pb4/6q1/3P1p1r/2P1R2P/PP1BQ1P1/5RKN w - -', 'a2 to a5', []),
    Test('5rk1/1ppbP2p/p1pb4/6q1/3P1p1r/2P1R2P/1P1BQ1P1/5RKN w - -', 'a2 a4', []),
    Test('5rk1/1ppbP2p/p1pb4/6q1/3P1p1r/2P1R2P/1P1BQ1P1/5RKN w - -', 'a2 a4', []),
    Test('5rk1/1ppbP2p/p1pb4/6q1/1P1P3r/2P1p2P/3BQ1P1/5RKN w - -', 'bishop takes pawn', ['d2e3']),
    Test('5rk1/1ppbP2p/p1pb4/6q1/1P1P3r/2P1p2P/3BQ1P1/5RKN w - -', 'bishop takes pawn at e3', ['d2e3']),
    Test('5rk1/1ppbP2p/p1pb4/6q1/1P1P3r/2P1p2P/3BQ1P1/5RKN w - -', 'queen takes pawn', ['e2a6', 'e2e3']),
    Test('5rk1/1ppbP2p/p1pb4/6q1/1P1P3r/2P1p2P/3BQ1P1/5RKN w - -', 'queen takes pawn at a6', ['e2a6']),
    Test('5rk1/1ppbP2p/p1pb4/6q1/1P1P3r/2P1p2P/3BQ1P1/5RKN w - -', 'queen takes at a6', ['e2a6']),
    Test('5rk1/1ppbP2p/p1pb4/6q1/1P1P3r/2P1p2P/3BQ1P1/5RKN w - -', 'promote to queen', ['e7f8q', 'e7e8q']),
    Test('5rk1/1ppbP2p/p1pb4/6q1/1P1P3r/2P1p2P/3BQ1P1/5RKN w - -', 'pawn takes rook', ['e7f8q', 'e7f8r', 'e7f8b', 'e7f8n']),
    Test('5rk1/1ppbP2p/p1pb4/6q1/1P1P3r/2P1p2P/3BQ1P1/5RKN w - -', 'pawn takes rook and promotes to queen', ['e7f8q']),
    Test('5rk1/1ppbP2p/p1pb4/6q1/1P1P3r/2P1p2P/3BQ1P1/5RKN w - -', 'e7 e8', ['e7e8q', 'e7e8r', 'e7e8b', 'e7e8n']),
    Test('5rk1/1ppbP2p/p1pb4/6q1/1P1P3r/2P1p2P/3BQ1P1/5RKN w - -', 'pawn to e8', ['e7e8q', 'e7e8r', 'e7e8b', 'e7e8n']),
    Test('5rk1/1ppb3p/p1pb4/6q1/1P1P3r/2P1p1PP/3BQP2/R3K2R w KQ -', 'castle', ['e1g1', 'e1c1']),
    Test('5rk1/1ppb3p/p1pb4/6q1/1P1P3r/2P1p1PP/3BQP2/R3K2R w KQ -', 'castle king side', ['e1g1']),
    Test('5rk1/1ppb3p/p1pb4/6q1/1P1P3r/2P1p1PP/3BQP2/R3K2R w KQ -', 'castle queen side', ['e1c1']),
    Test('r1r4R/5kp1/p2Q4/4pp2/1P2N3/1KP5/1P6/6q1 w - -', 'expect fail g1', []),
    Test('2r5/1P6/8/8/1K3k2/1P6/6p1/6N1 w - -', 'pawn to b8, promote to knight', ['b7b8n']),
    Test('2r5/1P6/8/8/1K3k2/1P6/6p1/6N1 w - -', 'move pawn to b8', ['b7b8q', 'b7b8r', 'b7b8b', 'b7b8n']),
]


batch_test_cases = [
    ('2r5/1P6/8/8/1K3k2/1P6/6p1/6N1 w - -', ['c8', 'promote to queen'], ['b7c8q']),
    ('4k3/4p3/8/8/8/1b6/2P1N3/3K4 w - -', ['knight to c3', 'c3'], ['e2c3']),
    ('4k3/4p3/8/8/8/1b6/2P1N3/3K4 w - -', ['night to C3', 'knight to c3', 'c3', 'c2c3'], ['e2c3']),
    ('r1b1k2r/pp3pbp/1qnp1np1/4p3/2Q1P3/1PN2N2/P1PBBPPP/R3K2R w KQkq -', ['castle', 'castle king side'], ['e1g1']),
    ('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -', ['pawn to', 'pawn to e4', 'onto e 4'], ['e2e4']),
]


def test_grammar(instance, test):
    moves = [move.uci() for move in instance.parse(fen=test.fen, text=test.text)]
    if moves == test.moves:
        Logger.info(f'Ok: {moves}')
    else:
        Logger.error(f'\u001b[31mFailed, moves={moves}, expected={test.moves}')


def test_autocorrect(instance, test):
    result = instance._autocorrect(test[0])
    if result == test[1]:
        Logger.info(f'Ok: {result}')
    else:
        Logger.error(f'\u001b[31mFailed, {result}, expected={test[1]}')


def test_result_batch(instance, test):
    result = [move.uci() for move in instance.run(test[0], test[1])]
    if result == test[2]:
        Logger.info(f'Ok: {result}')
    else:
        Logger.error(f'\u001b[31mFailed, {result}, expected={test[2]}')


if __name__ == '__main__':
    instance = NLP()

    [test_autocorrect(instance, test) for test in autocorrect_test_cases]
    [test_grammar(instance, test) for test in grammar_test_cases]
    [test_result_batch(instance, test) for test in batch_test_cases]