import argparse
import sqlite3

import chess
from tqdm import tqdm


def extract_data(args):
    conn = sqlite3.connect(args.input_db)
    cursor = conn.cursor()

    query = '''
        SELECT PuzzleId, FEN, Moves, Themes FROM puzzles
        WHERE
            Themes NOT LIKE '%defensive%'
            AND Themes NOT LIKE '%advantage%'
            AND Themes NOT LIKE '%crushing%'
            AND Themes NOT LIKE '%master%'
            AND Themes NOT LIKE '%mateIn2%'
            AND (Themes NOT LIKE '%long%' OR Themes LIKE '%mateIn3%' or Themes LIKE '%mateIn4%')
            AND (Themes LIKE '%clearance%' OR Themes LIKE '%sacrifice%')
    '''
    print(query)
    cursor.execute(query)
    rows = cursor.fetchall()

    conn.close()
    return rows

def process_data(data):
    processed_data = []
    for row in tqdm(data, desc="Processing data", unit="row"):
        puzzle_id, fen, moves, themes = row
        moves = moves.strip().split()
        if len(moves) < 2:
            continue
        board = chess.Board(fen=fen)

        if not board.is_valid():
            continue

        try:
            board.push_uci(moves[0])
        except ValueError:
            continue

        if not board.is_valid() or board.is_check():
            continue

        first_move_epd = board.epd()

        try:
            board.push_uci(moves[1])
        except ValueError:
            continue

        if board.is_valid() and not board.is_game_over():
            processed_data.append((puzzle_id, first_move_epd, moves[1], themes))

    return processed_data

def save_data_to_file(data, output_path):
    with open(output_path, "w") as file:
        file.write('puzzles="""\n')
        for puzzle_id, first_move_epd, second_move, themes in data:
            file.write(f'{first_move_epd} bm {second_move}; id "Lichess {puzzle_id}"; {themes}\n')
        file.write('"""')

def main():
    parser = argparse.ArgumentParser(description="Extract data from SQLite3 database")
    parser.add_argument("input_db", help="Path to the input SQLite3 database file")
    parser.add_argument("-o", "--output", help="Path to the output text file", required=True)

    args = parser.parse_args()

    data = extract_data(args)
    processed_data = process_data(data)
    save_data_to_file(processed_data, args.output)

if __name__ == "__main__":
    main()
