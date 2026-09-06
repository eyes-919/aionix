# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## リポジトリの現状

Aionix は「AI エージェントが継続的・再現可能に動作するための OS 的実行基盤」を
定義するプロジェクトだが、**現時点では設計文書が主体であり、ランタイム実装は存在しない**。

- `design/` — 設計文書 (このリポジトリの本体)
- `.github/` — Kernel Space の予約枠。全サブディレクトリが `.gitkeep` のみで**中身は空**
- `README.md` に出てくる `/root/` User Space も設計上の構造であり、まだ実装されていない
- `poc/note-algorithm/` — **唯一の実行可能コード** (Python)

「実装を追加してほしい」という依頼を受けたとき、既存の Agent Runtime や
Skill Dispatcher が動いている前提で書き始めないこと。まだ何も動いていない。

## 絶対規則: 絵文字禁止

`design/decisions/001_COMMUNICATION_RULES.md` により、**リポジトリ内のすべての
テキストで絵文字が禁止されている。例外はない**。

対象はドキュメント、コミットメッセージ、コード内コメント、PR / Issue コメント、
エージェント出力のすべて。

代替表現を使う。

- `NOTE:` `WARNING:` `IMPORTANT:`
- `[COMPLETED]` `[IN_PROGRESS]` `[BLOCKED]` `[APPROVED]` `[WAITING_APPROVAL]`
- `SUCCESS:` `FAILURE:` `ERROR:` `OK:` `NG:`

コミットメッセージの形式も同文書で規定されている。

```
<type>: <subject>

<body>
```

type は `feat:` `fix:` `refactor:` `docs:` `chore:` `test:`。

## 設計文書の追加規則

ファイル名は `NNN_YYYYMMDDHHMM_タイトル.md`。

**連番 `NNN` はサブディレクトリごとではなくリポジトリ全体で通し番号になっている。**
現在 001 から 008 まで使用済みで、`design/decisions/001`、`design/architecture/002`、
`design/philosophy/004` のように番号が分野をまたいで連続する。
新規文書は分野に関係なく次の番号を取る。

`design/decisions/` の内容 (本ルール自体を含む) を変更する場合は、
設計決定記録を更新したうえで GitHub Issue で discussion を経ることになっている。

## アーキテクチャの中核概念

設計文書全体を貫く分離は次の 2 つ。これを崩す提案はレビューで否定される。

**1. 三空間の分離**

| 空間 | 場所 | 役割 |
|---|---|---|
| Kernel Space | `.github/` | 統治する場所。ポリシー、承認ゲート、CI |
| Design Space | `design/` | 考える場所。設計判断の蓄積 |
| User Space | `/root/` | 作業させる場所。実際の動作 (未実装) |

**2. Agent と Skill の分離**

- **Agent は判断主体**。目的を理解し、実行計画を立て、Skill を選択し、成果物を評価する
- **Skill は機能部品**。自律的に意思決定しない再利用ライブラリ
- **Package は導入単位**。Agent + bundled skills + manifest

Skill に判断ロジックを持ち込む設計は原則違反。

詳細は `design/architecture/003_202604242245_Aionix_詳解ガイド.md` の
「6. Core Components 詳解」に、Task Manager / Agent Runtime / Context Manager /
Policy Engine / Permission Manager / Skill Dispatcher / Package Manager の
責務分担がある。

## poc/note-algorithm (noteseek)

note.com の配信アルゴリズムを観測し、施策がデータで裏づけられるかを判定する POC。
調査結果と設計判断は
`design/specifications/008_202609060300_note配信アルゴリズム調査とPOC設計.md`。

### コマンド

```bash
cd poc/note-algorithm
pip install -r requirements.txt        # 依存は requests のみ

# テスト全体
python -m unittest discover -s tests -t . -v

# 単一テスト / 単一クラス
python -m unittest tests.test_pipeline.TestAnalyze.test_pure_noise_is_not_reported_as_usable
python -m unittest tests.test_stats.TestStats

# 実装の検算 (ネットワーク不要。既知の係数を仕込んだ合成データで信号復元を確認)
python -m noteseek selftest

# 実データのフロー
python -m noteseek probe --tag AI                                    # API 生存確認
python -m noteseek collect --tags AI 生成AI --out data/corpus.jsonl  # 収集
python -m noteseek analyze --corpus data/corpus.jsonl                # 判定
python -m noteseek advise --corpus data/corpus.jsonl --draft a.md --tags 生成AI
```

`analyze` の終了コードは USABLE / PARTIALLY_USABLE で 0、それ以外で 2。

統計処理とベクトル化は標準ライブラリで自前実装している (numpy / scikit-learn を
入れていない)。日本語の形態素解析器も使わず、文字 N-gram で処理する。
依存を増やす前に、この方針が意図的なものである点を踏まえること。

### 壊してはいけない方法論

この POC の価値は測定設計にある。以下を崩すと結論が無意味になる。

- **母集団はハッシュタグ「新着」タブから取る**。人気タブの記事だけを集めて
  共通点を探す設計は生存者バイアスで破綻する
- **施策変数の効果は偏相関で読む**。フォロワー数・投稿数・経過日数は統制変数。
  統制しない単純相関はすべてフォロワー数の影を拾う
- **topic_fit は収集元ハッシュタグごとに測る**。複数タグ混合コーパスで
  単一重心を取ると「どのトピックにも中くらい似た記事」が高評価になり無意味になる
- **合格条件にベースライン超えを含める**。フォロワー数のみのモデルに勝てない
  結果は、記事側の工夫に意味があることを何も示していない
- **負の対照を維持する**。`tests/test_pipeline.py::test_pure_noise_is_not_reported_as_usable`
  が落ちる判定器は、実データで USABLE が出ても信用できない

`noteseek/api.py` が使うエンドポイントは note の非公式 API であり、予告なく変わる。
候補 URL リストから 200 を返したものを採用する構造になっているのは、
「API が変わったのか、分析結果が変わったのか」を切り分けるため。
収集前に必ず `probe` を通す。呼び出し間隔の下限 (既定 1.5 秒) を短くしない。

### スコープ外

スキやフォローの自動化は実装しない。規約違反であり note の方針とも逆行する。
ビュー数・読了率・外部流入は外部から観測できないため、推定値を実測のように
提示しない。

## 関連リポジトリ

| リポジトリ | 関係 |
|---|---|
| `eyes-919/note-like-bot` | **noteseek POC の移設先。こちらが本流**。note の自動エンゲージメント基盤 (Node.js + macOS アプリ)。企画・調査・指示書作成をこのセッション、実装を別セッションが担当する分担になっている |
| `eyes-919/note-mcp-automation` | note 記事を `READY_FOR_HUMAN_PUBLISH` まで準備する基盤 (Node.js)。**公開操作は意図的に実装していない**。変更を提案する際はこの境界を守ること |

`poc/note-algorithm` は note-like-bot の `poc/note-algorithm` に移設済み。
**note 向けの作業は note-like-bot 側が正本**であり、そちらの `CLAUDE.md` に
役割分担・受け渡し規約・調査時の安全条件 (実スキ禁止、`node -e` 禁止など) が
明文化されている。note 関連の依頼を受けたら、まずそちらを読むこと。

aionix 側のこのコピーは調査当時の記録として残している。
両方を編集しないこと。変更は note-like-bot 側に入れる。
