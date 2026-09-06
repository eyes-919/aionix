"""記事から説明変数を作る.

設計方針:
- 事前に「効くはず」と決め打たず、調査記事で語られている仮説を
  すべて特徴量として並べ、データに否定させる
- 露出時間 (age_days) は必ず入れる。古い記事ほどスキが積み上がるため、
  これを統制しないと「文字数が効く」等の疑似相関を拾う
"""

from __future__ import annotations

import datetime as dt
import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

from .schema import Article
from .text import TfidfIndex, centroid, cosine

_DIGIT = re.compile(r"[0-9０-９]")
_BRACKET = re.compile(r"[【】\[\]（）()「」『』]")
_QUESTION = re.compile(r"[?？]")
_EXCLAM = re.compile(r"[!！]")
_SEPARATOR = re.compile(r"[|｜:：\-—~〜]")

JST = dt.timezone(dt.timedelta(hours=9))

# 出力順を固定する。係数表の可読性のため。
FEATURE_NAMES: Tuple[str, ...] = (
    "log_creator_followers",
    "log_creator_notes",
    "title_chars",
    "title_has_digit",
    "title_has_bracket",
    "title_has_question",
    "title_has_exclam",
    "title_has_separator",
    "log_body_chars",
    "tag_count",
    "has_eyecatch",
    "is_paid",
    "log_age_days",
    "publish_hour_sin",
    "publish_hour_cos",
    "is_weekend",
    "topic_fit",
    "tag_overlap",
)


# 書き手が記事単位では動かせない変数。効果推定では統制側に回す。
CONTROL_FEATURES: Tuple[str, ...] = (
    "log_creator_followers",
    "log_creator_notes",
    "log_age_days",
)

# 下書き段階で書き手が動かせる変数。施策の対象はこちらだけ。
ACTIONABLE_FEATURES: Tuple[str, ...] = tuple(
    name for name in FEATURE_NAMES if name not in CONTROL_FEATURES
)


def _log1p(value: float) -> float:
    return math.log1p(max(0.0, float(value)))


def age_days(article: Article, now: Optional[dt.datetime] = None) -> float:
    published = article.published_dt
    if published is None:
        return 0.0
    reference = now or dt.datetime.now(tz=dt.timezone.utc)
    delta = (reference - published).total_seconds() / 86400.0
    return max(0.0, delta)


def document_of(article: Article) -> str:
    """トピック判定に使うテキスト。タイトルを重めに扱う."""
    return " ".join(
        [article.title, article.title, " ".join(article.tags), article.body_excerpt]
    )


