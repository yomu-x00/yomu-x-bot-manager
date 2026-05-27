# CSV インポート（スケジュール投稿一括登録）

WebUI の **Schedule ページ** から CSV ファイルをインポートして、スケジュール投稿を一括登録できます。

---

## 使い方

1. サイドバーでアカウントを選択
2. **Schedule** ページへ移動
3. **「CSV インポート」** ボタンをクリック
4. **「テンプレDL」** でサンプル CSV をダウンロード（任意）
5. CSV ファイルを選択 → プレビューで内容を確認
6. **「インポート」** ボタンで一括登録

---

## CSV フォーマット

```csv
account_id,content,scheduled_at,repeat_type
1,ツイート内容1,2026-06-01 09:00,none
1,ツイート内容2,2026-06-02 12:00,none
1,毎日投稿,2026-06-03 18:00,daily
```

### カラム一覧

| カラム | 必須 | 説明 | 例 |
|---|---|---|---|
| `account_id` | — | アカウントID（省略するとサイドバーで選択中のアカウントを使用） | `1` |
| `content` | ✓ | ツイート本文 | `おはようございます` |
| `scheduled_at` | ✓ | 投稿日時（`YYYY-MM-DD HH:MM` 形式） | `2026-06-01 09:00` |
| `repeat_type` | — | 繰り返しタイプ（省略時は `none`） | `none` / `daily` / `weekly` |

### repeat_type の値

| 値 | 説明 |
|---|---|
| `none` | 繰り返しなし（1回だけ投稿） |
| `daily` | 毎日同じ時刻に投稿 |
| `weekly` | 毎週同じ曜日・時刻に投稿 |

> ランダム時間帯（`random_window`）や画像付き投稿は CSV では指定できません。これらは「+ Schedule Post」ボタンから個別に登録してください。

---

## サンプル CSV

```csv
account_id,content,scheduled_at,repeat_type
1,おはようございます！今日も一日頑張りましょう,2026-06-01 09:00,daily
1,週次レポートをまとめました,2026-06-02 18:00,weekly
1,期間限定キャンペーン告知,2026-06-15 12:00,none
```

---

## エラーとプレビュー

インポートモーダルのプレビューテーブルで、各行の状態を確認できます。

| 表示 | 意味 |
|---|---|
| ✅ | 登録可能 |
| ⚠️ `content が空` | `content` カラムが空 |
| ⚠️ `scheduled_at が無効な日時` | 日時フォーマットが正しくない |
| ⚠️ `account_id=X が存在しない` | 指定したアカウントIDが登録されていない |

エラー行はスキップされ、✅ の行だけ登録されます。

---

## API での一括登録

WebUI を使わずに API から直接一括登録することもできます。

```bash
curl -s -X POST http://localhost:8000/api/schedule/bulk \
  -H "Content-Type: application/json" \
  -d '[
    {
      "account_id": 1,
      "content": "ツイート1",
      "scheduled_at": "2026-06-01T09:00:00",
      "repeat_type": "none",
      "repeat_config": {},
      "image_paths": []
    },
    {
      "account_id": 1,
      "content": "ツイート2",
      "scheduled_at": "2026-06-02T12:00:00",
      "repeat_type": "daily",
      "repeat_config": {},
      "image_paths": []
    }
  ]' | jq .
```

**レスポンス例:**
```json
{
  "created": 2,
  "errors": []
}
```

エラーがある場合:
```json
{
  "created": 1,
  "errors": [
    { "index": 1, "reason": "Account 99 not found" }
  ]
}
```
