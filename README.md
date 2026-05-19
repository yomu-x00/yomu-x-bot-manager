# Twitter Bot Manager

twitter-cli ベースのルールベース自動化管理ダッシュボード。
複数アカウントを管理し、WebUI でルール設定・監視・スケジュール投稿を行う。

## 現在の状態

| 項目 | 状態 |
|---|---|
| ローカル uv 起動 | 動作確認済み |
| twitter-cli 実連携 | 手動テスト待ち |
| Docker デプロイ | 未検証 |

## 機能

- **アカウント管理**: 複数 Twitter アカウントの Cookie 登録・有効性チェック・アカウントごとのWorker実行間隔設定
- **ルールエンジン**: keyword / user / engagement / schedule トリガーによる自動アクション（like, RT, reply, follow, unfollow）
- **スケジュール投稿**: 日時指定 + 繰り返し（daily / weekly / custom / **ランダム時間帯**）
- **キーワード監視**: 指定キーワードの検出 + Discord Webhook 通知
- **実行ログ**: フィルタ・ページネーション付きの実行履歴表示
- **セキュリティ**: Cookie の AES-GCM 暗号化保存、daily_limit / cooldown による BAN 対策

## 技術スタック

| レイヤー | 技術 |
|---|---|
| CLI ツール | twitter-cli（uv 管理） |
| バックエンド | Python 3.12 + FastAPI + APScheduler |
| DB | SQLite（WAL モード） |
| フロントエンド | Vite + Vanilla JS |
| コンテナ | Docker Compose |
| 公開 | Cloudflare Tunnel + Access |

## アーキテクチャ（SOLID 原則）

バックエンドは以下の5つの SOLID 原則に従って設計されています。

| 原則 | 適用箇所 |
|---|---|
| **S**ingle Responsibility | `routers/` で各ドメインのルートを分離、`repositories/` でDB アクセスを分離 |
| **O**pen/Closed | `triggers/` と `actions/` のストラテジーパターンにより新しいトリガー・アクションを追加しても既存コードを変更不要 |
| **L**iskov Substitution | `TriggerHandler` / `ActionHandler` の Protocol を実装するハンドラーは相互に置き換え可能 |
| **I**nterface Segregation | `TriggerHandler`（fetch_tweets + matches）と `ActionHandler`（execute）に責務を細分化 |
| **D**ependency Inversion | `dependencies.py` の FastAPI Depends 経由で DB 接続・暗号鍵を注入 |

## セットアップ

### 1. 暗号化キーの生成

```bash
cd backend
uv run python -c "from crypto import generate_key; print(generate_key())"
```

### 2. 環境変数の設定

```bash
cp .env.example .env
# ENCRYPTION_KEY に生成したキーを設定
```

### 3. 起動

```bash
./dev.sh
```

フロントエンドのビルドとバックエンドの起動をまとめて実行します。

または個別に：

```bash
# フロントエンドビルド（初回 / フロント変更時のみ）
cd frontend && npm install && npm run build

# バックエンド起動
cd backend && uv sync && uv run uvicorn main:app --reload --port 8000
```

