"""note API のレスポンスを解析可能な正規形に落とす.

note の API は v1 / v2 / v3 と GraphQL 移行が混在しており、同じ意味の値が
snake_case と camelCase の両方で返る。ここで一度だけ吸収する。
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

_TAG_PREFIX = re.compile(r"^[#＃]")
_HTML_TAG = re.compile(r"<[^>]+>")


def _first(source: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in source and source[key] is not None:
            return source[key]
    return default


def _to_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return default
    return default


def parse_datetime(value: Any) -> Optional[dt.datetime]:
    """note が返す各種日時表現を timezone-aware な datetime にする."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    for candidate in (text, text.replace(" ", "T")):
        try:
            parsed = dt.datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            # note の日時は JST 表記で tz が落ちて返ることがある
            parsed = parsed.replace(tzinfo=dt.timezone(dt.timedelta(hours=9)))
        return parsed
    return None


def strip_html(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return _HTML_TAG.sub(" ", value)


def normalize_tag(value: Any) -> Optional[str]:
    """ハッシュタグ表現を '#' なしの素の文字列にする."""
    if isinstance(value, dict):
        value = _first(value, "name", "hashtag", "title")
        if isinstance(value, dict):
            value = _first(value, "name", "title")
    if not isinstance(value, str):
        return None
    tag = _TAG_PREFIX.sub("", value).strip()
    return tag or None


def extract_tags(raw: Dict[str, Any]) -> List[str]:
    tags: List[str] = []
    for key in ("hashtags", "hashtag_notes", "tags", "note_hashtags"):
        node = raw.get(key)
        if not isinstance(node, list):
            continue
        for item in node:
            if isinstance(item, dict) and "hashtag" in item:
                item = item["hashtag"]
            tag = normalize_tag(item)
            if tag and tag not in tags:
                tags.append(tag)
    return tags


@dataclass
class Article:
    """分析単位。1 記事 1 レコード."""

    key: str
    title: str
    url: str = ""
    body_excerpt: str = ""
    body_chars: int = 0
    like_count: int = 0
    comment_count: int = 0
    published_at: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    is_paid: bool = False
    price: int = 0
    has_eyecatch: bool = False
    is_magazine_featured: bool = False
    creator_urlname: str = ""
    creator_nickname: str = ""
    creator_followers: int = 0
    creator_note_count: int = 0
    # 収集時に付与するラベル
    source_tag: str = ""
    source_order: str = ""
    source_rank: int = -1
    collected_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def published_dt(self) -> Optional[dt.datetime]:
        return parse_datetime(self.published_at)


def from_raw(raw: Dict[str, Any]) -> Optional[Article]:
    """note API の 1 レコードを Article にする. 記事でなければ None."""
    if not isinstance(raw, dict):
        return None

    key = _first(raw, "key", "id", "noteKey", "note_key")
    if key is None:
        return None
    key = str(key)

    title = _first(raw, "name", "title", default="") or ""
    body_raw = _first(raw, "body", "description", "bodyText", default="") or ""
    body_text = strip_html(body_raw)

    user = _first(raw, "user", "creator", "author", default={}) or {}
    if not isinstance(user, dict):
        user = {}

    eyecatch = _first(raw, "eyecatch", "eyecatch_url", "eyecatchUrl", "thumbnail")
    price = _to_int(_first(raw, "price", default=0))
    is_paid = bool(price) or bool(_first(raw, "is_limited", "isLimited", default=False))

    return Article(
        key=key,
        title=title,
        url=_first(raw, "note_url", "noteUrl", "url", default="") or "",
        body_excerpt=body_text[:400],
        body_chars=len(body_text),
        like_count=_to_int(_first(raw, "like_count", "likeCount", "likes_count")),
        comment_count=_to_int(
            _first(raw, "comment_count", "commentCount", "comments_count")
        ),
        published_at=_first(
            raw, "publish_at", "publishAt", "published_at", "created_at", "createdAt"
        ),
        tags=extract_tags(raw),
        is_paid=is_paid,
        price=price,
        has_eyecatch=bool(eyecatch),
        is_magazine_featured=bool(
            _first(raw, "is_magazine_featured", "isPickup", "pickup", default=False)
        ),
        creator_urlname=_first(user, "urlname", "url_name", default="") or "",
        creator_nickname=_first(user, "nickname", "name", default="") or "",
        creator_followers=_to_int(
            _first(user, "followerCount", "follower_count", "followersCount")
        ),
        creator_note_count=_to_int(_first(user, "noteCount", "note_count")),
    )


def from_raw_many(rows: List[Dict[str, Any]]) -> List[Article]:
    out: List[Article] = []
    for row in rows:
        article = from_raw(row)
        if article is not None and article.title:
            out.append(article)
    return out