class FeatureBuilder:
    """コーパス全体を見てから各記事の特徴量を作る.

    topic_fit と tag_overlap は「同じトピック内の上位群にどれだけ近いか」なので、
    source_tag ごとにグループを切って基準ベクトルを作る。
    複数タグを混ぜたコーパスで単一の重心を取ると、トピック適合度が
    「どのトピックにも中くらい似ている記事」を高く評価してしまい意味を失う。
    """

    def __init__(self, top_ratio: float = 0.2, min_top: int = 5) -> None:
        self.top_ratio = top_ratio
        self.min_top = min_top
        self.index = TfidfIndex()
        self.group_centroids: Dict[str, Dict[str, float]] = {}
        self.group_winner_tags: Dict[str, Dict[str, float]] = {}
        self.reference_time: Optional[dt.datetime] = None
        self.default_group: str = ""

    @staticmethod
    def group_of(article: Article) -> str:
        return article.source_tag or ""

    def fit(
        self,
        articles: Sequence[Article],
        performance: Optional[Sequence[float]] = None,
        now: Optional[dt.datetime] = None,
    ) -> "FeatureBuilder":
        self.reference_time = now or dt.datetime.now(tz=dt.timezone.utc)
        documents = [document_of(a) for a in articles]
        vectors = self.index.fit_transform(documents)

        if performance is None:
            performance = [float(a.like_count) for a in articles]

        groups: Dict[str, List[int]] = {}
        for i, article in enumerate(articles):
            groups.setdefault(self.group_of(article), []).append(i)

        for group, indices in groups.items():
            n_top = max(self.min_top, int(len(indices) * self.top_ratio))
            top_indices = sorted(
                indices, key=lambda i: performance[i], reverse=True
            )[: min(n_top, len(indices))]
            self.group_centroids[group] = centroid(
                [vectors[i] for i in top_indices]
            )

            tag_counts: Dict[str, int] = {}
            for i in top_indices:
                for tag in articles[i].tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
            total = float(len(top_indices)) or 1.0
            self.group_winner_tags[group] = {
                tag: count / total for tag, count in tag_counts.items()
            }

        if len(groups) == 1:
            self.default_group = next(iter(groups))
        return self

    # -- 単体変換 -------------------------------------------------------

    def _resolve_group(self, article: Article) -> Optional[str]:
        group = self.group_of(article)
        if group in self.group_centroids:
            return group
        if self.default_group in self.group_centroids:
            return self.default_group
        return None

    def topic_fit(self, article: Article) -> float:
        """所属トピックの上位群重心とのコサイン類似度.

        グループが特定できない下書きについては、全トピックの中で
        最もよく合うものを採用する (配信先が定まるかどうかを見たいため)。
        """
        if not self.group_centroids:
            return 0.0
        vector = self.index.transform(document_of(article))
        group = self._resolve_group(article)
        if group is not None:
            return cosine(vector, self.group_centroids[group])
        return max(
            (cosine(vector, c) for c in self.group_centroids.values()), default=0.0
        )

    def tag_overlap(self, article: Article) -> float:
        if not article.tags or not self.group_winner_tags:
            return 0.0
        group = self._resolve_group(article)
        if group is not None:
            weights = self.group_winner_tags[group]
        else:
            weights = {}
            for table in self.group_winner_tags.values():
                for tag, value in table.items():
                    weights[tag] = max(weights.get(tag, 0.0), value)
        scores = [weights.get(tag, 0.0) for tag in article.tags]
        return sum(scores) / len(scores)

    def row(self, article: Article) -> List[float]:
        title = article.title or ""
        published = article.published_dt
        hour = published.astimezone(JST).hour if published else 12
        weekday = published.astimezone(JST).weekday() if published else 0

        return [
            _log1p(article.creator_followers),
            _log1p(article.creator_note_count),
            float(len(title)),
            1.0 if _DIGIT.search(title) else 0.0,
            1.0 if _BRACKET.search(title) else 0.0,
            1.0 if _QUESTION.search(title) else 0.0,
            1.0 if _EXCLAM.search(title) else 0.0,
            1.0 if _SEPARATOR.search(title) else 0.0,
            _log1p(article.body_chars),
            float(len(article.tags)),
            1.0 if article.has_eyecatch else 0.0,
            1.0 if article.is_paid else 0.0,
            _log1p(age_days(article, self.reference_time)),
            math.sin(2 * math.pi * hour / 24.0),
            math.cos(2 * math.pi * hour / 24.0),
            1.0 if weekday >= 5 else 0.0,
            self.topic_fit(article),
            self.tag_overlap(article),
        ]

    def matrix(self, articles: Sequence[Article]) -> List[List[float]]:
        return [self.row(article) for article in articles]


def engagement_target(articles: Sequence[Article]) -> List[float]:
    """反応の代理指標. スキ数は裾が重いので対数化する.

    NOTE: ビュー数は自分の記事以外では取得できない。したがって POC では
    (1) スキ数 = 反応の代理, (2) 人気/急上昇への掲載 = 露出の代理
    の 2 本立てで評価する。
    """
    return [_log1p(a.like_count) for a in articles]


def exposure_labels(articles: Sequence[Article]) -> List[int]:
    """人気 / 急上昇タブに現れたかどうかの二値ラベル.

    source_order には記事が観測されたタブが "new,hot" のように連結で入る。
    新着プールを母集団とし、そのうち人気/急上昇に昇格したものを陽性とする。
    """
    labels: List[int] = []
    for article in articles:
        orders = {o for o in (article.source_order or "").split(",") if o}
        labels.append(1 if orders & {"popular", "hot"} else 0)
    return labels
