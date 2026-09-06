"""noteseek コマンドライン.

  python -m noteseek probe                 API 疎通確認
  python -m noteseek collect --tags AI 生成AI --out data/corpus.jsonl
  python -m noteseek analyze --corpus data/corpus.jsonl
  python -m noteseek advise  --corpus data/corpus.jsonl --draft draft.md --tags AI
  python -m noteseek selftest              合成データで実装を検算
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional, Sequence

from .advise import advise, build_draft_article, format_draft_report
from .analyze import analyze, format_report
from .api import NoteApi
from .collect import collect_tags, enrich_with_detail, load_jsonl, save_jsonl
from .fixtures import TRUE_SIGNALS, generate_corpus
from .httpclient import ClientConfig, HttpClient


def _api(args: argparse.Namespace) -> NoteApi:
    return NoteApi(
        HttpClient(
            ClientConfig(
                min_interval_sec=args.interval,
                cache_dir=None if args.no_cache else ".cache/noteseek",
            )
        )
    )


def cmd_probe(args: argparse.Namespace) -> int:
    results = _api(args).probe(sample_tag=args.tag, sample_query=args.tag)
    print("# API 疎通確認\n")
    print("| endpoint | status | items | url |")
    print("|---|---|---|---|")
    for row in results:
        print(
            f"| {row['endpoint']} | {row['status']} | {row['items']} "
            f"| {row.get('resolved_url') or row.get('error', '')} |"
        )
    ok = sum(1 for r in results if r["status"] == "OK")
    print(f"\n{ok}/{len(results)} エンドポイントが応答した。")
    return 0 if ok else 1


def cmd_collect(args: argparse.Namespace) -> int:
    api = _api(args)
    results = collect_tags(
        api, args.tags, pool_pages=args.pool_pages, exposed_pages=args.exposed_pages
    )
    articles = []
    print("# 収集結果\n")
    print("| tag | プール | 露出 | 露出率 | エラー |")
    print("|---|---|---|---|---|")
    for result in results:
        articles.extend(result.articles)
        print(
            f"| {result.tag} | {result.pool_size} | {result.exposed_size} "
            f"| {result.exposure_rate:.1%} | {len(result.errors)} |"
        )
        for error in result.errors:
            print(f"  WARNING: {error}", file=sys.stderr)

    if args.detail_limit:
        filled = enrich_with_detail(api, articles, limit=args.detail_limit)
        print(f"\n詳細補完: {filled} 件")

    count = save_jsonl(articles, args.out)
    print(f"\n{count} 件を {args.out} に保存した。")
    return 0 if count else 1


def cmd_analyze(args: argparse.Namespace) -> int:
    articles = load_jsonl(args.corpus)
    report = analyze(articles, folds=args.folds)
    text = format_report(report)
    print(text)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
    return 0 if report.verdict in ("USABLE", "PARTIALLY_USABLE") else 2


def cmd_advise(args: argparse.Namespace) -> int:
    corpus = load_jsonl(args.corpus)
    with open(args.draft, "r", encoding="utf-8") as handle:
        raw = handle.read()
    lines = [line for line in raw.splitlines() if line.strip()]
    title = args.title or (lines[0].lstrip("# ").strip() if lines else "(無題)")
    body = "\n".join(lines[1:]) if not args.title else raw

    draft = build_draft_article(title, body, args.tags or [])
    report = advise(draft, corpus, group=args.group)
    text = format_draft_report(report, title)
    print(text)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
    return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    """合成データで、既知の信号を分析器が拾えるかを確認する."""
    corpus = generate_corpus(n=args.n, seed=args.seed)
    report = analyze(corpus, folds=5)
    print(format_report(report))

    print("## 検算: 仕込んだ信号を検出できたか\n")
    detected = set()
    for model in (report.engagement, report.exposure):
        if model is None:
            continue
        detected |= {f.name for f in model.findings if f.significant}

    missed: List[str] = []
    print("| 仕込んだ信号 | 検出 |")
    print("|---|---|")
    for signal in TRUE_SIGNALS:
        hit = signal in detected
        if not hit:
            missed.append(signal)
        print(f"| {signal} | {'YES' if hit else 'NO'} |")

    ok = report.verdict == "USABLE" and not missed
    print(f"\nSELFTEST: {'PASS' if ok else 'FAIL'}")
    if missed:
        print(f"未検出: {', '.join(missed)}")
    if args.out_corpus:
        save_jsonl(corpus, args.out_corpus)
        print(f"合成コーパスを {args.out_corpus} に保存した。")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="noteseek", description="note 配信アルゴリズム調査 POC"
    )
    parser.add_argument(
        "--interval", type=float, default=1.5, help="API 呼び出し間隔の下限 (秒)"
    )
    parser.add_argument("--no-cache", action="store_true", help="ディスクキャッシュを使わない")
    sub = parser.add_subparsers(dest="command", required=True)

    probe = sub.add_parser("probe", help="API エンドポイントの疎通確認")
    probe.add_argument("--tag", default="AI")
    probe.set_defaults(func=cmd_probe)

    collect = sub.add_parser("collect", help="ハッシュタグ単位でコーパスを収集")
    collect.add_argument("--tags", nargs="+", required=True)
    collect.add_argument("--pool-pages", type=int, default=5)
    collect.add_argument("--exposed-pages", type=int, default=3)
    collect.add_argument("--detail-limit", type=int, default=0)
    collect.add_argument("--out", default="data/corpus.jsonl")
    collect.set_defaults(func=cmd_collect)

    analyze_cmd = sub.add_parser("analyze", help="仮説検証と POC 判定")
    analyze_cmd.add_argument("--corpus", default="data/corpus.jsonl")
    analyze_cmd.add_argument("--folds", type=int, default=5)
    analyze_cmd.add_argument("--out")
    analyze_cmd.set_defaults(func=cmd_analyze)

    advise_cmd = sub.add_parser("advise", help="下書きを診断する")
    advise_cmd.add_argument("--corpus", default="data/corpus.jsonl")
    advise_cmd.add_argument("--draft", required=True)
    advise_cmd.add_argument("--title")
    advise_cmd.add_argument("--tags", nargs="*")
    advise_cmd.add_argument(
        "--group", help="競合トピック (source_tag) を明示指定する"
    )
    advise_cmd.add_argument("--out")
    advise_cmd.set_defaults(func=cmd_advise)

    selftest = sub.add_parser("selftest", help="合成データで実装を検算")
    selftest.add_argument("--n", type=int, default=400)
    selftest.add_argument("--seed", type=int, default=7)
    selftest.add_argument("--out-corpus")
    selftest.set_defaults(func=cmd_selftest)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
