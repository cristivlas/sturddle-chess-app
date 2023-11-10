import logging

from chess import Board
from opening import ECO, Opening

class Tests:
    def __init__(self):
        self.eco = ECO()

    def test_board_lookup(self):
        pass

    def test_eco_lookup(self):
        test_cases = {
            'B50': None,
        }
        for eco, expected in test_cases.items():
            pass

    def test_name_lookup(self):
        test_cases = {
            "Sicilian Defense": Opening({'name': 'Sicilian Defense', 'eco': 'B50'}),
            "Monkey's Bum": Opening({'name': "Modern Defense: Bishop Attack, Monkey's Bum", 'eco': 'B06'}),            
            "Goring Gambit Declined": Opening({'name': 'Scotch Game: Scotch Gambit, Göring Gambit Declined', 'eco': 'C44'}),
        }
        for name, expected in test_cases.items():
            opening = self.eco.lookup_name(name, confidence=85)
            assert opening.name == expected.name, (expected.name, opening.name)
            assert opening.eco == expected.eco, (expected.eco, opening.eco)

    def test_phonetical_lookup(self):
        pass

    def run(self):
        self.test_board_lookup()
        self.test_eco_lookup()
        self.test_name_lookup()
        self.test_phonetical_lookup()


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.DEBUG)
    tests = Tests()
    tests.run()