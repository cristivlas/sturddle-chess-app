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
            "hyper-accelerated": "Hyperaccelerated",
        }
        for query, expected in queries.items():
            results = self.eco.query_by_name(query, top_n=1)
            for opening in results:
                # print(opening.name)
                self.assertIn(expected, opening.name)

if __name__ == '__main__':
    unittest.main()