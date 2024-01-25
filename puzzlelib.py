import xml.etree.ElementTree as ET

# Based on:
# https://github.com/lichess-org/lila/blob/master/translation/source/puzzleTheme.xml

__xml = '''<?xml version="1.0" encoding="UTF-8"?>
<themes>
<string name="advancedPawn">A pawn deep in enemy territory, possibly promoting soon.</string>
<string name="advantage">Gain a decisive advantage (between 200cp and 600cp).</string>
<string name="anastasiaMate">A knight and rook or queen trap the king between the board edge and a friendly piece.</string>
<string name="arabianMate">A knight and rook trap the king in a board corner.</string>
<string name="attackingF2F7">Attack targeting f2 or f7 pawn, e.g., in the fried liver opening.</string>
<string name="attraction">Exchange or sacrifice, forcing an opponent piece to a vulnerable square.</string>
<string name="backRankMate">Checkmate king on home rank, trapped by its pieces.</string>
<string name="bishopEndgame">Endgame with bishops and pawns only.</string>
<string name="bodenMate">Two bishops on criss-crossing diagonals mate a king blocked by friendly pieces.</string>
<string name="castling">Secure king and deploy rook for attack.</string>
<string name="capturingDefender">Remove a defending piece to capture another undefended piece.</string>
<string name="doubleBishopMate">Two bishops on adjacent diagonals mate a king blocked by friendly pieces.</string>
<string name="dovetailMate">Queen mates adjacent king with escape squares blocked by friendly pieces.</string>
<string name="equality">Recover from losing position, achieve draw or balance.</string>
<string name="kingsideAttack">Kingside attack.</string>
<string name="clearance">Clear square, file, or diagonal for a tactical idea.</string>
<string name="defensiveMove">Avoid losing material or advantage.</string>
<string name="deflection">Distract an opponent piece from guarding key square. Aka "overloading".</string>
<string name="discoveredAttack">Use a discovered attack by moving a blocking piece.</string>
<string name="doubleCheck">Check with two pieces after a discovered attack.</string>
<string name="enPassant">Capture an opponent pawn bypassing with en passant rule.</string>
<string name="exposedKing">Tactic with a poorly defended king, often leading to checkmate.</string>
<string name="fork">Attack two opponent pieces at once.</string>
<string name="hangingPiece">Tactic with an undefended opponent piece, free to be captured.</string>
<string name="hookMate">Checkmate with rook, knight, pawn, and enemy pawn limiting king escape.</string>
<string name="interference">Move piece between opponent pieces, leaving one or both undefended.</string>
<string name="intermezzo">Play immediate threat before expected move. Aka "Zwischenzug" or "In between".</string>
<string name="knightEndgame">Endgame with knights and pawns only.</string>
<string name="mateIn1">Checkmate in one move.</string>
<string name="mateIn2">Checkmate in two moves.</string>
<string name="mateIn3">Checkmate in three moves.</string>
<string name="mateIn4">Checkmate in four moves.</string>
<string name="mateIn5">Solve a long mating sequence.</string>
<string name="middlegame">A tactic during the second phase of the game.</string>
<string name="oneMove">One-move puzzle.</string>
<string name="pawnEndgame">Endgame with only pawns.</string>
<string name="pin">Piece unable to move without exposing higher value piece to attack.</string>
<string name="promotion">Promote a pawn to queen or minor piece.</string>
<string name="queenEndgame">Endgame with queens and pawns only.</string>
<string name="queenRookEndgame">Endgame with queens, rooks, and pawns only.</string>
<string name="queensideAttack">Queenside attack.</string>
<string name="quietMove">Neither check or capture, prepare hidden threat.</string>
<string name="rookEndgame">Endgame with rooks and pawns only.</string>
<string name="sacrifice">Give up material for advantage after forced moves.</string>
<string name="skewer">High value piece attacked, revealing lower value piece behind it. Inverse of pin.</string>
<string name="smotheredMate">Knight checkmates king surrounded by its pieces.</string>
<string name="trappedPiece">Piece unable to escape capture due to limited moves.</string>
<string name="underPromotion">Promote to knight, bishop, or rook.</string>
<string name="xRayAttack">Piece attacks or defends through an enemy piece.</string>
<string name="zugzwang">Opponent's moves worsen their position.</string>
</themes>
'''

# Parse the XML file and convert it into a Python dictionary
themes_dict = {}
for child in ET.fromstring(__xml):
    key = child.attrib['name']
    value = child.text
    themes_dict[key] = value


def puzzle_description(puzzle):
    assert len(puzzle) >= 4, puzzle
    theme_list = puzzle[-1].split()

    description = ''
    for key in theme_list:
        if key in themes_dict:
            description += themes_dict[key] + '\n'

    return description.strip()


class PuzzleCollection:
    puzzle_list = []

    def __init__(self):
        self._puzzles = self.puzzle_list

    @staticmethod
    def _parse():
        from puzzles import puzzles as epd
        i = 0
        for fields in epd.split('\n'):
            if not fields:
                continue # skip empty lines
            fields = fields.split(';')
            tokens = fields[0]
            if ' bm ' in tokens:
                tokens = tokens.split(' bm ')
            elif ' am ' in tokens:
                tokens = tokens.split(' am ')

            fen = tokens[0]
            solutions = tokens[1].strip().split(' ')
            id = None
            for f in fields:
                f = f.strip()
                if f.startswith('id '):
                    id = f.split('id ')[1]
                    break
            i += 1
            PuzzleCollection.puzzle_list.append((id, fen, solutions, i, fields[-1]))

        for p in PuzzleCollection.puzzle_list:
            assert puzzle_description(p)

    @property
    def count(self):
        return len(self._puzzles)

    def get(self, start, count):
        return self._puzzles[start : start + count]

    def filter(self, theme):
        return [p for p in self._puzzles if theme in p[-1]]


PuzzleCollection._parse()
