import pandas as pd
import sqlite3

# Read the CSV file without column headers and provide the column names
column_names = [
    'PuzzleId', 'FEN', 'Moves', 'Rating', 'RatingDeviation', 'Popularity',
    'NbPlays', 'Themes', 'GameUrl', 'OpeningTags'
]

data = pd.read_csv("lichess_db_puzzle.csv", header=None, names=column_names)

# Connect to the SQLite database (this will create a new file if it doesn't exist)
conn = sqlite3.connect("puzzles.db")

# Write the data to the database
data.to_sql("puzzles", conn, if_exists="replace", index=False)

# Close the connection to the database
conn.close()

