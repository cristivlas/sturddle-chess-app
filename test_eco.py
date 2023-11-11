import logging

from chess import Board
from opening import ECO, Opening

class Tests:
    def __init__(self):
        self.eco = ECO()

    def test_board_lookup(self):
        pass

    def test_eco_lookup(self):
        good_test_cases = {
            "sicilian defense": Opening({'name': 'Sicilian Defense', 'eco': 'B50'}),
            "Monkey's Butt": Opening({'name': "Modern Defense: Bishop Attack, Monkey's Bum", 'eco': 'B06'}),
            "Goring Gambit Declined": Opening({'name': 'Scotch Game: Scotch Gambit, Göring Gambit Declined', 'eco': 'C44'}),
        }
        for name, expected in good_test_cases.items():
            opening = self.eco.name_lookup(name, expected.eco, confidence=85)
            assert opening.name == expected.name, (expected.name, opening.name)
            assert opening.eco == expected.eco, (expected.eco, opening.eco)

        bad_test_cases = {
            'sicilian defense': 'b50',
            'sicilian defense': 'b5',
            'Cecilia and The Fans': 'b50',
        }
        for name, eco in bad_test_cases.items():
            opening = self.eco.name_lookup(name, eco, confidence=80)
            assert opening is None, (name, eco, opening)

        eco_ranges_cases = [
            {"name":"Grünfeld Defense", "eco":"D80-D99"},
            {"name":"Scandinavian Defense", "eco":"B01-B99"},
            {"name":"English Opening", "eco":"A10-A39"}
        ]
        for test in eco_ranges_cases:
            opening = self.eco.name_lookup(test['name'], test['eco'], confidence=90)
            assert opening
            assert opening.name == test['name'], (opening.name, test)


    def test_name_lookup(self):
        test_cases = {
            "Bongcloud Opening": Opening({'name':'Bongcloud Attack', 'eco': 'C20'}),
            "Orangutan Opening": Opening({'name':'English Orangutan', 'eco': 'A15'}),
            "kasparov's attack": Opening({'name':'Caro-Kann Defense: Karpov Variation, Modern Variation, Kasparov Attack', 'eco': 'B17'}),
            "Kasparov opening": Opening({'name': 'French Defense: Rubinstein Variation, Kasparov Attack', 'eco': 'C10'}),
            "Sicilian Defense": Opening({'name': 'Sicilian Defense', 'eco': 'B50'}),
            "Silician Defense": Opening({'name': 'Sicilian Defense', 'eco': 'B50'}),
            "Monkey's Bum": Opening({'name': "Modern Defense: Bishop Attack, Monkey's Bum", 'eco': 'B06'}),
            "Goring Gambit Declined": Opening({'name': 'Scotch Game: Scotch Gambit, Göring Gambit Declined', 'eco': 'C44'}),
            "albin's gambit": Opening({'name': 'Italian Game: Classical Variation, Albin Gambit', 'eco': 'C50'}),
        }
        for name, expected in test_cases.items():
            opening = self.eco.name_lookup(name, confidence=85)
            assert opening.name == expected.name, (expected.name, opening.name)
            assert opening.eco == expected.eco, (expected.eco, opening.eco)

    def test_phonetical_lookup(self):
        good_test_cases = {
            "sicilian defense": Opening({'name': 'Sicilian Defense', 'eco': 'B50'}),
            "Moon Keys Bomb": Opening({'name': "Modern Defense: Bishop Attack, Monkey's Bum", 'eco': 'B06'}),
            "Goring Gambit Declined": Opening({'name': 'Scotch Game: Scotch Gambit, Göring Gambit Declined', 'eco': 'C44'}),
            "Goering Gambit": Opening({'name': 'Scotch Game: Göring Gambit', 'eco': 'C44'}),
        }
        for name, expected in good_test_cases.items():
            opening = self.eco.phonetical_lookup(name, confidence=62)
            assert opening.name == expected.name, (expected.name, opening.name)
            assert opening.eco == expected.eco, (expected.eco, opening.eco)

        bad_test_cases = {
            'zilcian defens',
            'Cecilia and The Fans',
        }
        for name in bad_test_cases:
            opening = self.eco.phonetical_lookup(name, confidence=80)
            assert opening is None, (name, opening)

    def run(self):
        self.test_board_lookup()
        self.test_eco_lookup()
        self.test_name_lookup()
        self.test_phonetical_lookup()


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.DEBUG)
    tests = Tests()
    tests.run()