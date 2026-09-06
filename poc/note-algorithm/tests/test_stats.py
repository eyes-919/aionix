import unittest

from noteseek.stats import (
    RidgeRegression,
    auc,
    ndcg_at_k,
    partial_spearman,
    pearson,
    rankdata,
    residualize,
    spearman,
)


class TestStats(unittest.TestCase):
    def test_spearman_detects_monotonic_but_nonlinear_relation(self):
        x = [1, 2, 3, 4, 5]
        y = [1, 4, 9, 16, 25]
        self.assertAlmostEqual(spearman(x, y), 1.0, places=6)
        self.assertLess(pearson(x, y), 1.0)

    def test_rankdata_averages_ties(self):
        self.assertEqual(rankdata([10, 20, 20, 30]), [1.0, 2.5, 2.5, 4.0])

    def test_auc_is_one_for_perfect_separation(self):
        self.assertAlmostEqual(auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]), 1.0)
        self.assertAlmostEqual(auc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]), 0.0)

    def test_auc_degenerate_labels_return_half(self):
        self.assertEqual(auc([1, 1, 1], [0.1, 0.5, 0.9]), 0.5)

    def test_ndcg_rewards_correct_ordering(self):
        good = ndcg_at_k([3.0, 2.0, 1.0], k=3)
        bad = ndcg_at_k([1.0, 2.0, 3.0], k=3)
        self.assertAlmostEqual(good, 1.0)
        self.assertLess(bad, good)

    def test_ridge_recovers_known_coefficients(self):
        features = [[float(i), float(i % 3)] for i in range(60)]
        target = [3.0 * a + 1.5 * b + 2.0 for a, b in features]
        model = RidgeRegression(alpha=1e-6).fit(features, target)
        self.assertAlmostEqual(model.coefficients[0], 3.0, places=2)
        self.assertAlmostEqual(model.coefficients[1], 1.5, places=2)

    def test_partial_correlation_removes_confounder(self):
        # x と y はどちらも交絡 c から作られており、直接の関係はない
        c = [float(i) for i in range(80)]
        x = [value * 2.0 for value in c]
        y = [value * 3.0 for value in c]
        controls = [[value] for value in c]
        self.assertGreater(spearman(x, y), 0.99)
        self.assertLess(abs(partial_spearman(x, y, controls)), 0.2)

    def test_residualize_without_controls_is_identity(self):
        target = [1.0, 2.0, 3.0]
        self.assertEqual(residualize(target, []), target)


if __name__ == "__main__":
    unittest.main()
