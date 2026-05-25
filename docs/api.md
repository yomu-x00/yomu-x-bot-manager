# API リファレンス

Base URL: `http://localhost:8000`

すべてのエンドポイントは `/api` プレフィックスを持ちます。  
Content-Type は `application/json`。

---

## 目次

- [クイックスタート — キーワード検索とトリガーを試す](#クイックスタート--キーワード検索とトリガーを試す)
- [System](#system)
- [Accounts](#accounts)
- [Rules](#rules)
- [Schedule](#schedule)
- [Monitors](#monitors)
- [Logs & Stats](#logs--stats)
- [Search](#search)
- [Uploads](#uploads)
- [Webhook](#webhook)

---

## クイックスタート — キーワード検索とトリガーを試す

サーバーを起動したら、以下の手順で実際に動作確認できます。

### 事前準備: auth_token と ct0 の取得

Twitter にログイン済みのブラウザで **開発者ツール → Application → Cookies → twitter.com** を開き、
`auth_token` と `ct0` の値をコピーします。

---

### Step 1: アカウントを登録する

```powershell
# PowerShell
$body = @{
    name          = "テストアカウント"
    username      = "your_twitter_username"
    auth_token    = "YOUR_AUTH_TOKEN"
    ct0           = "YOUR_CT0"
    is_active     = $true
    interval_minutes = 5
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/accounts" `
    -Method POST -ContentType "application/json" -Body $body
```

```bash
# curl
curl -s -X POST http://localhost:8000/api/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "テストアカウント",
    "username": "your_twitter_username",
    "auth_token": "YOUR_AUTH_TOKEN",
    "ct0": "YOUR_CT0"
  }' | jq .
```

レスポンス例（`id` を以降の手順で使います）:
```json
{ "id": 1, "name": "テストアカウント", "username": "your_twitter_username", "is_active": true }
```

---

### Step 2: 認証情報を確認する

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/accounts/1/verify"
```

```bash
curl -s -X POST http://localhost:8000/api/accounts/1/verify | jq .
```

```json
{ "valid": true, "output": "{\"username\": \"...\"}", "error": "" }
```

---

### Step 3: キーワード検索を実行する

`account_id` と検索クエリ `q` を指定します。

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/search?account_id=1&q=AI+LLM&count=5" | ConvertTo-Json -Depth 5
```

```bash
curl -s "http://localhost:8000/api/search?account_id=1&q=AI+LLM&count=5" | jq '.tweets[] | {id, text, username}'
```

レスポンス例:
```json
{
  "query": "AI LLM",
  "count": 5,
  "tweets": [
    { "id": "1234567890", "text": "...", "username": "someone", "likes": 10 }
  ]
}
```

---

### Step 4: ルール（キーワード検知 → アクション）を作成する

#### 例A: キーワードを検知したら通知（Discord）

```bash
curl -s -X POST http://localhost:8000/api/rules \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": 1,
    "name": "AI キーワード → Discord 通知",
    "trigger_type": "keyword",
    "trigger_config": { "keywords": ["AI", "LLM"], "match": "any" },
    "action_type": "notify",
    "action_config": {
      "type": "discord",
      "url": "https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN",
      "message_template": "検知: {tweet_text}\n{tweet_url}"
    },
    "cooldown_minutes": 60,
    "daily_limit": 20
  }' | jq .
```

#### 例B: キーワードを検知したらいいね

```bash
curl -s -X POST http://localhost:8000/api/rules \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": 1,
    "name": "AI キーワード → いいね",
    "trigger_type": "keyword",
    "trigger_config": { "keywords": ["Claude", "Anthropic"], "match": "any" },
    "action_type": "like",
    "action_config": {},
    "cooldown_minutes": 30,
    "daily_limit": 50
  }' | jq .
```

#### 例C: キーワードを検知したら新規ツイートで返答

```bash
curl -s -X POST http://localhost:8000/api/rules \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": 1,
    "name": "キーワード検知 → ツイート",
    "trigger_type": "keyword",
    "trigger_config": { "keywords": ["test_keyword_xyz"] },
    "action_type": "tweet",
    "action_config": {
      "text": "「{tweet_text}」を検知しました → {tweet_url}"
    }
  }' | jq .
```

---

### Step 5: ルールを手動トリガーする

```powershell
# 特定のルールだけ実行（rule_id=1）
Invoke-RestMethod -Uri "http://localhost:8000/api/rules/1/run" -Method POST

# アクティブな全ルールを一括実行
Invoke-RestMethod -Uri "http://localhost:8000/api/rules/run-all" -Method POST
```

```bash
# 特定のルールだけ実行
curl -s -X POST http://localhost:8000/api/rules/1/run | jq .
# → {"executed": 3}

# 全ルール一括実行
curl -s -X POST http://localhost:8000/api/rules/run-all | jq .
# → {"executed_total": 5, "per_rule": {"1": 3, "2": 2}}
```

---

### Step 6: 実行ログを確認する

```bash
# 最新20件
curl -s "http://localhost:8000/api/logs?limit=20" | jq '.[] | {rule_id, action, status, reason, executed_at}'

# 失敗だけ
curl -s "http://localhost:8000/api/logs?status=failed" | jq .

# 今日の統計
curl -s "http://localhost:8000/api/stats" | jq .
```

---

### Step 7: 外部サービス（Docker内自作サービス等）からツイートを呼ぶ

```bash
# WEBHOOK_SECRET が未設定の場合（Docker内部専用）
curl -s -X POST http://localhost:8000/api/webhook/tweet \
  -H "Content-Type: application/json" \
  -d '{"account_id": 1, "text": "外部サービスからのツイート"}' | jq .

# WEBHOOK_SECRET が設定されている場合
curl -s -X POST http://localhost:8000/api/webhook/tweet \
  -H "Content-Type: application/json" \
  -d '{"account_id": 1, "text": "テスト投稿", "token": "your_secret"}' | jq .
```

Python（Docker内の自作サービスから呼ぶ場合）:
```python
import httpx

async def post_tweet_via_webhook(text: str, account_id: int = 1):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://twitter-backend:8000/api/webhook/tweet",
            json={"account_id": account_id, "text": text, "token": "your_secret"},
        )
        resp.raise_for_status()
        return resp.json()
```

---

### よくあるエラー

| エラー | 原因 | 対処 |
|---|---|---|
| `{"detail": "twitter-cli not found"}` | Dockerイメージのビルドが必要 | `docker compose up --build` で再ビルド |
| `{"valid": false}` | auth_token / ct0 が期限切れ | ブラウザから最新の Cookie を再取得 |
| `{"executed": 0}` | クールダウン中 or 検索結果0件 | `cooldown_minutes` を短くするか別キーワードで試す |
| `401 Invalid token` | WEBHOOK_SECRET が一致しない | `.env` の値と `token` フィールドを確認 |

---

## System

### GET /api/health
サーバーとデータベースの死活確認。Docker ヘルスチェックや外部監視ツールから利用する。

**Response 200 (正常)**
```json
{ "status": "ok", "version": "0.1.0", "db": "ok" }
```

**Response 200 (DB 異常)**
```json
{ "status": "degraded", "version": "0.1.0", "db": "error" }
```

---

## Accounts

### GET /api/accounts
全アカウント一覧を返す。

**Response 200**
```json
[
  {
    "id": 1,
    "name": "メインアカウント",
    "username": "my_bot",
    "is_active": true,
    "interval_minutes": 5,
    "created_at": "2024-01-01T00:00:00"
  }
]
```

---

### POST /api/accounts
アカウントを作成する。`auth_token` / `ct0` はサーバー側で暗号化して保存される。

**Request Body**
```json
{
  "name": "メインアカウント",
  "username": "my_bot",
  "auth_token": "xxxxxx",
  "ct0": "yyyyyy",
  "is_active": true,
  "interval_minutes": 5
}
```

**Response 201** — 作成されたアカウントオブジェクト

---

### GET /api/accounts/{id}
指定 ID のアカウントを返す。

**Response 200** — アカウントオブジェクト  
**Response 404** — Account not found

---

### PUT /api/accounts/{id}
アカウントを部分更新する（未指定フィールドは変更なし）。

**Request Body** — すべてのフィールドが省略可能
```json
{
  "name": "新しい名前",
  "is_active": false,
  "interval_minutes": 10,
  "auth_token": "new_token",
  "ct0": "new_ct0",
  "username": "new_username"
}
```

**Response 200** — 更新後のアカウントオブジェクト  
**Response 404** — Account not found

---

### DELETE /api/accounts/{id}
アカウントを削除する。

**Response 204** — No Content  
**Response 404** — Account not found

---

### POST /api/accounts/{id}/tweet
指定アカウントで即時ツイートを投稿する（ルール・スケジュールを経由しない直接投稿）。

**Request Body**
```json
{
  "text": "今すぐ投稿するツイート",
  "images": ["/app/data/uploads/abc123.png"]
}
```

**Response 200**
```json
{ "status": "ok", "tweet": { "id": "...", "text": "..." } }
```

**Response 404** — Account not found  
**Response 500** — twitter-cli からのエラー

---

### GET /api/accounts/{id}/timeline
指定アカウントの最近のツイート一覧を返す。

**Query Parameters**
- `count` (optional, default: 20, max: 100) — 取得件数

**Response 200**
```json
{
  "account_id": 1,
  "username": "my_bot",
  "tweets": [
    { "id": "...", "text": "...", "created_at": "...", "likes": 5, "retweets": 2 }
  ]
}
```

---

### POST /api/accounts/{id}/verify
Twitter 認証情報の有効性を確認する。

**Response 200**
```json
{
  "valid": true,
  "output": "{ \"username\": \"my_bot\", ... }",
  "error": ""
}
```

---

## Rules

ルール = トリガー（検知条件）＋アクション（実行内容）の組み合わせ。

### トリガータイプ一覧

| trigger_type | 説明 | trigger_config フィールド |
|---|---|---|
| `keyword` | キーワード/ハッシュタグ検索 | `keywords: string[]`, `hashtags: string[]`, `match: "any"\|"all"` |
| `user` | 特定ユーザーの投稿監視 | `usernames: string[]`, `include_retweets: bool` |
| `engagement` | エンゲージメント閾値 | `search_query: string`, `min_likes: int`, `min_retweets: int`, `min_replies: int` |
| `schedule` | 時間帯・曜日指定 | `hours: int[]`, `days_of_week: int[]` (0=月, 6=日), `search_query: string` |

### アクションタイプ一覧

| action_type | 説明 | action_config フィールド |
|---|---|---|
| `like` | ツイートにいいね | なし |
| `rt` | リツイート | なし |
| `reply` | リプライ | `reply_text: string` |
| `follow` | ツイート投稿者をフォロー | なし |
| `unfollow` | ツイート投稿者をアンフォロー | なし |
| `tweet` | 新規ツイートを投稿 | `text: string`（`{tweet_text}` `{tweet_url}` `{username}` テンプレ利用可） |
| `notify` | 外部 Webhook に通知 | `url: string`, `type: "discord"\|"webhook"`, `message_template: string` |

---

### GET /api/rules
ルール一覧を返す。`account_id` クエリパラメータでフィルタ可能。

**Query Parameters**
- `account_id` (optional) — アカウントID でフィルタ

**Response 200**
```json
[
  {
    "id": 1,
    "account_id": 1,
    "name": "AI キーワード監視",
    "is_active": true,
    "trigger_type": "keyword",
    "trigger_config": { "keywords": ["AI", "LLM"], "match": "any" },
    "action_type": "notify",
    "action_config": {
      "type": "discord",
      "url": "https://discord.com/api/webhooks/...",
      "message_template": "検知: {tweet_text}\n{tweet_url}"
    },
    "cooldown_minutes": 60,
    "daily_limit": 50,
    "created_at": "2024-01-01T00:00:00"
  }
]
```

---

### POST /api/rules
ルールを作成する。

**Request Body**
```json
{
  "account_id": 1,
  "name": "AI キーワード監視",
  "is_active": true,
  "trigger_type": "keyword",
  "trigger_config": { "keywords": ["AI", "LLM"], "match": "any" },
  "action_type": "notify",
  "action_config": {
    "type": "discord",
    "url": "https://discord.com/api/webhooks/...",
    "message_template": "検知: {tweet_text}\n{tweet_url}"
  },
  "cooldown_minutes": 60,
  "daily_limit": 50
}
```

**Response 201** — 作成されたルールオブジェクト  
**Response 400** — Account not found

---

### GET /api/rules/{id}
指定 ID のルールを返す。

**Response 200** — ルールオブジェクト  
**Response 404** — Rule not found

---

### PUT /api/rules/{id}
ルールを部分更新する。

**Request Body** — すべてのフィールドが省略可能
```json
{
  "name": "新しい名前",
  "is_active": false,
  "trigger_type": "keyword",
  "trigger_config": { "keywords": ["新キーワード"] },
  "action_type": "like",
  "action_config": {},
  "cooldown_minutes": 30,
  "daily_limit": 20
}
```

**Response 200** — 更新後のルールオブジェクト  
**Response 404** — Rule not found

---

### DELETE /api/rules/{id}
ルールを削除する。

**Response 204** — No Content  
**Response 404** — Rule not found

---

### POST /api/rules/{id}/toggle
ルールの有効/無効を切り替える。

**Response 200** — 更新後のルールオブジェクト  
**Response 404** — Rule not found

---

### POST /api/rules/{id}/run
ルールを即時実行する（手動トリガー）。

**Response 200**
```json
{ "executed": 3 }
```

**Response 404** — Rule not found

---

### POST /api/rules/run-all
アクティブな全ルールを即時実行する。CI テストやデバッグ、強制リフレッシュ時に使用する。

**Response 200**
```json
{
  "executed_total": 12,
  "per_rule": { "1": 5, "2": 7, "3": 0 }
}
```

---

## Schedule

### GET /api/schedule
スケジュール投稿一覧を返す。

**Query Parameters**
- `status` (optional) — `pending` | `posted` | `failed` でフィルタ

**Response 200**
```json
[
  {
    "id": 1,
    "account_id": 1,
    "content": "定期ツイートです",
    "scheduled_at": "2024-06-01T12:00:00",
    "repeat_type": "daily",
    "repeat_config": { "hour": 12 },
    "image_paths": [],
    "status": "pending",
    "posted_at": null
  }
]
```

**repeat_type の値**
- `none` — 繰り返しなし
- `daily` — 毎日（`repeat_config: { "hour": 12 }`）
- `weekly` — 毎週（`repeat_config: { "day": 0, "hour": 9 }`、day は 0=月）

---

### POST /api/schedule
スケジュール投稿を作成する。

**Request Body**
```json
{
  "account_id": 1,
  "content": "定期ツイートです",
  "scheduled_at": "2024-06-01T12:00:00",
  "repeat_type": "none",
  "repeat_config": {},
  "image_paths": []
}
```

**Response 201** — 作成された投稿オブジェクト  
**Response 400** — Account not found

---

### GET /api/schedule/{id}
指定 ID のスケジュール投稿を返す。

**Response 200** — 投稿オブジェクト  
**Response 404** — Scheduled post not found

---

### PATCH /api/schedule/{id}
`pending` 状態の投稿の内容・日時を更新する。

**Request Body** — すべてのフィールドが省略可能
```json
{
  "content": "修正したツイート内容",
  "scheduled_at": "2024-06-01T15:00:00"
}
```

**Response 200** — 更新後の投稿オブジェクト  
**Response 404** — Scheduled post not found  
**Response 409** — `posted` / `failed` 状態の投稿は更新不可

---

### DELETE /api/schedule/{id}
スケジュール投稿を削除する。

**Response 204** — No Content  
**Response 404** — Scheduled post not found

---

## Monitors

キーワード監視設定（`notify` アクションとは独立した簡易モニタリング機能）。

### GET /api/monitors
モニター一覧を返す。

**Response 200**
```json
[
  {
    "id": 1,
    "account_id": 1,
    "keyword": "Claude",
    "notify_discord": true,
    "discord_webhook": "https://discord.com/api/webhooks/...",
    "last_checked_at": "2024-01-01T00:00:00",
    "is_active": true
  }
]
```

---

### POST /api/monitors
モニターを作成する。

**Request Body**
```json
{
  "account_id": 1,
  "keyword": "Claude",
  "notify_discord": true,
  "discord_webhook": "https://discord.com/api/webhooks/...",
  "is_active": true
}
```

**Response 201** — 作成されたモニターオブジェクト  
**Response 400** — Account not found

---

### GET /api/monitors/{id}
指定 ID のモニターを返す。

**Response 200** — モニターオブジェクト  
**Response 404** — Monitor not found

---

### PUT /api/monitors/{id}
モニターを部分更新する。

**Request Body** — すべてのフィールドが省略可能
```json
{
  "keyword": "新キーワード",
  "notify_discord": false,
  "discord_webhook": null,
  "is_active": true
}
```

**Response 200** — 更新後のモニターオブジェクト  
**Response 404** — Monitor not found

---

### DELETE /api/monitors/{id}
モニターを削除する。

**Response 204** — No Content  
**Response 404** — Monitor not found

---

### POST /api/monitors/{id}/toggle
モニターの有効/無効を切り替える。

**Response 200** — 更新後のモニターオブジェクト  
**Response 404** — Monitor not found

---

## Logs & Stats

### GET /api/logs
ルール実行ログを返す（降順、ページネーション対応）。

**Query Parameters**
- `account_id` (optional) — アカウントID でフィルタ
- `rule_id` (optional) — ルールID でフィルタ
- `action` (optional) — アクション種別でフィルタ（`like`, `rt`, `reply`, `follow`, `unfollow`, `tweet`, `notify`）
- `status` (optional) — `success` | `failed` | `skipped` でフィルタ
- `limit` (optional, default: 50, max: 200) — 取得件数
- `offset` (optional, default: 0) — オフセット

**Response 200**
```json
[
  {
    "id": 1,
    "rule_id": 1,
    "account_id": 1,
    "tweet_id": "1234567890",
    "action": "like",
    "status": "success",
    "reason": null,
    "executed_at": "2024-01-01T12:00:00"
  }
]
```

---

### GET /api/stats
本日の実行統計サマリーを返す。

**Response 200**
```json
{
  "total_accounts": 2,
  "active_accounts": 1,
  "total_rules": 5,
  "active_rules": 3,
  "pending_posts": 2,
  "today_executions": 42,
  "today_success": 38,
  "today_failed": 2,
  "today_skipped": 2
}
```

---

## Search

### GET /api/search
指定アカウントの認証情報を使って Twitter を検索する。ルールのトリガー設定テストやキーワード検証に使用する。

**Query Parameters**
- `account_id` (required) — 検索に使用するアカウント ID
- `q` (required) — 検索クエリ（キーワード、ハッシュタグ等）
- `count` (optional, default: 20, max: 100) — 取得件数

**Response 200**
```json
{
  "query": "AI LLM",
  "count": 20,
  "tweets": [
    { "id": "...", "text": "...", "username": "...", "likes": 10, "retweets": 3 }
  ]
}
```

**Response 404** — Account not found  
**Response 500** — twitter-cli からのエラー

---

## Uploads

画像ファイルのアップロードと管理。スケジュール投稿の `image_paths` に使用するパスをここで取得する。

対応拡張子: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`

### GET /api/uploads
アップロード済みファイルの一覧を返す（更新日時の降順）。

**Response 200**
```json
{
  "files": [
    {
      "filename": "abc123.png",
      "path": "/app/data/uploads/abc123.png",
      "size": 102400,
      "uploaded_at": "2024-01-01T12:00:00"
    }
  ],
  "total": 1
}
```

---

### POST /api/uploads
ファイルをアップロードする（multipart/form-data）。

**Request** — `Content-Type: multipart/form-data`
```
file=<binary>
```

**Response 201**
```json
{
  "filename": "abc123.png",
  "path": "/app/data/uploads/abc123.png",
  "size": 102400,
  "content_type": "image/png"
}
```

**Response 400** — 非対応の拡張子

---

### GET /api/uploads/{filename}
アップロード済みファイルのバイナリを返す。

**Response 200** — ファイルバイナリ  
**Response 404** — File not found

---

### DELETE /api/uploads/{filename}
アップロード済みファイルを削除する。

**Response 204** — No Content  
**Response 404** — File not found

---

## Webhook

外部サービス（Discord Bot、自作サービス等）からツイートを投稿するためのエンドポイント。

### POST /api/webhook/tweet
指定アカウントでツイートを投稿する。

**認証**  
`.env` に `WEBHOOK_SECRET` を設定した場合、リクエストの `token` フィールドと一致しなければ 401 を返す。  
`WEBHOOK_SECRET` が空の場合は認証なし（Docker 内部ネットワーク専用運用に適している）。

**Request Body**
```json
{
  "account_id": 1,
  "text": "ツイートする内容",
  "token": "your_webhook_secret",
  "images": []
}
```

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `account_id` | int | ✓ | ツイートするアカウントの ID |
| `text` | string | ✓ | ツイート本文 |
| `token` | string | — | `WEBHOOK_SECRET` と照合するトークン |
| `images` | string[] | — | アップロード済み画像パスのリスト |

**Response 200**
```json
{ "status": "ok", "output": "{ \"id\": \"...\", ... }" }
```

**Response 401** — Invalid token  
**Response 404** — Account not found or inactive  
**Response 500** — twitter-cli からのエラー

**Docker 内部からの呼び出し例**
```python
import httpx

await httpx.AsyncClient().post(
    "http://twitter-backend:8000/api/webhook/tweet",
    json={
        "account_id": 1,
        "text": "自動投稿テスト",
        "token": "your_webhook_secret"
    }
)
```

---

## エラーレスポンス共通形式

```json
{ "detail": "エラーメッセージ" }
```

| ステータス | 意味 |
|---|---|
| 400 | リクエスト不正（存在しないアカウントID 等） |
| 401 | 認証失敗（webhook token 不一致） |
| 404 | リソースが存在しない |
| 409 | 状態が操作を許可しない（posted 投稿の更新等） |
| 500 | サーバー内部エラー（twitter-cli 失敗等） |

---

## FastAPI 自動生成ドキュメント

サーバー起動中は以下の URL でインタラクティブな API ドキュメントを参照できます：

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
