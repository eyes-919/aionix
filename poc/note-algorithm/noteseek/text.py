"""日本語テキストの軽量ベクトル化.

形態素解析器 (MeCab / Sudachi) は環境構築コストが高く、POC の再現性を下げる。
ここでは日本語で実用的な精度が出る文字 N-gram + TF-IDF を採用する。
外部依存はゼロ。
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Dict, Iterable, List, Sequence, Tuple

_NOISE = re.compile(r"https?://\S+|[\s　]+")
_KEEP = re.compile(r"[0-9A-Za-z぀-ゟ゠-ヿ一-鿿ー]+")

# 単体では意味を持ちにくい語。トピック語抽出時に落とす。
STOPWORDS = {
    "こと", "もの", "ため", "よう", "これ", "それ", "あれ", "ここ", "そこ",
    "です", "ます", "した", "して", "する", "ある", "いる", "なる", "れる",
    "から", "まで", "ので", "けど", "でも", "また", "そして", "しかし",
    "思い", "思う", "自分", "今回", "とき", "ときに", "たち", "さん",
    "the", "and", "for", "you", "this", "that", "with", "are", "was",
}


def normalize(text: str) -> str:
    """NFKC 正規化 + URL / 空白除去 + 小文字化."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _NOISE.sub(" ", text)
    return text.lower()


def char_ngrams(text: str, sizes: Sequence[int] = (2, 3)) -> List[str]:
    """文字 N-gram。記号や空白をまたぐ gram は作らない."""
    grams: List[str] = []
    for chunk in _KEEP.findall(normalize(text)):
        for size in sizes:
            if len(chunk) < size:
                if len(chunk) >= 2:
                    grams.append(chunk)
                continue
            for i in range(len(chunk) - size + 1):
                grams.append(chunk[i : i + size])
    return grams


class TfidfIndex:
    """文書集合の TF-IDF インデックス.

    note の 2026-02 レコメンド刷新は「LLM が本文を読んでトピックに割り当てる」
    方式である。本 POC はその代理として、同一トピック上位記事群の重心ベクトルと
    ドラフトの近さ (topic fit) を測る。
    """

    def __init__(self, sizes: Sequence[int] = (2, 3), min_df: int = 2) -> None:
        self.sizes = tuple(sizes)
        self.min_df = min_df
        self.idf: Dict[str, float] = {}
        self.n_docs = 0

    def fit(self, documents: Iterable[str]) -> "TfidfIndex":
        docs = list(documents)
        self.n_docs = len(docs)
        df: Counter = Counter()
        for doc in docs:
            df.update(set(char_ngrams(doc, self.sizes)))
        self.idf = {
            gram: math.log((1 + self.n_docs) / (1 + count)) + 1.0
            for gram, count in df.items()
            if count >= self.min_df
        }
        return self

    def transform(self, document: str) -> Dict[str, float]:
        grams = char_ngrams(document, self.sizes)
        if not grams:
            return {}
        counts = Counter(grams)
        total = float(len(grams))
        vector = {
            gram: (count / total) * self.idf[gram]
            for gram, count in counts.items()
            if gram in self.idf
        }
        return l2_normalize(vector)

    def fit_transform(self, documents: Iterable[str]) -> List[Dict[str, float]]:
        docs = list(documents)
        self.fit(docs)
        return [self.transform(doc) for doc in docs]


def l2_normalize(vector: Dict[str, float]) -> Dict[str, float]:
    norm = math.sqrt(sum(value * value for value in vector.values()))
    if norm == 0.0:
        return {}
    return {key: value / norm for key, value in vector.items()}


def cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return sum(value * b.get(key, 0.0) for key, value in a.items())


def centroid(vectors: Sequence[Dict[str, float]]) -> Dict[str, float]:
    """複数ベクトルの重心 (L2 正規化済み)."""
    acc: Dict[str, float] = {}
    for vector in vectors:
        for key, value in vector.items():
            acc[key] = acc.get(key, 0.0) + value
    return l2_normalize(acc)


def merge_grams(grams: Sequence[str], max_len: int = 10) -> List[str]:
    """重なり合う文字 N-gram を連結して読める語に戻す.

    "技術選" + "術選定" -> "技術選定"。
    連結は「右側の gram の先頭 (長さ n-1) が現在の語尾と一致する」場合だけに限る。
    1 文字だけの重なりで繋ぐと無関係な gram が数珠つなぎになり、
    "実務検証精度モデルテンプレート..." のような読めない文字列になるため。
    """
    remaining = list(dict.fromkeys(grams))
    result: List[str] = []

    while remaining:
        term = remaining.pop(0)
        extended = True
        while extended and len(term) < max_len:
            extended = False
            for i, candidate in enumerate(remaining):
                overlap = len(candidate) - 1
                if overlap < 2:
                    continue
                if term.endswith(candidate[:overlap]):
                    term = term + candidate[overlap:]
                    remaining.pop(i)
                    extended = True
                    break
        result.append(term)

    # 他の語に完全に含まれる語は落とす
    deduped: List[str] = []
    for term in sorted(result, key=len, reverse=True):
        if not any(term in longer for longer in deduped):
            deduped.append(term)
    return deduped


def top_terms(
    vectors: Sequence[Dict[str, float]], limit: int = 30, min_len: int = 3
) -> List[Tuple[str, float]]:
    """重心ベクトルから代表語を取り出す (人が読むための要約用)."""
    weights = centroid(vectors)
    ranked = [
        (gram, weight)
        for gram, weight in weights.items()
        if len(gram) >= min_len and gram not in STOPWORDS
    ]
    ranked.sort(key=lambda pair: pair[1], reverse=True)
    return ranked[:limit]


def top_phrases(
    vectors: Sequence[Dict[str, float]], limit: int = 15
) -> List[str]:
    """代表語を人間が読める形にまとめて返す."""
    grams = [gram for gram, _ in top_terms(vectors, limit=limit * 4)]
    phrases = [p for p in merge_grams(grams) if len(p) >= 3 and p not in STOPWORDS]
    return phrases[:limit]
