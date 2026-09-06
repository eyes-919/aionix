"""ドラフト診断 (アプリに載せる想定の機能本体).

analyze.py が「その指標は信用できるか」を判定するのに対し、
ここは「では、この下書きをどう直すか」を出す。

出力は必ず根拠つきにする。コーパス内の実測値を伴わない助言は返さない。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .features import (
    FeatureBuilder,
    JST,
    engagement_target,
    exposure_labels,
)
from .schema import Article
from .stats import RidgeRegression, Standardizer, mean
from .text import top_phrases

MIN_TAG_SUPPORT = 3


@dataclass
class TagSuggestion:
    tag: str
    winner_share: float
    pool_share: float
    lift: float
    support: int

    def as_line(self) -> str:
        return (
            f"#{self.tag} (上位群 {self.winner_share:.0%} / 母集団 {self.pool_share:.0%} "
            f"/ lift {self.lift:.2f}x / n={self.support})"
        )


@dataclass
class TimingSuggestion:
    hour_range: str
    exposure_rate: float
    sample: int


@dataclass
class DraftReport:
    predicted_percentile: float
    topic_fit: float
    topic_fit_percentile: float
    tag_overlap: float
    missing_tags: List[TagSuggestion] = field(default_factory=list)
    title_notes: List[str] = field(default_factory=list)
    timing: List[TimingSuggestion] = field(default_factory=list)
    topic_terms: List[str] = field(default_factory=list)
    group: str = ""
    group_fallback: bool = False
    reference_articles: List[Tuple[str, int, str]] = field(default_factory=list)
    corpus_size: int = 0


def _percentile_of(value: float, population: Sequence[float]) -> float:
    if not population:
        return 0.0
    below = sum(1 for v in population if v <= value)
    return below / len(population)


def tag_lift(
    articles: Sequence[Article], min_support: int = MIN_TAG_SUPPORT
) -> List[TagSuggestion]:
    """タグごとの露出率リフトを実測する.

    「タグは 3-5 個が良い」といった通説を鵜呑みにせず、
    そのコーパスで実際に露出率を押し上げているタグだけを返す。
    """
    labels = exposure_labels(articles)
    overall = mean([float(v) for v in labels]) or 1e-9
    stats: Dict[str, List[int]] = {}
    for article, label in zip(articles, labels):
        for tag in set(article.tags):
            bucket = stats.setdefault(tag, [0, 0])
            bucket[0] += 1
            bucket[1] += label

    suggestions: List[TagSuggestion] = []
    total = float(len(articles)) or 1.0
    for tag, (support, exposed) in stats.items():
        if support < min_support:
            continue
        winner_share = exposed / support
        suggestions.append(
            TagSuggestion(
                tag=tag,
                winner_share=winner_share,
                pool_share=support / total,
                lift=winner_share / overall,
                support=support,
            )
        )
    suggestions.sort(key=lambda s: (s.lift, s.support), reverse=True)
    return suggestions


def timing_table(articles: Sequence[Article]) -> List[TimingSuggestion]:
    """投稿時刻帯ごとの露出率. JST 3 時間バケット."""
    labels = exposure_labels(articles)
    buckets: Dict[int, List[int]] = {}
    for article, label in zip(articles, labels):
        published = article.published_dt
        if published is None:
            continue
        hour = published.astimezone(JST).hour
        bucket = (hour // 3) * 3
        entry = buckets.setdefault(bucket, [0, 0])
        entry[0] += 1
        entry[1] += label

    rows = [
        TimingSuggestion(
            hour_range=f"{start:02d}:00-{start + 3:02d}:00 JST",
            exposure_rate=exposed / count,
            sample=count,
        )
        for start, (count, exposed) in sorted(buckets.items())
        if count >= 5
    ]
    rows.sort(key=lambda r: r.exposure_rate, reverse=True)
    return rows


def _title_notes(title: str, corpus_titles: Sequence[str]) -> List[str]:
    notes: List[str] = []
    length = len(title)
    lengths = sorted(len(t) for t in corpus_titles if t)
    if lengths:
        median = lengths[len(lengths) // 2]
        if length > median * 1.6:
            notes.append(
                f"タイトルが {length} 文字。コーパス中央値 {median} 文字より長く、"
                "一覧表示で末尾が切れる可能性がある"
            )
        elif length < max(8, median * 0.5):
            notes.append(
                f"タイトルが {length} 文字。コーパス中央値 {median} 文字より短く、"
                "検索語との一致面積が小さい"
            )
    if not any(ch.isdigit() for ch in title):
        notes.append("タイトルに数字がない。件数・年・手順数は一覧での識別性を上げる")
    return notes


def build_draft_article(
    title: str, body: str, tags: Sequence[str], has_eyecatch: bool = True
) -> Article:
    """下書きを Article として扱えるようにする."""
    return Article(
        key="__draft__",
        title=title,
        body_excerpt=body[:400],
        body_chars=len(body),
        tags=list(tags),
        has_eyecatch=has_eyecatch,
        published_at=dt.datetime.now(tz=JST).isoformat(),
        source_order="new",
    )


MIN_GROUP_SIZE = 20


def select_group(
    draft: Article, corpus: Sequence[Article], now: Optional[dt.datetime] = None
) -> str:
    """下書きが競合するトピック (source_tag) を選ぶ.

    複数タグを混ぜたコーパスをそのまま使うと、別トピックの上位記事から
    タグや語彙を推薦してしまう。必ず 1 トピックに絞ってから助言する。
    """
    groups = {a.source_tag for a in corpus if a.source_tag}
    if not groups:
        return ""
    if draft.source_tag in groups:
        return draft.source_tag
    if len(groups) == 1:
        return next(iter(groups))
    probe = FeatureBuilder().fit(
        corpus, performance=[float(a.like_count) for a in corpus], now=now
    )
    vector = probe.index.transform(
        " ".join([draft.title, draft.title, " ".join(draft.tags), draft.body_excerpt])
    )
    from .text import cosine as _cosine

    return max(
        probe.group_centroids,
        key=lambda g: _cosine(vector, probe.group_centroids[g]),
    )


def advise(
    draft: Article,
    corpus: Sequence[Article],
    now: Optional[dt.datetime] = None,
    max_tag_suggestions: int = 8,
    group: Optional[str] = None,
) -> DraftReport:
    if not corpus:
        raise ValueError("コーパスが空。先に collect を実行すること")

    chosen = group if group is not None else select_group(draft, corpus, now=now)
    scoped = [a for a in corpus if a.source_tag == chosen] if chosen else list(corpus)
    fallback = False
    if len(scoped) < MIN_GROUP_SIZE:
        # トピック内の件数が足りない場合だけ全体にフォールバックする。
        # このとき推薦は別トピック混じりになるのでレポートに明示する。
        scoped = list(corpus)
        fallback = True

    draft = Article(**{**draft.to_dict(), "source_tag": chosen if not fallback else ""})
    corpus = scoped

    likes = [float(a.like_count) for a in corpus]
    builder = FeatureBuilder().fit(corpus, performance=likes, now=now)
    matrix = builder.matrix(corpus)
    target = engagement_target(corpus)

    scaler = Standardizer().fit(matrix)
    model = RidgeRegression(alpha=1.0).fit(scaler.transform(matrix), target)

    # ドラフトはフォロワー数が未知なのでコーパス中央値を仮置きする。
    # 「記事側で動かせる要素だけ」を比較したいので、この統制は意図的。
    draft_row = builder.row(draft)
    followers_column = sorted(row[0] for row in matrix)
    draft_row[0] = followers_column[len(followers_column) // 2]
    draft_row[1] = sorted(row[1] for row in matrix)[len(matrix) // 2]
    # 公開直後を仮定するため経過日数はコーパス最小に寄せる
    draft_row[12] = min(row[12] for row in matrix)

    corpus_scores = model.predict(scaler.transform(matrix))
    draft_score = model.predict_row(scaler.transform_row(draft_row))

    topic_fits = [builder.topic_fit(a) for a in corpus]
    draft_fit = builder.topic_fit(draft)

    draft_tags = set(draft.tags)
    suggestions = [
        s
        for s in tag_lift(corpus)
        if s.tag not in draft_tags and s.lift > 1.0
    ][:max_tag_suggestions]

    ranked = sorted(corpus, key=lambda a: a.like_count, reverse=True)[:5]
    references = [(a.title, a.like_count, a.url) for a in ranked]

    winner_vectors = [
        builder.index.transform(a.title + " " + a.body_excerpt)
        for a in ranked
    ]

    return DraftReport(
        group=chosen,
        group_fallback=fallback,
        predicted_percentile=_percentile_of(draft_score, corpus_scores),
        topic_fit=draft_fit,
        topic_fit_percentile=_percentile_of(draft_fit, topic_fits),
        tag_overlap=builder.tag_overlap(draft),
        missing_tags=suggestions,
        title_notes=_title_notes(draft.title, [a.title for a in corpus]),
        timing=timing_table(corpus)[:4],
        topic_terms=top_phrases(winner_vectors, limit=15),
        reference_articles=references,
        corpus_size=len(corpus),
    )


def format_draft_report(report: DraftReport, title: str) -> str:
    lines = [
        "# ドラフト診断",
        "",
        f"対象: {title}",
        f"競合トピック: {report.group or '(未分類)'}",
        f"参照コーパス: {report.corpus_size} 件",
        "",
        "## スコア",
        "",
        f"- 予測反応スコアの位置: 上位 {(1 - report.predicted_percentile):.0%}",
        f"- トピック適合度 (topic fit): {report.topic_fit:.3f} "
        f"(コーパス内 上位 {(1 - report.topic_fit_percentile):.0%})",
        f"- 上位群タグとの重なり: {report.tag_overlap:.3f}",
        "",
    ]

    if report.group_fallback:
        lines.append(
            "WARNING: 該当トピックの収集件数が不足したため、コーパス全体で診断した。"
            "推薦タグ・語彙に別トピックが混じる。該当タグの collect を増やすこと。"
        )
        lines.append("")

    if report.topic_fit_percentile < 0.5:
        lines.append(
            "NOTE: トピック適合度が母集団の下位半分にある。"
            "2026-02 のレコメンド刷新は LLM が本文を読んでトピックへ割り当てる方式のため、"
            "本文中に対象トピックの語彙が薄いと配信先が定まらない。"
        )
        lines.append("")

    if report.missing_tags:
        lines.append("## 追加候補タグ (露出率リフト順)")
        lines.append("")
        for suggestion in report.missing_tags:
            lines.append(f"- {suggestion.as_line()}")
        lines.append("")

    if report.title_notes:
        lines.append("## タイトル所見")
        lines.append("")
        for note in report.title_notes:
            lines.append(f"- {note}")
        lines.append("")

    if report.timing:
        lines.append("## 投稿時間帯別の露出率 (実測)")
        lines.append("")
        lines.append("| 時間帯 | 露出率 | 件数 |")
        lines.append("|---|---|---|")
        for row in report.timing:
            lines.append(
                f"| {row.hour_range} | {row.exposure_rate:.1%} | {row.sample} |"
            )
        lines.append("")

    if report.topic_terms:
        lines.append("## 上位記事の語彙 (本文に不足していれば補う)")
        lines.append("")
        lines.append(", ".join(report.topic_terms))
        lines.append("")

    if report.reference_articles:
        lines.append("## 参照した上位記事")
        lines.append("")
        for ref_title, likes, url in report.reference_articles:
            lines.append(f"- {ref_title} (スキ {likes}) {url}")
        lines.append("")

    return "\n".join(lines)