- WebUI: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`

`ENCRYPTION_KEY` や `DATABASE_PATH` が未設定の場合は起動時に警告が表示されます。

> フロントエンドのビルド済みファイル（`frontend/dist/`）を FastAPI から直接配信するため、Node プロセスは不要です。フロントのコードを変更した場合のみ再ビルドしてください。

### テスト実行

```bash
cd backend
uv sync --all-extras
uv run pytest -v
```

### Docker Compose（本番・デプロイ用）

```bash
docker compose up -d
```

## ディレクトリ構成

```
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── main.py                # FastAPI アプリファクトリのみ（SRP）
│   ├── dependencies.py        # FastAPI DI プロバイダ（DIP）
│   ├── worker.py              # ルールエンジン（ハンドラー委譲版）
│   ├── scheduler.py           # スケジュール投稿管理（リポジトリ委譲版）
│   ├── executor.py            # twitter-cli コマンドラッパー
│   ├── db.py                  # DB スキーマ・接続管理
│   ├── models.py              # Pydantic モデル
│   ├── crypto.py              # AES-GCM 暗号化
│   ├── routers/               # ドメイン別 API ルーター（SRP）
│   │   ├── accounts.py        # アカウント管理
│   │   ├── rules.py           # ルール管理
│   │   ├── schedule.py        # スケジュール投稿
│   │   ├── monitors.py        # キーワード監視
│   │   └── logs.py            # ログ・統計
│   ├── repositories/          # DB アクセス層（SRP + DIP）
│   │   ├── account_repository.py
│   │   ├── rule_repository.py
│   │   ├── schedule_repository.py
│   │   ├── monitor_repository.py
│   │   └── log_repository.py
│   ├── triggers/              # トリガーハンドラー戦略（OCP + SRP）
│   │   └── __init__.py        # KeywordTrigger / UserTrigger / etc.
│   ├── actions/               # アクションハンドラー戦略（OCP + SRP）
│   │   └── __init__.py        # LikeAction / RetweetAction / etc.
│   └── tests/                 # pytest テスト
│       ├── test_api.py        # API エンドポイント統合テスト
│       ├── test_repositories.py # リポジトリ単体テスト
│       ├── test_handlers.py   # トリガー・アクションハンドラーテスト
│       ├── test_worker.py     # ルールエンジンテスト
│       ├── test_scheduler.py  # スケジューラーテスト
│       ├── test_crypto.py     # 暗号化テスト
│       ├── test_db.py         # DB テスト
│       ├── test_executor.py   # executor テスト
│       └── test_models.py     # モデルテスト
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── index.html
│   └── src/
│       ├── main.js            # SPA ルーター
│       ├── api.js             # API クライアント
│       └── pages/             # 各画面コンポーネント
└── data/
    └── twitter.db             # SQLite DB（自動生成）
```

## API エンドポイント

| メソッド | パス | 説明 |
|---|---|---|
| GET/POST | `/api/accounts` | アカウント一覧 / 追加 |
| PUT/DELETE | `/api/accounts/{id}` | アカウント更新 / 削除 |
| POST | `/api/accounts/{id}/verify` | Cookie 有効性確認 |
| GET/POST | `/api/rules` | ルール一覧 / 作成 |
| PUT/DELETE | `/api/rules/{id}` | ルール更新 / 削除 |
| POST | `/api/rules/{id}/toggle` | 有効/無効切り替え |
| POST | `/api/rules/{id}/run` | 手動実行 |
| GET/POST | `/api/schedule` | スケジュール一覧 / 追加 |
| DELETE | `/api/schedule/{id}` | 予約削除 |
| GET/POST | `/api/monitors` | 監視一覧 / 追加 |
| GET | `/api/logs` | 実行ログ（フィルタ・ページネーション対応） |
| GET | `/api/stats` | 統計サマリー |

## 新規トリガー・アクションの追加方法

SOLID の開放閉鎖原則（OCP）により、既存コードを変更せずに拡張できます。

### 新しいトリガーを追加する例

```python
# backend/triggers/__init__.py に追記するだけ

class MentionTriggerHandler:
    async def fetch_tweets(self, auth_token, ct0, config):
        # 実装
        ...

    def matches(self, tweet, config):
        # 実装
        ...

# レジストリへの登録
TRIGGER_HANDLERS["mention"] = MentionTriggerHandler()
```

### 新しいアクションを追加する例

```python
# backend/actions/__init__.py に追記するだけ

class BookmarkActionHandler:
    async def execute(self, auth_token, ct0, config, tweet):
        # 実装
        ...

ACTION_HANDLERS["bookmark"] = BookmarkActionHandler()
```

## Cloudflare Tunnel 設定

既存の cloudflared にルート追加:

```yaml
ingress:
  - hostname: twitter.yomu.uk
    service: http://localhost:8000
```

Cloudflare Access で OTP 認証を設定し、WebUI へのアクセスを制限。
