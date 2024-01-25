#!/usr/bin/env python3
""" Run this after updating ECO. """
import logging
import opening
import os
import sh
from contextlib import contextmanager

INDEX_DIR = 'openings.idx'
TOOLS_DIR = os.path.join(os.getcwd(), 'annembed')

EPOCHS = 200  # For training.
TEXT_FILE = 'names.txt'

logging.basicConfig(level=logging.INFO)

eco = opening.ECO()  # Load the Encyclopaedia of Chess Openings.

@contextmanager
def change_directory(new_dir):
    original_dir = os.getcwd()
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(original_dir)

logging.info(f'Creating: "{INDEX_DIR}"')
os.makedirs(INDEX_DIR, exist_ok=True)

def run(tool, *args):
    def output(line):
        print(line, end='')
    logging.info(f'Running tool: {tool} {args}')
    sh.python3((os.path.join(TOOLS_DIR, tool), *args), _out=output)

with change_directory(INDEX_DIR):
    # Write all openings to a file.
    logging.info(f'Writing out: "{TEXT_FILE}"')
    with open(TEXT_FILE, 'w') as f:
        for row in eco.data:
            name = row['name'].split(':')
            # Double the main opening names, to give them more weight in the training.
            # ... and take the opportunity to replace apostrophes so that at query time
            # we can match "Queens Gambit" against "Queen's Gambit
            alt_name = name[0].replace("'", "")
            f.write(f"{name[0]} ({alt_name}) {' '.join(name[1:])}\n")

    run('train.py', '--epochs', f'{EPOCHS}', '--text', TEXT_FILE, '--use-metaphone', '--embed', '64', '--win', '10')
    run('index.py', '--text', TEXT_FILE, '--num-trees', 8)

