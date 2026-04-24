# Aionix コミュニケーション・ドキュメント作成ルール

作成日: 2026-04-25

## 1. 適用範囲

このルールは以下すべてに適用される。

- GitHub Issue / PR コメント
- ドキュメント（README.md、仕様書、ガイド等）
- コミットメッセージ
- コード内コメント
- Slack / Discord 等のチーム内通信
- AI エージェント出力

## 2. 絵文字の使用禁止

**ルール:** リポジトリ内のすべてのテキスト、ドキュメント、コミュニケーションで絵文字を使用してはいけない。

理由:
- 文字エンコーディングの問題を避ける
- 自動ツール・パーサーとの互換性を確保
- 国際的なチーム対応
- アクセシビリティを考慮
- 正式なドキュメントの品質維持

許可されない例:
- ❌ "✅ 完了"
- ❌ "📝 メモ"
- ❌ "🚀 リリース"
- ❌ "⚠️ 注意"

推奨される代替表現:
- "DONE: 完了"
- "NOTE: メモ"
- "RELEASE: リリース"
- "WARNING: 注意"
- "[SUCCESS]"
- "[PENDING]"
- "[ERROR]"
- "[INFO]"

## 3. テキストフォーマッティング

### 3.1 見出し

Markdown の `#` を使用する。

```markdown
# 第1レベル見出し
## 第2レベル見出し
### 第3レベル見出し
```

### 3.2 強調

- 太字: `**bold text**`
- イタリック: `*italic text*`
- コード: `` `code` ``

### 3.3 リスト

#### 順序付きリスト
```markdown
1. 最初の項目
2. 次の項目
3. 最後の項目
```

#### 順序なしリスト
```markdown
- 項目 A
- 項目 B
- 項目 C
```

### 3.4 マーカー・区切り記号

テーブルや視覚的な区切りが必要な場合：

- 見出し区切り: `---` または `---`（複数行）
- テーブル行分け: Markdown テーブル形式使用

**禁止:**
- 絵文字による装飾
- フローイング絵文字区切り
- 特殊記号の過度な連続

### 3.5 コードブロック

言語指定を含める。

```markdown
\`\`\`python
def hello():
    print("Hello, Aionix")
\`\`\`
```

## 4. タイトル・見出しのスタイル

### 4.1 大文字・小文字

日本語: 通常通り。英語は必要に応じてタイトルケースを使用。

```markdown
# Aionix Core Components Architecture
# エージェント実行フロー

OK: Introduction to Agent Design
NG: introduction to agent design (見出しの場合)
```

### 4.2 記号・接続詞

日本語: 適切な句点「。」「、」を使用。  
英語: 一般的な英文法に従う。

## 5. テーブル表現

Markdown テーブル形式を使用。

```markdown
| ヘッダー1 | ヘッダー2 | ヘッダー3 |
|---|---|---|
| 行1列1 | 行1列2 | 行1列3 |
| 行2列1 | 行2列2 | 行2列3 |
```

## 6. 特殊な情報の表示

### 6.1 警告・注意

記号ブロック形式:

```markdown
IMPORTANT: これは重要な情報です
```

```markdown
WARNING: これは注意事項です
```

```markdown
NOTE: これは参考情報です
```

### 6.2 状態表示

テキストマーカーを使用:

```markdown
[PENDING] タスク実施待機中
[IN_PROGRESS] タスク実施中
[COMPLETED] タスク完了
[BLOCKED] タスク阻害
[REJECTED] タスク却下
[APPROVED] 承認済み
[WAITING_APPROVAL] 承認待機中
```

### 6.3 成功・失敗

テキスト表現:

```markdown
SUCCESS: 処理成功
FAILURE: 処理失敗
ERROR: エラー発生
OK: 問題なし
NG: 問題あり
```

## 7. リンク記述

### 7.1 ドキュメントリンク

```markdown
[リンク表示テキスト](./path/to/document.md)
[全体設計](./design/architecture/002_202604242230_Aionix_全体設計.md)
```

### 7.2 外部リンク

```markdown
[テキスト](https://example.com/path)
```

## 8. コミットメッセージ

### 8.1 形式

```
<type>: <subject>

<body>

<footer>
```

### 8.2 Type

- `feat:` 新機能
- `fix:` バグ修正
- `refactor:` リファクタリング
- `docs:` ドキュメント更新
- `chore:` メンテナンス・ビルド
- `test:` テスト追加・更新

### 8.3 例

```
feat: Add Architecture Designer Agent specification

- Define role and responsibilities
- Specify decision scope
- Outline required skills and permissions
- Create Package manifest template

Related Issue: #123
```

絵文字は使用しない。

## 9. AI エージェント出力

Aionix エージェントが出力するドキュメント、ログ、メッセージでも同様に絵文字を禁止する。

- エージェント生成レポート: テキスト形式のみ
- ログメッセージ: [STATUS] 形式
- ドキュメント自動生成: 本ルール遵守

## 10. レビュー・品質確認

Code Reviewer Agent、Documentation Reviewer Agent は、本ルール違反（絵文字使用）を検出したら指摘する。

違反箇所は以下のように修正要求:

```
REQUEST FOR CHANGE:
- Line XX: 絵文字を含む
  Before: "✅ 完了した"
  After:  "[COMPLETED] 完了した"
```

## 11. 例外

なし。すべてのコンテキストで絵文字は禁止。

## 12. このルールの更新

本ルール自体の変更は、設計決定記録（design/decisions/）を更新し、GitHub Issue で discussion を経た後に実施する。

---

**ルール作成者:** eyes-919  
**有効開始:** 2026-04-25  
**バージョン:** 1.0
