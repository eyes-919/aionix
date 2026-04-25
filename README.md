# Aionix

AI エージェントが継続的に作業し、安全かつ再現可能に動作するための実行基盤。

## 概要

Aionix は、Claude Code / CLI などの AI 実行環境を、単なるプロンプト実行ツールではなく、**OS 的な構造で扱うための設計思想および実装基盤**です。

AI が便利になるほど、運用の問題が大きくなります。Aionix は、その問題に対して、**構造、役割、保存、権限、ログ、承認**という形で答えます。

### Aionix が解決する問題

AI を毎日の作業で継続利用すると起きる問題:

- 前に何を頼んだか分からなくなる
- どのファイルが正本か分からなくなる
- AI がどのルールで動いたのか追えない
- 成果物が散らかる
- どこまで AI に任せてよいか曖昧
- 公開してはいけない情報が混ざる危険

Aionix が提供する解決策:

- すべての作業が追跡可能
- 成果物の保存場所が明確
- ルールと判断ログが残る
- ファイル操作がゲートされる
- 役割と権限が分離
- 情報混在を防ぐ

## 主な特徴

### 1. Agent と Skill の分離

- **Agent** は判断主体 - 目的を理解し、実行計画を立てる
- **Skill** は機能部品 - 判断しない再利用ライブラリ
- **Package** は導入単位 - Agent + bundled skills + manifest

```
┌─────────────────────────────────────┐
│  User Request                       │
└────────────┬────────────────────────┘
             │
             v
┌─────────────────────────────────────┐
│  Agent (判断主体)                   │
│  - 目的を理解                        │
│  - 実行計画を立案                    │
│  - Skill を選択・呼び出し            │
└────────────┬────────────────────────┘
             │
      ┌──────┴──────┐
      │             │
      v             v
   Skill 1      Skill 2
   (機能部品)    (機能部品)
      │             │
      └──────┬──────┘
             │
             v
        Artifact
       (成果物)
```

### 2. Kernel Space と User Space の分離

```
Kernel Space (.github/)          Design Space (design/)          User Space (/root/)
├─ workflows/                    ├─ philosophy/                  ├─ agents/
├─ policies/                     ├─ architecture/                ├─ runtime/
├─ approval-gates/               ├─ specifications/              ├─ skills/
└─ packages/                     ├─ agents/                      ├─ var/
                                 └─ decisions/                   └─ ...
  
  "統治する場所"                 "考える場所"                   "作業させる場所"
  制御・ガバナンス                設計判断を蓄積                 実際の動作
```

### 3. OS 的な概念マッピング

| OS 概念 | Aionix | 説明 |
|---|---|---|
| Process | Agent 実行インスタンス | 一回のタスク実行 |
| Thread | Agent 内のサブタスク | 細粒度な作業単位 |
| System Call | Tool / Skill 呼び出し | 外部操作の一元化 |
| Library | Skill | 再利用可能な機能 |
| File system | Workspace / Repository | Git 管理される成果物 |
| Permission | Tool Access / File Access | 役割ベースのアクセス制御 |
| Signal | Human approval / interruption | 人間による介入・承認 |
| Kernel policy | Policy Engine | 作業上のルール適用 |

## 構成

```
aionix/
├── .github/                    (Kernel Space - 統治する場所)
│   ├── workflows/              # GitHub Actions
│   ├── policies/               # 実行ポリシー
│   ├── approval-gates/         # 承認ゲート定義
│   └── packages/               # Package 配布ルール
│
├── design/                     (Design Space - 考える場所)
│   ├── philosophy/             # 理念・背景
│   ├── architecture/            # システム設計
│   ├── specifications/          # 実装仕様
│   ├── agents/                 # エージェント設計
│   └── decisions/              # 設計決定記録
│
└── root/                       (User Space - 作業させる場所)
    ├── bin/                    # 実行可能ファイル
    ├── etc/aionix/             # 設定ファイル
    │   ├── agents/
    │   ├── skills/
    │   ├── packages/
    │   ├── policies/
    │   └── systemd/
    ├── lib/aionix/             # ライブラリ・実装
    │   ├── core/
    │   ├── agents/
    │   ├── skills/
    │   ├── tools/
    │   └── utils/
    └── var/
        ├── lib/aionix/         # ランタイム状態・キャッシュ
        │   ├── packages/
        │   ├── workspace/
        │   ├── cache/
        │   ├── state/
        │   └── memory/
        ├── log/aionix/         # ログ
        └── run/aionix/         # ソケット・lock
```

