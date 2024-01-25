# import os
# import sys
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import opening
import unittest

class TestOpenings(unittest.TestCase):
    def setUp(self):
        self.eco = opening.ECO(index_dir='openings.idx')

    def test_index(self):
        queries = {
            "alban's counter-gambit": [
                "Queen's Gambit Declined: Albin Countergambit",

                #"Queen's Gambit Declined: Albin Countergambit, Fianchetto Variation",
                #"Queen's Gambit Declined: Albin Countergambit, Lasker Trap"
            ],
            "kasparov attack": [
                "Queen's Indian Defense: Kasparov-Petrosian Variation, Kasparov Attack",
                "French Defense: Rubinstein Variation, Kasparov Attack",
            ],
            "casparoff petrosian": [
                "Queen's Indian Defense: Kasparov-Petrosian Variation, Petrosian Attack",
                "Queen's Indian Defense: Kasparov-Petrosian Variation, Kasparov Attack",
                "Queen's Indian Defense: Kasparov-Petrosian Variation"
            ],
            "monkey bum": [
                "Modern Defense: Bishop Attack, Monkey's Bum",
            ],
            "lookup monkey's bum": [
                "Modern Defense: Bishop Attack, Monkey's Bum",
            ],
            "pterodactil": [
                "Pterodactyl Defense",
                "Modern Defense: Pterodactyl Variation"
            ],
            "sicilian pterodactil": [
                "Pterodactyl Defense: Sicilian, Benoni Gambit",
            ],
            "sicilian defence pterodactyle": [
                "Pterodactyl Defense",
                "Pterodactyl Defense: Sicilian, Benoni Gambit",
            ],
            "Dragon, hyperaccelerated": [
                "Sicilian Defense: Hyperaccelerated Dragon",
            ],
            "CaroKann": [
                "Caro-Kann Defense",
            ],
            "LiverFried attack": [
                "Italian Game: Two Knights Defense, Fried Liver Attack"
            ],
            "Fried Liver Attak": [
                "Italian Game: Anti-Fried Liver Defense",
                "Italian Game: Two Knights Defense, Fried Liver Attack"
            ],
            "hyper-accelerated dragon": [
                "Sicilian Defense: Hyperaccelerated Dragon",
            ],
            "ageincourt de-fence": [
                "English Opening: Agincourt Defense",

                #"English Opening: Agincourt Defense, Keres Defense",
                #"English Opening: Agincourt Defense, Catalan Defense",
                #"English Opening: Agincourt Defense, Wimpy System",
                #"English Opening: Agincourt Defense, Kurajica Defense",
                #"English Opening: Agincourt Defense, Tarrasch Defense",
                #"English Opening: Agincourt Defense, Catalan Defense, Semi-Slav Defense"
            ],
            "orthoshnapp gambit": [
                "French Defense: Orthoschnapp Gambit",
                "French Defense: Perseus Gambit"
            ],
            "ortoshnap gambitt": [
                "French Defense: Orthoschnapp Gambit",
                "French Defense: Perseus Gambit"
            ],
            "OrthoSchnapp Gambit": [
                "French Defense: Orthoschnapp Gambit",
            ],
            "elephant's": [
                "Elephant Gambit",
            ],
            "fiancheto variant": [
                "King's Indian Defense: Fianchetto Variation, Classical Fianchetto",
                "King's Indian Defense: Fianchetto Variation, Immediate Fianchetto"
            ],
            "The Goblin": [
                "Dresden Opening: The Goblin",
            ],
            "queens gambith declineth": [
                "Queen's Gambit Declined",
            ],
            "yugoslav attack": [
                "Sicilian Defense: Dragon Variation, Yugoslav Attack",
                "Sicilian Defense: Dragon Variation, Yugoslav Attack, Soltis Variation"
            ],
            "sicilian iugoslav attack": [
                "Sicilian Defense: Dragon Variation, Yugoslav Attack",
            ],
            "sicilian defence yugoslav attack": [
                "Sicilian Defense: Dragon Variation, Yugoslav Attack",
            ],
            "rubenstain sistem": [
                "Semi-Slav Defense: Rubinstein System",
            ],
            "kapablanka sister" : [
                "Queen's Gambit Declined: Orthodox Defense, Capablanca System"
            ],
            "Lasker belly can" : [
                "Sicilian Defense: Lasker-Pelikan Variation",
            ]
        }
        for query, expected in queries.items():
            results = self.eco.query_by_name(query, top_n=1)
            self.assertEqual(len(results), 1)
            for opening in results:
                #print(opening.name)
                self.assertIn(opening.name, expected)

    def test_lookup_by_eco(self):
        queries = {
            "c10": "French Defense",
            "A00-02": "Amar",
            "B98-B99": "Sicilian Defense: Najdorf Variation",
        }
        for query, expected in queries.items():
            results = self.eco.query_by_eco_code(query, top_n=3)
            self.assertTrue(len(results) <= 3)
            for opening in results:
                # print(opening.eco, opening.name)
                self.assertIn(opening.eco, query.upper())
                self.assertIn(expected, opening.name)

if __name__ == '__main__':
    unittest.main()
