import re
from num2words import num2words

# Regular expression for chess moves in SAN
# \b: Word boundary to ensure we're capturing full moves.
# (?:[1-9][0-9]*\.\s*)?: Non-capturing group for optional move numbers (e.g., "1." or "12.") followed by a space.
# ([KQBNR]?[a-h1-8]?x?[a-h][1-8](?:=[QRBN])?):
#   - [KQBNR]?: Optional piece notation (K for King, Q for Queen, B for Bishop, N for Knight, R for Rook). If omitted, it implies a Pawn.
#   - [a-h1-8]?: Optional disambiguation character, which can be a file (a-h) or a rank (1-8), used when two pieces of the same type can move to the same square.
#   - x?: Optional 'x' character denoting a capture.
#   - [a-h][1-8]: Mandatory destination square notation (file followed by rank).
#   - (?:=[QRBN])?: Optional pawn promotion indicator, capturing '=Q', '=R', '=B', or '=N'.
# |O-O(?:-O)?: Captures castling moves, "O-O" for kingside and "O-O-O" for queenside.
# [\+#]?: Optional '+' or '#' at the end to denote check ('+') or checkmate ('#').

regex = r'(?<! to | on |the |rom )\b(?:[1-9][0-9]*\.\s*)?(([KQBNR]?[a-hA-H1-8]?[xX]?[a-hA-H][1-8](?:=[QRBN])?|O-O(?:-O)?)\b[\+#]?)'

def capitalize_chess_coords(coords):
    pattern = r'\b([a-h])([1-8])\b'
    return re.sub(pattern, lambda m: m.group(1).upper() + m.group(2), coords)


def substitute_chess_moves(text, insert_delim=None, num_words=False, capitalize=True):
    '''
    Replace moves in SAN notation with pronounceable text, suitable for text-to-speech.
    '''
    def replace_match(match):
        move = match.group(1)
        return translate_chess_move(move, num_words, capitalize) + (insert_delim or '')

    # Replace each move in the text with its translated version
    translated_text = re.sub(regex, replace_match, text)
    return translated_text


def translate_chess_move(move, num_words=False, capitalize=False):
    # Translation for each piece
    piece_dict = {'K': 'king', 'Q': 'queen', 'B': 'bishop', 'N': 'knight', 'R': 'rook'}

    # Detect and handle check/checkmate symbols
    status = ""
    if move.endswith('+'):
        status = ", check"
        move = move[:-1]  # Remove the '+' from the move

    elif move.endswith('#'):
        status = ", checkmate"
        move = move[:-1]  # Remove the '#' from the move

    # Handle castling
    if move in ["O-O", "O-O-O"]:
        return "castle kingside" if move == "O-O" else "castle queenside"

    # Remove captures
    move = move.replace('x', '')

    # Check for pawn promotion
    promotion = ""
    if '=' in move:
        promotion_piece = move.split('=')[1]
        promotion = ", promoting to " + piece_dict.get(promotion_piece, '')
        move = move.split('=')[0]

    # Extract only the destination square (last two characters)
    destination = move[-2:]

    # Convert to uppercase so the A is pronounced correctly
    if capitalize:
        destination = destination.capitalize()

    if num_words:
        destination = destination.replace(destination[1], ' ' + num2words(destination[1]))

    # Piece or pawn?
    piece = piece_dict[move[0]] if move[0] in piece_dict else "pawn"

    return f"{piece} to {destination}" + promotion + status


def remove_san_notation(text):
    def check_and_remove(match):
        san_part = match.group(1)
        # Translate the SAN to English
        english_move = translate_chess_move(san_part)

        # Create a pattern to match the English move description followed by the SAN notation
        preceding_text_pattern = r'(\b' + re.escape(english_move) + r'\s*\()' + re.escape(san_part) + r'\)'

        # Check for the complete pattern in the text
        if re.search(preceding_text_pattern, text, flags=re.IGNORECASE):
            return ''
        return match.group(0)

    # Regex pattern to find SAN notations in parentheses
    san_pattern = r'\s+?\((O-O-O|O-O|[KQBNR]?[a-h1-8]?x?[a-h][1-8](?:=[QRBN])?)\)'
    return re.sub(san_pattern, check_and_remove, text)


