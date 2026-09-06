"""既知の生成モデルから合成コーパスを作る.

用途は 2 つ。

1. ネットワークなしでパイプライン全体を動かす (CI / 初回セットアップ)
2. 「分析が正しく信号を拾えるか」の検算。真の係数を仕込んだデータで
   analyze() が USABLE を返せないなら、実データで NOT_USABLE が出ても
   それは note 側の話ではなく実装の欠陥である

合成データは実データの代わりにはならない。判定の根拠は必ず実データで取る。
"""

from __future__ import annotations

import datetime as dt
import math
import random
from typing import Dict, List, Sequence

from .schema import Article

JST = dt.timezone(dt.timedelta(hours=9))

TOPICS: Dict[str, Dict[str, Sequence[str]]] = {
    "生成AI活用": {
        "tags": ["AI", "生成AI", "ChatGPT", "プロンプト", "業務効率化"],
        "vocab": [
            "生成AI", "プロンプト", "ChatGPT", "業務効率", "自動化", "検証",
            "ワークフロー", "モデル", "精度", "運用", "テンプレート", "実務",
        ],
    },
    "個人開発": {
        "tags": ["個人開発", "エンジニア", "プログラミング", "Python", "リリース"],
        "vocab": [
            "個人開発", "リリース", "設計", "実装", "テスト", "デプロイ",
            "リファクタ", "ユーザー", "機能", "収益", "技術選定", "運用コスト",
        ],
    },
    "働き方": {
        "tags": ["働き方", "キャリア", "転職", "マネジメント", "仕事"],
        "vocab": [
            "働き方", "キャリア", "面談", "評価", "裁量", "チーム",
            "転職", "報酬", "上司", "文化", "残業", "成長",
        ],
    },
}

FILLER = [
    "今日", "先週", "結果", "課題", "背景", "整理", "感想", "手順",
    "比較", "失敗", "気づき", "記録", "共有", "現場", "改善",
]


def _sentence(rng: random.Random, vocab: Sequence[str], length: int) -> str:
    words = [rng.choice(vocab) for _ in range(length)]
    return "".join(words)


def _make_body(rng: random.Random, vocab: Sequence[str], fit: float, chars: int) -> str:
    """fit が高いほどトピック語彙の比率を上げる."""
    parts: List[str] = []
    while sum(len(p) for p in parts) < chars:
        pool = vocab if rng.random() < fit else FILLER
        parts.append(_sentence(rng, pool, rng.randint(4, 9)))
        parts.append("。")
    return "".join(parts)[:chars]


def generate_corpus(
    n: int = 400, seed: int = 7, exposure_top_ratio: float = 0.18
) -> List[Article]:
    """合成コーパス.

    真の生成モデル (log スケール):
        score = 0.80 * log1p(followers)
              + 2.20 * topic_fit_true
              + 0.45 * has_eyecatch
              + 0.60 * tag_overlap_true
              - 0.35 * is_paid
              + 0.30 * prime_hour
              + noise
    """
    rng = random.Random(seed)
    now = dt.datetime.now(tz=dt.timezone.utc)
    topic_names = list(TOPICS)
    articles: List[Article] = []
    scored: List[tuple] = []

    for i in range(n):
        topic_name = topic_names[i % len(topic_names)]
        topic = TOPICS[topic_name]
        vocab = list(topic["vocab"])
        topic_tags = list(topic["tags"])

        fit_true = min(1.0, max(0.05, rng.betavariate(2.0, 3.0)))
        followers = int(math.exp(rng.gauss(5.2, 1.6)))
        has_eyecatch = rng.random() < 0.78
        is_paid = rng.random() < 0.12

        n_tags = rng.randint(0, 5)
        on_topic = rng.randint(0, min(n_tags, len(topic_tags)))
        tags = rng.sample(topic_tags, on_topic)
        off_pool = [
            t
            for name, spec in TOPICS.items()
            if name != topic_name
            for t in spec["tags"]
        ]
        tags += rng.sample(off_pool, min(n_tags - on_topic, len(off_pool)))
        tag_overlap_true = on_topic / max(1, n_tags)

        age = rng.uniform(0.5, 30.0)
        published = now - dt.timedelta(days=age)
        hour = published.astimezone(JST).hour
        prime_hour = 1.0 if 6 <= hour <= 9 or 19 <= hour <= 22 else 0.0

        body_chars = int(rng.uniform(600, 4000))
        body = _make_body(rng, vocab, fit_true, min(400, body_chars))
        title = _sentence(rng, vocab, rng.randint(2, 4))
        if rng.random() < 0.4:
            title = f"【{rng.randint(3, 10)}選】" + title

        score = (
            0.80 * math.log1p(followers)
            + 2.20 * fit_true
            + 0.45 * has_eyecatch
            + 0.60 * tag_overlap_true
            - 0.35 * is_paid
            + 0.30 * prime_hour
            + rng.gauss(0, 0.55)
        )
        # 掲載からの経過で反応が積み上がる分
        likes = max(0, int(math.expm1(max(0.0, score)) * min(1.0, age / 3.0) / 12.0))

        article = Article(
            key=f"nfixture{i:04d}",
            title=title,
            url=f"https://note.com/fixture/n/nfixture{i:04d}",
            body_excerpt=body,
            body_chars=body_chars,
            like_count=likes,
            comment_count=int(likes * rng.uniform(0.0, 0.12)),
            published_at=published.isoformat(),
            tags=tags,
            is_paid=is_paid,
            price=500 if is_paid else 0,
            has_eyecatch=has_eyecatch,
            creator_urlname=f"creator{i % 60:03d}",
            creator_nickname=f"creator{i % 60:03d}",
            creator_followers=followers,
            creator_note_count=rng.randint(1, 300),
            source_tag=topic_name,
            source_order="new",
            collected_at=now.isoformat(),
        )
        articles.append(article)
        scored.append((score, article))

    # 上位を人気/急上昇に昇格させる
    scored.sort(key=lambda pair: pair[0], reverse=True)
    cutoff = int(len(scored) * exposure_top_ratio)
    for rank, (_, article) in enumerate(scored[:cutoff]):
        article.source_order = "new,hot" if rank % 2 else "new,popular"
        article.source_rank = rank

    return articles


TRUE_SIGNALS = (
    "log_creator_followers",
    "topic_fit",
    "has_eyecatch",
    "tag_overlap",
)
