import argparse
import sqlite3

import chess
from tqdm import tqdm


def extract_data(database_path, include_themes, exclude_themes):
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    include_condition = ""
    if include_themes:
        include_condition = " AND (" + " OR ".join(f"Themes LIKE '%{theme}%'" for theme in include_themes) + ")"

    exclude_condition = ""
    if exclude_themes:
        exclude_condition = " AND (" + " AND ".join(f"Themes NOT LIKE '%{theme}%'" for theme in exclude_themes) + ")"

    query = f"""
    SELECT PuzzleId, FEN, Moves, Themes FROM puzzles
    WHERE 1 {include_condition} {exclude_condition};
    """
    print(query)
    cursor.execute(query)
    rows = cursor.fetchall()

    conn.close()
    return rows

def process_data(data):
    processed_data = []
    for row in tqdm(data, desc="Processing data", unit="row"):
        puzzle_id, fen, moves, _ = row
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

        if not board.is_valid():
            continue

        first_move_epd = board.epd()

        try:
            board.push_uci(moves[1])
        except ValueError:
            continue

        if board.is_valid() and not board.is_game_over():
            processed_data.append((puzzle_id, first_move_epd, moves[1]))

    return processed_data

def save_data_to_file(data, output_path):
    with open(output_path, "w") as file:
        file.write('puzzles="""\n')
        for puzzle_id, first_move_epd, second_move in data:
            file.write(f'{first_move_epd} bm {second_move}; id "Lichess {puzzle_id}";\n')
        file.write('\n"""')

def main():
    parser = argparse.ArgumentParser(description="Extract data from SQLite3 database")
    parser.add_argument("input_db", help="Path to the input SQLite3 database file")
    parser.add_argument("-o", "--output", help="Path to the output text file", required=True)
    parser.add_argument("--include", nargs="*", help="Themes to include")
    parser.add_argument("--exclude", nargs="*", help="Themes to exclude")

    args = parser.parse_args()

    data = extract_data(args.input_db, args.include, args.exclude)
    processed_data = process_data(data)
    save_data_to_file(processed_data, args.output)

if __name__ == "__main__":
    main()
