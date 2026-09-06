"""レート制限つき HTTP クライアント (ディスクキャッシュ + 指数バックオフ)."""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

try:
    import requests
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "requests が必要です。`pip install -r requirements.txt` を実行してください。"
    ) from exc


DEFAULT_UA = (
    "noteseek-poc/0.1 (research; contact: repository owner) "
    "python-requests"
)


class HttpError(RuntimeError):
    """回復不能な HTTP エラー."""

    def __init__(self, status: int, url: str, body: str = "") -> None:
        super().__init__(f"HTTP {status} for {url}: {body[:200]}")
        self.status = status
        self.url = url


@dataclass
class ClientConfig:
    """収集ポリシー.

    min_interval_sec は note 側への負荷を抑えるための下限間隔。
    調査目的である以上、ここを短くしすぎない。
    """

    min_interval_sec: float = 1.5
    timeout_sec: float = 20.0
    max_retries: int = 4
    cache_dir: Optional[str] = ".cache/noteseek"
    cache_ttl_sec: float = 60 * 60 * 6
    user_agent: str = DEFAULT_UA
    extra_headers: Dict[str, str] = field(default_factory=dict)


class HttpClient:
    """GET 専用の薄いクライアント.

    - 呼び出し間隔を強制的に空ける
    - 429 / 5xx は指数バックオフで再試行
    - 成功レスポンスは URL ハッシュでディスクキャッシュする
    """

    def __init__(self, config: Optional[ClientConfig] = None) -> None:
        self.config = config or ClientConfig()
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": self.config.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "ja,en;q=0.8",
                **self.config.extra_headers,
            }
        )
        self._last_request_at = 0.0
        if self.config.cache_dir:
            os.makedirs(self.config.cache_dir, exist_ok=True)

    # -- cache ---------------------------------------------------------

    def _cache_path(self, url: str) -> Optional[str]:
        if not self.config.cache_dir:
            return None
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        return os.path.join(self.config.cache_dir, digest + ".json")

    def _read_cache(self, url: str) -> Optional[Any]:
        path = self._cache_path(url)
        if not path or not os.path.exists(path):
            return None
        age = time.time() - os.path.getmtime(path)
        if age > self.config.cache_ttl_sec:
            return None
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None

    def _write_cache(self, url: str, payload: Any) -> None:
        path = self._cache_path(url)
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False)
        except OSError:
            pass

    # -- request -------------------------------------------------------

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_at
        wait = self.config.min_interval_sec - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.time()

    def get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        full_url = url
        if params:
            query = urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None}
            )
            full_url = f"{url}?{query}"

        cached = self._read_cache(full_url)
        if cached is not None:
            return cached

        last_error: Optional[Exception] = None
        for attempt in range(self.config.max_retries):
            self._throttle()
            try:
                response = self._session.get(
                    full_url, timeout=self.config.timeout_sec
                )
            except requests.RequestException as exc:
                last_error = exc
                self._sleep_backoff(attempt)
                continue

            if response.status_code == 200:
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise HttpError(200, full_url, response.text) from exc
                self._write_cache(full_url, payload)
                return payload

            if response.status_code in (429, 500, 502, 503, 504):
                last_error = HttpError(
                    response.status_code, full_url, response.text
                )
                self._sleep_backoff(attempt, response.headers.get("Retry-After"))
                continue

            raise HttpError(response.status_code, full_url, response.text)

        raise HttpError(0, full_url, str(last_error))

    def _sleep_backoff(self, attempt: int, retry_after: Optional[str] = None) -> None:
        if retry_after:
            try:
                time.sleep(min(float(retry_after), 60.0))
                return
            except ValueError:
                pass
        delay = (2**attempt) + random.uniform(0, 0.5)
        time.sleep(min(delay, 30.0))
