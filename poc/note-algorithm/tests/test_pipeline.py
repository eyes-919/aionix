"""収集 / 分析 / 助言のパイプライン結合テスト."""

import datetime as dt
import os
import tempfile
import unittest

from noteseek.advise import advise, build_draft_article, select_group, tag_lift
from noteseek.analyze import analyze
from noteseek.api import NoteApi
from noteseek.collect import collect_tag, load_jsonl, save_jsonl
from noteseek.fixtures import TRUE_SIGNALS, generate_corpus
from noteseek.schema import Article


class FakeApi(NoteApi):
    """HTTP を出さずに collect の観測設計だけを検証する."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def hashtag_notes(self, tag, order="new", page=1):
        self.calls.append((tag, order, page))
        return self.pages.get((order, page), [])


def raw(key, likes=0):
    return {
        "key": key,
        "name": f"title-{key}",
        "like_count": likes,
        "publish_at": "2026-09-01T20:00:00+09:00",
        "user": {"urlname": "u", "followerCount": 100},
    }


class TestCollect(unittest.TestCase):
    def test_pool_is_new_tab_and_exposed_articles_are_labelled(self):
        api = FakeApi(
            {
                ("new", 1): [raw("n1"), raw("n2"), raw("n3")],
                ("popular", 1): [raw("n1")],
                ("hot", 1): [raw("n2")],
            }
        )
        result = collect_tag(api, "AI", pool_pages=1, exposed_pages=1)
        self.assertEqual(result.pool_size, 3)
        self.assertEqual(result.exposed_size, 2)
        by_key = {a.key: a for a in result.articles}
        self.assertEqual(by_key["n1"].source_order, "new,popular")
        self.assertEqual(by_key["n2"].source_order, "new,hot")
        self.assertEqual(by_key["n3"].source_order, "new")

    def test_articles_only_in_exposed_tabs_do_not_inflate_the_pool(self):
        # 新着に出ていない古い人気記事を母集団に混ぜると露出率が壊れる
        api = FakeApi(
            {("new", 1): [raw("n1")], ("popular", 1): [raw("n1"), raw("old")]}
        )
        result = collect_tag(api, "AI", pool_pages=1, exposed_pages=1)
        self.assertEqual(result.pool_size, 1)
        self.assertEqual(result.exposed_size, 1)
        self.assertEqual(result.exposure_rate, 1.0)

    def test_jsonl_roundtrip_preserves_every_field(self):
        articles = generate_corpus(n=5, seed=1)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "c.jsonl")
            save_jsonl(articles, path)
            restored = load_jsonl(path)
        self.assertEqual(len(restored), 5)
        self.assertEqual(restored[0].to_dict(), articles[0].to_dict())


class TestAnalyze(unittest.TestCase):
    def test_known_signals_are_recovered_from_synthetic_data(self):
        report = analyze(generate_corpus(n=400, seed=7))
        self.assertEqual(report.verdict, "USABLE")
        detected = set()
        for model in (report.engagement, report.exposure):
            detected |= {f.name for f in model.findings if f.significant}
        for signal in TRUE_SIGNALS:
            self.assertIn(signal, detected, f"{signal} を検出できなかった")

    def test_pure_noise_is_not_reported_as_usable(self):
        """無関係なデータで USABLE が出るなら判定は信用できない."""
        import random

        rng = random.Random(3)
        now = dt.datetime.now(tz=dt.timezone.utc)
        corpus = [
            Article(
                key=f"n{i}",
                title="".join(rng.choice("あいうえおかきくけこ") for _ in range(10)),
                body_excerpt="".join(rng.choice("さしすせそたちつてと") for _ in range(80)),
                body_chars=rng.randint(300, 3000),
                like_count=rng.randint(0, 200),
                tags=[rng.choice(["a", "b", "c", "d"]) for _ in range(rng.randint(0, 3))],
                has_eyecatch=rng.random() < 0.5,
                creator_followers=rng.randint(10, 5000),
                source_tag="noise",
                source_order="new,hot" if rng.random() < 0.2 else "new",
                published_at=(now - dt.timedelta(days=rng.uniform(1, 30))).isoformat(),
            )
            for i in range(300)
        ]
        self.assertNotEqual(analyze(corpus).verdict, "USABLE")

    def test_small_corpus_reports_insufficient_data(self):
        self.assertEqual(analyze(generate_corpus(n=10, seed=2)).verdict, "INSUFFICIENT_DATA")

    def test_empty_corpus_does_not_raise(self):
        self.assertEqual(analyze([]).verdict, "INSUFFICIENT_DATA")


class TestAdvise(unittest.TestCase):
    def setUp(self):
        self.corpus = generate_corpus(n=400, seed=7)

    def test_group_selection_picks_the_matching_topic(self):
        draft = build_draft_article(
            "生成AIのプロンプト運用",
            "生成AIプロンプト検証運用精度ワークフロー業務効率",
            ["生成AI"],
        )
        self.assertEqual(select_group(draft, self.corpus), "生成AI活用")

    def test_recommendations_come_from_the_drafts_own_topic_only(self):
        draft = build_draft_article(
            "生成AIのプロンプト運用",
            "生成AIプロンプト検証運用精度ワークフロー業務効率",
            ["生成AI"],
        )
        report = advise(draft, self.corpus)
        self.assertEqual(report.group, "生成AI活用")
        self.assertFalse(report.group_fallback)
        self.assertLess(report.corpus_size, len(self.corpus))

    def test_on_topic_draft_outscores_off_topic_draft(self):
        on_topic = build_draft_article(
            "生成AIプロンプト運用の記録",
            "生成AIプロンプト検証運用精度モデルワークフロー業務効率自動化",
            ["生成AI"],
        )
        off_topic = build_draft_article(
            "生成AIプロンプト運用の記録",
            "今日先週結果課題背景整理感想手順比較失敗気づき記録共有現場改善",
            ["生成AI"],
        )
        group = "生成AI活用"
        self.assertGreater(
            advise(on_topic, self.corpus, group=group).topic_fit,
            advise(off_topic, self.corpus, group=group).topic_fit,
        )

    def test_falls_back_to_full_corpus_and_flags_it_when_topic_is_thin(self):
        thin = [a for a in self.corpus if a.source_tag == "生成AI活用"][:5]
        others = [a for a in self.corpus if a.source_tag != "生成AI活用"]
        draft = build_draft_article("生成AI", "生成AIプロンプト検証", ["生成AI"])
        report = advise(draft, thin + others, group="生成AI活用")
        self.assertTrue(report.group_fallback)

    def test_suggested_tags_exclude_tags_already_on_the_draft(self):
        draft = build_draft_article(
            "生成AIプロンプト運用", "生成AIプロンプト検証運用", ["ChatGPT", "生成AI"]
        )
        report = advise(draft, self.corpus)
        self.assertNotIn("ChatGPT", [s.tag for s in report.missing_tags])

    def test_tag_lift_ignores_tags_below_support_threshold(self):
        corpus = [a for a in self.corpus if a.source_tag == "生成AI活用"]
        for suggestion in tag_lift(corpus, min_support=5):
            self.assertGreaterEqual(suggestion.support, 5)

    def test_empty_corpus_is_rejected(self):
        draft = build_draft_article("t", "b", [])
        with self.assertRaises(ValueError):
            advise(draft, [])


if __name__ == "__main__":
    unittest.main()