## ドキュメント

設計思想から実装仕様まで、順序立てて読めるドキュメント体系：

### 初めての方向け

1. [**Aionix が必要な理由**](design/philosophy/004_202604241030_Aionixが必要な理由.md)
   - 日常的な AI 利用で何が問題か
   - Aionix がそれにどう答えるか

### 設計概要

2. [**全体設計**](design/architecture/002_202604242230_Aionix_全体設計.md)
   - アーキテクチャの骨格
   - OS 概念とのマッピング

3. [**詳解ガイド**](design/architecture/003_202604242245_Aionix_詳解ガイド.md)
   - 実装・運用の考え方
   - Core components 詳解

### 実装・開発向け

4. [**Ubuntu 最小機能一覧と実装リスト**](design/specifications/005_202604241120_Ubuntu最小機能一覧と実装リスト.md)
   - 実装スコープ定義
   - P0 ~ P2 の優先度付きタスク

5. [**Aionix 開発に必要なエージェント一覧**](design/agents/006_202604250000_Aionix開発に必要なエージェント一覧.md)
   - 30 個のエージェント定義
   - ライフサイクルフェーズ別の役割分担
   - MVP 優先度付け

6. [**/root LHF 準拠ディレクトリ設計**](design/specifications/007_202604250100_root_LHF準拠ディレクトリ設計.md)
   - /root 以下の完全なディレクトリ階層設計
   - Linux 標準慣習への準拠
   - コンポーネント配置対応表
   - 権限・ユーザー管理ルール

## 開発のライフサイクル

```
Phase 1: 設計・計画
  └─ Architecture Designer, Planning Agent

Phase 2: 実装
  └─ Core Implementation, Agent/Skill Implementation

Phase 3: テスト・検証
  └─ Test Design, Test Executor, Performance Validator

Phase 4: ドキュメント
  └─ Technical Docs, User Docs, Release Notes

Phase 5: レビュー・品質確認
  └─ Code Review, Architecture Review, Quality Gate

Phase 6: リリース・デプロイ
  └─ Release Manager, Package Manager, Deployment
```

各フェーズで必要な判断主体（Agent）が定義されています。

## 技術スタック（計画）

- **Runtime target**: Ubuntu 26.04 LTS
- **Package manager**: APT / dpkg ベース
- **Service manager**: systemd
- **Language**: Python（初期段階）、Go（後期段階検討）
- **IaC**: Bicep / Terraform（展望）

## MVP（最小実行可能構成）

初期リリースで実装すべきエージェント：

- [ ] Architecture Designer Agent
- [ ] Planning Agent
- [ ] Core Implementation Agent
- [ ] Code Reviewer Agent
- [ ] File Governor Agent
- [ ] Context Manager Agent
- [ ] Test Design Agent
- [ ] Release Manager Agent

## 次のステップ

1. **Agent Definition Specification** を作成
2. **Skill Registry** を設計
3. **Package Manifest** テンプレートを定義
4. **Permission Policy** を詳細化
5. **Agent Interaction Protocol** を確立

## License

（未定 - 後で決定予定）

## 関連リソース

- [Canonical Ubuntu 公式ドキュメント](https://documentation.ubuntu.com/server/)
- [systemd 公式ドキュメント](https://systemd.io/)
- [Claude Code / CLI ドキュメント](https://anthropic.com)

---

**Aionix は、AI を継続的な作業環境の中で安全に運用するための基盤です。**

単発の質問や一時的なタスクだけなら、Aionix のような基盤は不要です。  
しかし、AI が毎日の作業に組み込まれると、便利さより先に**運用の問題**が大きくなります。

Aionix は、その運用の問題に対して、**OS 的な思考**で答えます。
