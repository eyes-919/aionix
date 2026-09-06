"""note.com 非公式 API クライアント.

IMPORTANT: これらのエンドポイントは note が公式に文書化したものではない。
note のフロントエンドが利用している URL を調査記事から整理したものであり、
予告なく変更・廃止される。本 POC では次の方針を取る。

1. エンドポイントは候補リストとして持ち、実際に 200 を返したものを採用する
2. どの候補が生きているかは `probe` コマンドで明示的に確認できるようにする
3. レスポンス形状の揺れは schema.py 側で吸収する

これにより「調べた時点では動いていたが今は動かない」という POC の典型的な
破綻を、コード変更なしに検知できる。
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from .httpclient import HttpClient, HttpError

BASE = "https://note.com/api"

# 掲載順序。note の画面上の「新着 / 人気 / 急上昇」に対応する。
ORDER_NEW = "new"
ORDER_POPULAR = "popular"
ORDER_HOT = "hot"
ORDERS = (ORDER_NEW, ORDER_POPULAR, ORDER_HOT)


def _as_list(payload: Any, *keys: str) -> List[Dict[str, Any]]:
    """レスポンスから記事配列を取り出す。API バージョン差を吸収する."""
    if payload is None:
        return []
    node: Any = payload
    if isinstance(node, dict) and "data" in node:
        node = node["data"]
    if isinstance(node, list):
        return [item for item in node if isinstance(item, dict)]
    if isinstance(node, dict):
        for key in keys:
            value = node.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                for inner in ("contents", "notes"):
                    nested = value.get(inner)
                    if isinstance(nested, list):
                        return [i for i in nested if isinstance(i, dict)]
    return []


class NoteApi:
    """読み取り専用クライアント. 認証は行わない."""

    def __init__(self, client: Optional[HttpClient] = None) -> None:
        self.client = client or HttpClient()
        self._resolved: Dict[str, str] = {}

    # -- 低レベル -------------------------------------------------------

    def _try_candidates(
        self, kind: str, candidates: Sequence[Tuple[str, Dict[str, Any]]]
    ) -> Tuple[Any, str]:
        """候補 URL を順に試し、最初に成功したものを記憶して返す."""
        remembered = self._resolved.get(kind)
        ordered = list(candidates)
        if remembered:
            ordered.sort(key=lambda c: 0 if c[0] == remembered else 1)

        errors: List[str] = []
        for url, params in ordered:
            try:
                payload = self.client.get_json(url, params)
            except HttpError as exc:
                errors.append(f"{url} -> {exc.status}")
                continue
            self._resolved[kind] = url
            return payload, url
        raise HttpError(0, kind, "; ".join(errors) or "no candidate succeeded")

    # -- キーワード検索 -------------------------------------------------

    def search_notes(
        self, query: str, start: int = 0, size: int = 20, sort: str = "popular"
    ) -> List[Dict[str, Any]]:
        """キーワード検索。sort は popular / new / hot を想定."""
        payload, _ = self._try_candidates(
            "search_notes",
            [
                (
                    f"{BASE}/v3/searches",
                    {
                        "context": "note",
                        "q": query,
                        "size": size,
                        "start": start,
                        "sort": sort,
                    },
                ),
                (
                    f"{BASE}/v3/searches",
                    {"context": "note", "q": query, "size": size, "start": start},
                ),
            ],
        )
        if isinstance(payload, dict):
            data = payload.get("data", payload)
            if isinstance(data, dict) and isinstance(data.get("notes"), dict):
                return _as_list(data["notes"], "contents")
        return _as_list(payload, "notes", "contents")

    # -- ハッシュタグ ---------------------------------------------------

    def hashtag_notes(
        self, tag: str, order: str = ORDER_NEW, page: int = 1
    ) -> List[Dict[str, Any]]:
        """ハッシュタグ配下の記事一覧を指定順序で取得する.

        order = new / popular / hot は note の「新着 / 人気 / 急上昇」に対応する。
        この 3 つの差分が、本 POC における「露出された記事」のラベル源になる。
        """
        if order not in ORDERS:
            raise ValueError(f"order must be one of {ORDERS}, got {order!r}")
        payload, _ = self._try_candidates(
            f"hashtag_notes:{order}",
            [
                (f"{BASE}/v3/hashtags/{tag}/notes", {"order": order, "page": page}),
                (f"{BASE}/v2/hashtags/{tag}/notes", {"order": order, "page": page}),
                (
                    f"{BASE}/v3/searches",
                    {
                        "context": "hashtag",
                        "q": tag,
                        "size": 20,
                        "start": (page - 1) * 20,
                        "sort": order,
                    },
                ),
            ],
        )
        return _as_list(payload, "notes", "contents", "hashtag_notes")

    def hashtag_info(self, tag: str) -> Dict[str, Any]:
        payload, _ = self._try_candidates(
            "hashtag_info",
            [
                (f"{BASE}/v2/hashtags/{tag}", {}),
                (f"{BASE}/v3/hashtags/{tag}", {}),
            ],
        )
        if isinstance(payload, dict):
            data = payload.get("data", payload)
            if isinstance(data, dict):
                return data
        return {}

    # -- カテゴリ -------------------------------------------------------

    def category_notes(
        self, category: str, sort: str = "new", page: int = 1
    ) -> List[Dict[str, Any]]:
        """カテゴリページの記事一覧.

        2026-02 のレコメンド刷新でカテゴリ / トピックが拡張された領域であり、
        「LLM 自動タグ付けがどのトピックに記事を置いたか」の観測点になる。
        """
        payload, _ = self._try_candidates(
            "category_notes",
            [
                (
                    f"{BASE}/v2/categories/{category}",
                    {"note_intro_only": "true", "sort": sort, "page": page},
                ),
                (
                    f"{BASE}/v3/categories/{category}/notes",
                    {"sort": sort, "page": page},
                ),
            ],
        )
        return _as_list(payload, "notes", "contents")

    # -- 記事 / クリエイター --------------------------------------------

    def note_detail(self, key: str) -> Dict[str, Any]:
        """記事詳細。本文・ハッシュタグ・有料設定などを含む."""
        payload, _ = self._try_candidates(
            "note_detail",
            [
                (f"{BASE}/v3/notes/{key}", {}),
                (f"{BASE}/v1/notes/{key}", {}),
            ],
        )
        if isinstance(payload, dict):
            data = payload.get("data", payload)
            if isinstance(data, dict):
                return data
        return {}

    def creator_notes(
        self, urlname: str, page: int = 1
    ) -> List[Dict[str, Any]]:
        payload, _ = self._try_candidates(
            "creator_notes",
            [
                (
                    f"{BASE}/v2/creators/{urlname}/contents",
                    {"kind": "note", "page": page},
                ),
                (
                    f"{BASE}/v3/searches",
                    {"context": "user", "q": urlname, "size": 20},
                ),
            ],
        )
        return _as_list(payload, "contents", "notes")

    def creator_info(self, urlname: str) -> Dict[str, Any]:
        payload, _ = self._try_candidates(
            "creator_info", [(f"{BASE}/v2/creators/{urlname}", {})]
        )
        if isinstance(payload, dict):
            data = payload.get("data", payload)
            if isinstance(data, dict):
                return data
        return {}

    # -- 疎通確認 -------------------------------------------------------

    def probe(self, sample_tag: str = "AI", sample_query: str = "AI") -> List[Dict[str, Any]]:
        """各エンドポイントが現在も生きているかを確認する.

        POC を再実行したときに「API 仕様が変わった」のか
        「分析結果が変わった」のかを切り分けるために必ず先に走らせる。
        """
        checks = [
            ("search_notes", lambda: self.search_notes(sample_query, size=3)),
            ("hashtag_notes:new", lambda: self.hashtag_notes(sample_tag, ORDER_NEW)),
            (
                "hashtag_notes:popular",
                lambda: self.hashtag_notes(sample_tag, ORDER_POPULAR),
            ),
            ("hashtag_notes:hot", lambda: self.hashtag_notes(sample_tag, ORDER_HOT)),
            ("hashtag_info", lambda: self.hashtag_info(sample_tag)),
        ]
        results: List[Dict[str, Any]] = []
        for name, call in checks:
            try:
                value = call()
                count = len(value) if isinstance(value, (list, dict)) else 0
                results.append(
                    {
                        "endpoint": name,
                        "status": "OK" if count else "EMPTY",
                        "items": count,
                        "resolved_url": self._resolved.get(name.split(":")[0])
                        or self._resolved.get(name),
                    }
                )
            except HttpError as exc:
                results.append(
                    {"endpoint": name, "status": "NG", "items": 0, "error": str(exc)}
                )
        return results


def iter_pages(
    fetch, max_pages: int = 5, start_page: int = 1
) -> Iterator[Dict[str, Any]]:
    """ページャ。空ページで打ち切る."""
    for page in range(start_page, start_page + max_pages):
        items = fetch(page)
        if not items:
            return
        for item in items:
            yield item
