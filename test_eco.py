from chess import Board
from opening import ECO, Opening
from kivy.logger import Logger, LOG_LEVELS

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
            "Caro-Kann Defense: Panov-Botvinnik Attack": Opening({'name': 'Caro-Kann Defense: Panov Attack', 'eco': 'B14'}),
        }
        for name, expected in good_test_cases.items():
            opening = self.eco.lookup_best_matching_name(name, expected.eco, confidence=85)
            assert opening
            assert opening.name == expected.name, (expected.name, opening.name)
            assert opening.eco == expected.eco, (expected.eco, opening.eco)

        bad_test_cases = {
            'sicilian defense': 'b50',
            'sicilian defense': 'b5',
            'Cecilia and The Fans': 'b50',
        }
        for name, eco in bad_test_cases.items():
            opening = self.eco.lookup_best_matching_name(name, eco, confidence=80)
            assert opening is None, (name, eco, opening)

        eco_ranges_cases = [
            {"name":"Grünfeld Defense", "eco":"D80-D99"},
            {"name":"Scandinavian Defense", "eco":"B01-B99"},
            {"name":"English Opening", "eco":"A10-A39"}
        ]
        for test in eco_ranges_cases:
            opening = self.eco.lookup_best_matching_name(test['name'], test['eco'], confidence=90)
            assert opening
            assert opening.name == test['name'], (opening.name, test)


    def test_name_lookup(self):
        test_cases = {
            "Bongcloud Opening": Opening({'name':'Bongcloud Attack', 'eco': 'C20'}),
            "Orangutan Opening": Opening({'name':'English Orangutan', 'eco': 'A15'}),
            "kasparov's attack": Opening({'name':'French Defense: Rubinstein Variation, Kasparov Attack', 'eco': 'C10'}),
            "Kasparov opening": Opening({'name': "Queen's Indian Defense: Kasparov Variation", 'eco': 'E13'}),
            "Sicilian Defense": Opening({'name': 'Sicilian Defense', 'eco': 'B50'}),
            "Silician Defense": Opening({'name': 'Sicilian Defense', 'eco': 'B50'}),
            "Monkey's Bum": Opening({'name': "Modern Defense: Bishop Attack, Monkey's Bum", 'eco': 'B06'}),
            "Goring Gambit Declined": Opening({'name': 'Scotch Game: Scotch Gambit, Göring Gambit Declined', 'eco': 'C44'}),
            "albin's gambit": Opening({'name': 'Italian Game: Classical Variation, Albin Gambit', 'eco': 'C50'}),
            "najdorf variation, schven": Opening({'name': 'Sicilian Defense: Najdorf Variation, Scheveningen Variation', 'eco': 'B84'}),
            "najdorf variation": Opening({'name': 'Sicilian Defense: Najdorf Variation', 'eco': 'B98'}),
        }
        for name, expected in test_cases.items():
            opening = self.eco.lookup_best_matching_name(name, confidence=85)
            assert opening.name == expected.name, (expected.name, opening.name)
            assert opening.eco == expected.eco, (expected.eco, opening.eco)

    def test_phonetic_lookup(self):
        good_test_cases = {
            "sicilian defense": Opening({'name': 'Sicilian Defense', 'eco': 'B50'}),
            "Moon Keys Bomb": Opening({'name': "Modern Defense: Bishop Attack, Monkey's Bum", 'eco': 'B06'}),
            "Goring Gambit Declined": Opening({'name': 'Scotch Game: Scotch Gambit, Göring Gambit Declined', 'eco': 'C44'}),
            "Goering Gambit": Opening({'name': 'Scotch Game: Göring Gambit', 'eco': 'C44'}),
            "Anti Fried Liver": Opening({'name': 'Italian Game: Anti-Fried Liver Defense', 'eco': 'C50'}),
        }
        for name, expected in good_test_cases.items():
            opening = self.eco.phonetic_lookup(name, confidence=62)
            assert opening.name == expected.name, (expected.name, opening.name)
            assert opening.eco == expected.eco, (expected.eco, opening.eco)

        bad_test_cases = {
            'zilcian defens',
            'Cecilia and The Fans',
        }
        for name in bad_test_cases:
            opening = self.eco.phonetic_lookup(name, confidence=80)
            assert opening is None, (name, opening)


    def test_matches(self):
        results = self.eco.lookup_matches('Fischer')
        results = [r.eco for r in results]
        assert results == ['B88', 'C34', 'C34', 'C34', 'E44'], results

        results = self.eco.lookup_matches('Lasker')
        results = [r.eco for r in results]
        assert results == [
            'A00', 'A02', 'A02', 'A03', 'A83', 'B01',
            'B20', 'B33', 'C52', 'D18', 'D56', 'D57'], results

        results = self.eco.lookup_matches('najdorf variation')
        results = [r.eco for r in results]
        assert results == [
            'B84', 'B98', 'B90', 'B90', 'B90', 'B90', 'B90', 'B90',
            'B91', 'B92', 'B92', 'B92', 'B93', 'B94', 'B96', 'B96',
            'B96', 'B97', 'B97', 'B98', 'B98', 'B98', 'B99'
        ], results


    def test_phonetic_matches(self):
        results = self.eco.phonetic_matches('najdorf variation', confidence=82)
        results = [r.eco for r in results]
        assert results == [
            'B84', 'B98', 'B90', 'B90', 'B90', 'B90', 'B90', 'B90',
            'B91', 'B92', 'B92', 'B92', 'B93', 'B94', 'B96', 'B96',
            'B96', 'B97', 'B97', 'B98', 'B98', 'B98', 'B99'
        ], results

        results = self.eco.phonetic_matches("Alban's countergambit", confidence=82)
        results = [r.name for r in results]
        assert results == [
            'Duras Gambit',
            'Blackmar-Diemer Gambit: Reversed Albin Countergambit',
            "Queen's Gambit Declined: Albin Countergambit",
        ], results

        results = self.eco.phonetic_matches("Alpin counter gambit", confidence=85)
        results = [r.name for r in results]
        assert results == [
            'Blackmar-Diemer Gambit: Reversed Albin Countergambit',
            "Queen's Gambit Declined: Albin Countergambit",
        ], results


    def run(self):
        self.test_board_lookup()
        self.test_eco_lookup()
        self.test_matches()
        self.test_name_lookup()
        self.test_phonetic_lookup()
        self.test_phonetic_matches()


if __name__ == '__main__':
    Logger.setLevel(LOG_LEVELS['debug'])

    tests = Tests()
    tests.run()
