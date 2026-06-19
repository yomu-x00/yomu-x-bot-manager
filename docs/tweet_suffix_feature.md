# 機能要件: アカウントごとのツイート末尾テキスト（tweet_suffix）

## 概要

アカウントに `tweet_suffix` フィールドを追加し、そのアカウントから投稿される
すべてのツイートの末尾に自動でテキストを付与する機能を実装してください。

---

## DB変更

`accounts` テーブルに以下のカラムを追加:

- `tweet_suffix` TEXT, nullable, default null

---

## API変更

**POST /api/accounts** および **PUT /api/accounts/{id}**
リクエスト・レスポンスに `tweet_suffix` フィールドを追加。

```json
{
  "tweet_suffix": "\n#世界の祝日"
}
```

**GET /api/accounts** および **GET /api/accounts/{id}**
レスポンスに `tweet_suffix` を含める。

---

## ツイート投稿ロジック

以下のすべての投稿経路で `tweet_suffix` を自動付与すること:

1. スケジュール投稿（`/api/schedule` からの自動実行）
2. 直接投稿（`POST /api/accounts/{id}/tweet`）
3. ルールのアクション（`action_type: "tweet"`）
4. Webhook（`POST /api/webhook/tweet`）

付与ロジック:

```python
if account.tweet_suffix:
    text = text + account.tweet_suffix
```

---

## バリデーション

`tweet_suffix` を含めたツイート全体が 280文字を超える場合はエラーにせず、
本文を末尾から切り詰めて suffix を必ず付与する（または警告ログを出す）。
→ どちらの挙動が望ましいかは要確認。

---

## WebUI

アカウント設定画面に `ツイート末尾テキスト` 入力欄を追加。

- placeholder 例: `\n#世界の祝日`
