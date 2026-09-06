"""コーパス収集.

観測設計 (ここが POC の肝):

  母集団 = ハッシュタグの「新着」タブに出た記事 (露出前の候補プール)
  陽性   = そのうち「人気」または「急上昇」タブにも現れた記事

これで「露出された記事の特徴」ではなく「露出される記事の特徴」を見る。
人気タブだけを集めて分析すると生存者バイアスで結論が壊れるため、
必ず新着プールを母集団に取る。
"""

from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

from .api import ORDER_HOT, ORDER_NEW, ORDER_POPULAR, NoteApi
from .httpclient import HttpError
from .schema import Article, from_raw_many


@dataclass
class CollectionResult:
    articles: List[Article]
    tag: str
    pool_size: int
    exposed_size: int
    errors: List[str]

    @property
    def exposure_rate(self) -> float:
        return self.exposed_size / self.pool_size if self.pool_size else 0.0


def _merge_orders(existing: str, new_order: str) -> str:
    orders = [o for o in existing.split(",") if o]
    if new_order not in orders:
        orders.append(new_order)
    return ",".join(orders)


def collect_tag(
    api: NoteApi,
    tag: str,
    pool_pages: int = 5,
    exposed_pages: int = 3,
) -> CollectionResult:
    """1 ハッシュタグ分のコーパスを作る."""
    by_key: Dict[str, Article] = {}
    errors: List[str] = []
    now = dt.datetime.now(tz=dt.timezone.utc).isoformat()

    def ingest(order: str, pages: int) -> int:
        seen = 0
        for page in range(1, pages + 1):
            try:
                raw = api.hashtag_notes(tag, order=order, page=page)
            except HttpError as exc:
                errors.append(f"{tag}/{order}/p{page}: {exc}")
                break
            if not raw:
                break
            for rank, article in enumerate(from_raw_many(raw)):
                seen += 1
                existing = by_key.get(article.key)
                if existing is None:
                    article.source_tag = tag
                    article.source_order = order
                    article.source_rank = (page - 1) * len(raw) + rank
                    article.collected_at = now
                    by_key[article.key] = article
                else:
                    existing.source_order = _merge_orders(
                        existing.source_order, order
                    )
                    # 露出タブ側の順位のほうが情報量が高い
                    if order != ORDER_NEW:
                        existing.source_rank = (page - 1) * len(raw) + rank
        return seen

    ingest(ORDER_NEW, pool_pages)
    pool_keys = set(by_key)
    ingest(ORDER_POPULAR, exposed_pages)
    ingest(ORDER_HOT, exposed_pages)

    articles = list(by_key.values())
    exposed = sum(
        1
        for a in articles
        if a.key in pool_keys
        and {o for o in a.source_order.split(",") if o} & {ORDER_POPULAR, ORDER_HOT}
    )
    return CollectionResult(
        articles=articles,
        tag=tag,
        pool_size=len(pool_keys),
        exposed_size=exposed,
        errors=errors,
    )


def collect_tags(
    api: NoteApi,
    tags: Sequence[str],
    pool_pages: int = 5,
    exposed_pages: int = 3,
) -> List[CollectionResult]:
    return [collect_tag(api, tag, pool_pages, exposed_pages) for tag in tags]


def enrich_with_detail(
    api: NoteApi, articles: Sequence[Article], limit: int = 0
) -> int:
    """一覧 API に本文長やタグが含まれない場合に詳細で補完する.

    リクエスト数が記事数だけ増えるため、既定では無効 (limit=0)。
    """
    filled = 0
    targets = [a for a in articles if a.body_chars == 0 or not a.tags]
    if limit:
        targets = targets[:limit]
    for article in targets:
        try:
            detail = api.note_detail(article.key)
        except HttpError:
            continue
        from .schema import from_raw

        merged = from_raw(detail)
        if merged is None:
            continue
        if merged.body_chars:
            article.body_chars = merged.body_chars
            article.body_excerpt = merged.body_excerpt or article.body_excerpt
        if merged.tags:
            article.tags = merged.tags
        if merged.creator_followers:
            article.creator_followers = merged.creator_followers
        filled += 1
    return filled


# -- 永続化 -------------------------------------------------------------


def save_jsonl(articles: Iterable[Article], path: str) -> int:
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    count = 0
    with open(path, "w", encoding="utf-8") as handle:
        for article in articles:
            handle.write(json.dumps(article.to_dict(), ensure_ascii=False) + "\n")
            count += 1
    return count


def load_jsonl(path: str) -> List[Article]:
    articles: List[Article] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            articles.append(Article(**payload))
    return articles
