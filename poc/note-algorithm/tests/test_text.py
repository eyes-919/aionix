import unittest

from noteseek.text import (
    TfidfIndex,
    char_ngrams,
    cosine,
    merge_grams,
    normalize,
    top_phrases,
)


class TestText(unittest.TestCase):
    def test_normalize_removes_urls_and_folds_width(self):
        result = normalize("ＡＩ の記事 https://note.com/x/n/n1 です")
        self.assertIn("ai", result)
        self.assertNotIn("note.com", result)

    def test_ngrams_do_not_span_separators(self):
        grams = char_ngrams("あい うえ", sizes=(2,))
        self.assertIn("あい", grams)
        self.assertIn("うえ", grams)
        self.assertNotIn("いう", grams)

    def test_similar_documents_score_higher_than_unrelated(self):
        index = TfidfIndex(min_df=1)
        index.fit(
            [
                "生成AIのプロンプト設計と業務効率化",
                "生成AIプロンプトの検証と運用",
                "登山用テントの選び方と重量比較",
                "キャンプ道具の収納と積載",
            ]
        )
        ai = index.transform("生成AIのプロンプト運用")
        related = index.transform("生成AIプロンプト設計の業務効率化")
        unrelated = index.transform("登山テントの重量比較")
        self.assertGreater(cosine(ai, related), cosine(ai, unrelated))

    def test_merge_grams_joins_overlapping_and_drops_substrings(self):
        self.assertEqual(merge_grams(["技術選", "術選定"]), ["技術選定"])
        self.assertNotIn("技術選", merge_grams(["技術選", "術選定"]))

    def test_merge_grams_refuses_single_character_overlap(self):
        # "あいう" と "うえお" は 1 文字しか重ならないので繋いではいけない
        merged = merge_grams(["あいう", "うえお"])
        self.assertNotIn("あいうえお", merged)
        self.assertEqual(sorted(merged), ["あいう", "うえお"])

    def test_merge_grams_respects_max_length(self):
        grams = ["ab" + chr(0x3042 + i) for i in range(20)]
        for term in merge_grams(grams, max_len=6):
            self.assertLessEqual(len(term), 6)

    def test_top_phrases_returns_readable_terms(self):
        index = TfidfIndex(min_df=1)
        docs = ["運用コストの削減"] * 3 + ["技術選定の記録"] * 3
        vectors = index.fit_transform(docs)
        phrases = top_phrases(vectors, limit=10)
        self.assertTrue(all(len(p) >= 3 for p in phrases))

    def test_empty_vectors_are_safe(self):
        self.assertEqual(cosine({}, {"a": 1.0}), 0.0)
        self.assertEqual(TfidfIndex().fit([]).transform("何か"), {})


if __name__ == "__main__":
    unittest.main()
