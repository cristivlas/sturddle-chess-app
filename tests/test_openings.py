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
            "alban's counter-gambit": "Albin Countergambit",
            "kasparov attack": "Kasparov",
            "casparoff petrosian": "Kasparov-Petrosian Variation",
            "monkey bum": "Bishop Attack, Monkey's Bum",
            "lookup monkey's bum": "Bishop Attack, Monkey's Bum",
            "pterodactil": "Pterodactyl Defense",
            "dragon, very accelerated": "Dragon Variation",
            "Dragon, hyperaccelerated": "Hyperaccelerated Dragon",
            "CaroKann": "Caro-Kann",
            "LiverFried attack": "Fried Liver Attack",
            "Fried Liver Attak": "Fried Liver Attack",
            "hyper-accelerated dragon": "Hyperaccelerated Dragon",
            "court defense": "Agincourt Defense",
        }
        for query, expected in queries.items():
            results = self.eco.query_by_name(query, top_n=1)
            self.assertEqual(len(results), 1)
            for opening in results:
                # print(opening.name)
                self.assertIn(expected, opening.name)

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