# poc/

## note-algorithm (noteseek) は移設済み

note.com の配信アルゴリズム調査 POC は
**[eyes-919/note-like-bot](https://github.com/eyes-919/note-like-bot) の
`poc/note-algorithm/` が正本**である。このリポジトリからは削除した。

### 削除した理由

aionix 側にコピーを残していたが、note-like-bot 側で開発が進み、
次のモジュールが aionix 側に存在しない状態になった。

- `campaign.py` — 施策の効果測定 (ランダム化ホールドアウト、層別、標本サイズ設計)
- `report.py` — アウトバウンド / インバウンドの効率比較
- `store.py` — SQLite 永続化
- `timing.py` — 投稿時刻・曜日の実測

古いコピーが「動く POC」に見えてしまい、拾った人が存在しない機能を探すことになる。
二重管理をやめる。

### 調査記録は design/ に残す

[design/specifications/008_202609060300_note配信アルゴリズム調査とPOC設計.md](../design/specifications/008_202609060300_note配信アルゴリズム調査とPOC設計.md)
に調査当時の一次情報と設計判断がある。こちらは記録として維持する。