def test_substitute_chess_moves():
    test_cases = [
        ["cxd3", "pawn to d3"],
        ["dxc8=R+", "pawn to c8, promoting to rook, check"],
        ["dxc8=R# !!!", "pawn to c8, promoting to rook, checkmate !!!"],
        ["1. e4 e5 2. Nf3 Nc6", "pawn to e4 pawn to e5 knight to f3 knight to c6"],
        ["3. Bxf7+ Kxf7", "bishop to f7, check king to f7"],
        ["4. exd5!", "pawn to d5!"],
        ["5. Qd8+ Kf7", "queen to d8, check king to f7"],
        ["6. Nf6#", "knight to f6, checkmate"],
        ["7. O-O!??", "castle kingside!??"],
        ["8. O-O-O", "castle queenside"],
        ["9. e8=Q", "pawn to e8, promoting to queen"],
        ["10. dxc8=R+", "pawn to c8, promoting to rook, check"],
        ["11. Nbd2", "knight to d2"],
        ["12. Rfe1", "rook to e1"],
        ["13. exd6 e.p.", "pawn to d6 e.p."],
        ["14. Qh4+!", "queen to h4, check!"],
        ["15. Nxe6??", "knight to e6??"],
        ["16. N1f3", "knight to f3"],
        ["17. Bb5+ c6", "bishop to b5, check pawn to c6"],
        ["In a surprising turn of events, 18. c4 c5 19. d4 cxd4 20. Qxd4 Nc6",
        "In a surprising turn of events, pawn to c4 pawn to c5 pawn to d4 pawn to d4 queen to d4 knight to c6"],
        ["After a long thought, she played 21. Bg5, which was followed by 22... h6 23. Bxf6 Qxf6",
        "After a long thought, she played bishop to g5, which was followed by 22... pawn to h6 bishop to f6 queen to f6"],
        ["The game started with 1. e4, and after 1... e5, it was clear it would be a battle. Then came 2. Nf3 Nc6 and 3. Bc4",
        "The game started with pawn to e4, and after 1... pawn to e5, it was clear it would be a battle. Then came knight to f3 knight to c6 and bishop to c4"],
        ["24. Rad1, leading to a complex middle game. Then 24... d5 was played, shaking the board.",
        "rook to d1, leading to a complex middle game. Then 24... pawn to d5 was played, shaking the board."],
        ["The final move was 25. Qh5#, ending the game dramatically.",
        "The final move was queen to h5, checkmate, ending the game dramatically."],
        ["king to c3", "king to c3"],
        ["pawn on c3", "pawn on c3"],
        ["the c3 pawn", "the c3 pawn"],
        ["A good pawn move for you to consider is dxE5", "A good pawn move for you to consider is pawn to E5"],
        ["A good pawn move for you to consider is DxE5", "A good pawn move for you to consider is pawn to E5"],
        ["A good pawn move for you to consider is DXe5", "A good pawn move for you to consider is pawn to e5"],
        ["knight from g1", "knight from g1"]
]

    for test, expected in test_cases:
        translation = substitute_chess_moves(test, capitalize=False)
        assert translation == expected, (expected, translation)


def test_remove_san_notation():
    test_cases = {
        "Castle kingside (O-O)": "Castle kingside",
        "Knight to f3 (Nf3)": "Knight to f3",
        "Pawn to e4  (e4)": "Pawn to e4",
        "the move is bishop to F7 (Bf7)": "the move is bishop to F7",
        "Queen to h5 (Qh5), check": "Queen to h5, check",
        "Rook to d1 (Rd1)": "Rook to d1",
        "Pawn to c4 (c4), Bishop to G7 (Bg7)": "Pawn to c4, Bishop to G7",
        "Pawn to c4 (C4), bishop to g7 (Bg7)": "Pawn to c4 (C4), bishop to g7",
        "Castle queenside (O-O-O)": "Castle queenside",
        "wrong! castle kingisde (O-O-O)": "wrong! castle kingisde (O-O-O)",
    }
    for test, expected in test_cases.items():
        translation = remove_san_notation(test)
        assert translation == expected, (expected, translation)


if __name__ == '__main__':
    test_substitute_chess_moves()
    test_remove_san_notation()
