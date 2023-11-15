import chess
import chess.pgn
import io
import itertools
import re

from speech.nlp import describe_move


def find_moves(text):
    mark = '1.'
    start, end = text.find(mark), -1

    if start >= 0:
        i = start + len(mark)
        for n in itertools.count(2):
            mark = f'{n}.'
            j = text.find(mark, i)
            if j < 0:
                break
            i = j + len(mark)

        for delim in ')., ':
            end = text.find(delim, i)
            if end >= 0:
                break

    return text[start:end]


def describe_sequence(text, epd=None):
    moves = []

    if epd:
        text = f'[FEN "{epd}"]\n{text}'

    game = chess.pgn.read_game(io.StringIO(text))
    if game:
        # Iterate through all moves and play them on a board.
        board = game.board()
        for move in game.mainline_moves():
            # Collect move descriptions in English
            moves.append(
                describe_move(
                    board,
                    move,
                    announce_check=True,
                    announce_capture=True,
                    spell_digits=True
                ))
            board.push(move)

        return ', '.join(moves)


def substitutions(text, epd=None):
    '''
    Find sequences of moves that can be substituted with spoken descriptions.
    Return dictionary of substitutions.
    '''
    fragments = re.split(' move | moves | \(|:|"', text)
    substs = {}
    for f in fragments:
        moves = find_moves(f)
        if moves:
            descr = describe_sequence(moves, epd)
            if descr:
                substs[moves] = descr
    return substs


def transcribe_moves(text):
    '''
    Replace chess moves in the text with their spoken equivalents.
    '''
    for old, new in substitutions(text).items():
        text = text.replace(old, new, 1)

    return text


def test_transcribe_moves():
    test_cases = [
        [(
            'Sicilian Defense, Dragon Variation is a sharp and aggressive opening that leads to '
            'complex and tactical positions. It begins with the moves 1. e4 c5 2. Nf3 d6 3. d4 cxd4 '
            '4. Nxd4 Nf6 5. Nc3 g6. Enjoy your game with this exciting variation!'
        ),
        (
            'Sicilian Defense, Dragon Variation is a sharp and aggressive opening that leads to '
            'complex and tactical positions. It begins with the moves pawn to E four, pawn to C '
            'five, knight to F three, pawn to D six, pawn to D four, pawn takes pawn on D four, knight '
            'takes pawn on D four, knight to F six, knight to C three, pawn to G six Enjoy your game '
            'with this exciting variation!'
        )
        ],
        [(
            "Gambits are aggressive openings where a player sacrifices material for rapid "
            "development and attacking chances. Some popular gambits to practice include "
            "the King's Gambit (1.e4 e5 2.f4), the Queen's Gambit (1.d4 d5 2.c4), and the "
            "Evans Gambit (1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.b4)."
        ),
        (
            "Gambits are aggressive openings where a player sacrifices material for rapid "
            "development and attacking chances. Some popular gambits to practice include "
            "the King's Gambit (pawn to E four, pawn to E five, pawn to F four), "
            "the Queen's Gambit (pawn to D four, pawn to D five, pawn to C four), "
            "and the Evans Gambit (pawn to E four, pawn to E five, knight to F three, knight to C six, "
            "bishop to C four, bishop to C five, pawn to B four)."
        )
        ],
        [(
            "The Albin's Countergambit is a response to the Queen\'s Gambit that begins with the moves "
            "1. d4 d5 2. c4 e5. It is a sharp and aggressive way for Black to counter the Queen\'s Gambit "
            "and create imbalances in the position."
        ),
        (
            "The Albin's Countergambit is a response to the Queen's Gambit that begins with the moves "
            "pawn to D four, pawn to D five, pawn to C four, pawn to E five. It is a sharp and aggressive "
            "way for Black to counter the Queen's Gambit and create imbalances in the position."
        )
        ],
        [   "1. e4 g6 2. Bc4 Bg7 3. Qf3 e6 4. d4 Bxd4.",
        (
            "pawn to E four, pawn to G six, bishop to C four, bishop to G seven, queen to F three, "
            "pawn to E six, pawn to D four, bishop takes pawn on D four."
        )
        ],
        [
            "1. a3 e5\n2. b3 d5\n3. c3 Nf6\n4. d3 Nc6\n5. e3 Bd6\n6. f3 O-O\n7. g3.",
            (
                "pawn to A three, pawn to E five, pawn to B three, pawn to D five, "
                "pawn to C three, knight to F six, pawn to D three, knight to C six, "
                "pawn to E three, bishop to D six, pawn to F three, castle king side, pawn to G three."
            )
        ],
        [(
            "The King's Gambit is an aggressive chess opening that begins with the moves 1.e4 e5 2.f4. "
            "White sacrifices a pawn to gain rapid development and open lines for attacking the black king. "
            "The King's Gambit is known for its sharp and tactical nature, and it often leads to dynamic and "
            "exciting positions on the board."
        ),
        (
            "The King's Gambit is an aggressive chess opening that begins with the moves pawn to E four, pawn "
            "to E five, pawn to F four. White sacrifices a pawn to gain rapid development and open lines for "
            "attacking the black king. The King's Gambit is known for its sharp and tactical nature, and it often "
            "leads to dynamic and exciting positions on the board."
        )
        ],
    ]

    for test in test_cases:
        t = transcribe_moves(test[0])
        assert t == test[1], f'\n{test[0]}\n{t}\n{test[1]}'


if __name__ == '__main__':
    test_transcribe_moves()
