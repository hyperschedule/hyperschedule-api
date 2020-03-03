import unittest

from hyperschedule.worker import apply_diff, compute_diff, merge_diffs


class TestDiff(unittest.TestCase):
    def test_abc(self):
        cases = [
            [{"foo": "a"}, {"foo": "b"}, {"foo": "c"}],
            [{}, {"foo": "b"}, {"foo": "c"}],
            [{"foo": "a"}, {}, {"foo": "c"}],
            [{}, {"foo": "b"}, {}],
            [{}, {"foo": {"bar": "b"}}, {"foo": "c"}],
            [{"foo": {"bar": "a"}}, {"foo": "b"}, {"foo": {"bar": "b"}}],
        ]
        for a, b, c in cases:
            d_ab = compute_diff(a, b)
            d_bc = compute_diff(b, c)
            d_ac = merge_diffs(d_ab, d_bc)
            c_from_a = apply_diff(a, d_ac)
            c_from_b = apply_diff(b, d_ac)
            self.assertEqual(c, c_from_a)
            self.assertEqual(c, c_from_b)
