import datetime as dt
import unittest

from noteseek.features import (
    ACTIONABLE_FEATURES,
    CONTROL_FEATURES,
    FEATURE_NAMES,
    FeatureBuilder,
    exposure_labels,
)
from noteseek.schema import Article


def make(key, tag, title, body, likes=0, order="new", tags=None):
    return Article(
        key=key,
        title=title,
        body_excerpt=body,
        body_chars=len(body),
        like_count=likes,
        tags=tags or [],
        source_tag=tag,
        source_order=order,
        published_at=dt.datetime(2026, 9, 1, 20, 0, tzinfo=dt.timezone.utc).isoformat(),
    )


class TestFeatures(unittest.TestCase):
    def test_feature_row_length_matches_names(self):
        builder = FeatureBuilder()
        builder.fit([make("n1", "AI", "タイトル", "本文")])
        self.assertEqual(len(builder.row(make("n2", "AI", "t", "b"))), len(FEATURE_NAMES))

    def test_control_and_actionable_partition_all_features(self):
        self.assertEqual(
            set(CONTROL_FEATURES) | set(ACTIONABLE_FEATURES), set(FEATURE_NAMES)
        )
        self.assertFalse(set(CONTROL_FEATURES) & set(ACTIONABLE_FEATURES))

    def test_exposure_label_reads_every_observed_tab(self):
        articles = [
            make("a", "AI", "t", "b", order="new"),
            make("b", "AI", "t", "b", order="new,hot"),
            make("c", "AI", "t", "b", order="new,popular"),
            make("d", "AI", "t", "b", order=""),
        ]
        self.assertEqual(exposure_labels(articles), [0, 1, 1, 0])

    def test_topic_fit_is_computed_within_each_source_tag(self):
        # AI 群と登山群を混ぜる。AI 記事は AI 群の重心とだけ比べるべき。
        corpus = [
            make(f"ai{i}", "AI", "生成AIプロンプト運用", "生成AIプロンプト検証運用精度", likes=100 - i)
            for i in range(6)
        ] + [
            make(f"mt{i}", "登山", "登山テント重量比較", "登山テント重量比較装備軽量化", likes=100 - i)
            for i in range(6)
        ]
        builder = FeatureBuilder().fit(corpus)
        self.assertIn("AI", builder.group_centroids)
        self.assertIn("登山", builder.group_centroids)

        on_topic = make("x", "AI", "生成AIプロンプト設計", "生成AIプロンプト検証運用")
        off_topic = make("y", "AI", "登山テント重量", "登山テント重量比較装備")
        self.assertGreater(builder.topic_fit(on_topic), builder.topic_fit(off_topic))

    def test_tag_overlap_uses_winner_tags_of_own_group(self):
        corpus = [
            make(f"a{i}", "AI", "生成AI", "生成AI本文", likes=500, tags=["生成AI"])
            for i in range(6)
        ] + [
            make(f"b{i}", "AI", "雑記", "雑記本文", likes=1, tags=["日記"])
            for i in range(6)
        ]
        builder = FeatureBuilder().fit(corpus)
        with_winner = make("x", "AI", "t", "b", tags=["生成AI"])
        without = make("y", "AI", "t", "b", tags=["日記"])
        self.assertGreater(builder.tag_overlap(with_winner), builder.tag_overlap(without))

    def test_unknown_group_falls_back_to_best_matching_topic(self):
        corpus = [
            make(f"ai{i}", "AI", "生成AIプロンプト", "生成AIプロンプト運用検証", likes=10)
            for i in range(6)
        ] + [
            make(f"mt{i}", "登山", "登山テント", "登山テント重量比較装備", likes=10)
            for i in range(6)
        ]
        builder = FeatureBuilder().fit(corpus)
        draft = make("draft", "", "生成AIプロンプトの運用", "生成AIプロンプト検証運用")
        self.assertGreater(builder.topic_fit(draft), 0.0)


if __name__ == "__main__":
    unittest.main()
