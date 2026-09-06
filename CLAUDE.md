# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## リポジトリの現状

Aionix は「AI エージェントが継続的・再現可能に動作するための OS 的実行基盤」を
定義するプロジェクトだが、**現時点では設計文書が主体であり、ランタイム実装は存在しない**。

- `design/` — 設計文書 (このリポジトリの本体)
- `.github/` — Kernel Space の予約枠。全サブディレクトリが `.gitkeep` のみで**中身は空**
- `README.md` に出てくる `/root/` User Space も設計上の構造であり、まだ実装されていない
- `poc/` — 移設済み。**実行可能コードは持たない** ([poc/README.md](poc/README.md))

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

## 関連リポジトリ

| リポジトリ | 関係 |
|---|---|
| `eyes-919/note-like-bot` | **noteseek POC の移設先。こちらが本流**。note の自動エンゲージメント基盤 (Node.js + macOS アプリ)。企画・調査・指示書作成をこのセッション、実装を別セッションが担当する分担になっている |
| `eyes-919/note-mcp-automation` | note 記事を `READY_FOR_HUMAN_PUBLISH` まで準備する基盤 (Node.js)。**公開操作は意図的に実装していない**。変更を提案する際はこの境界を守ること |

**note 向けの作業は note-like-bot 側が正本。** noteseek POC はそちらへ移設し、
aionix からは削除した ([poc/README.md](poc/README.md))。
note 関連の依頼を受けたら、まず note-like-bot の `CLAUDE.md` と
`docs/constraints-for-planning.md` を読むこと。役割分担・受け渡し規約・
調査時の安全条件 (実スキ禁止、`node -e` 禁止) がそちらに明文化されている。

aionix に残しているのは調査記録 (`design/specifications/008_...md`) のみ。
コードは持たない。
