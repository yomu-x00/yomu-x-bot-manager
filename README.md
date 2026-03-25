# Twitter Bot Manager

twitter-cli ベースのルールベース自動化管理ダッシュボード。
複数アカウントを管理し、WebUI でルール設定・監視・スケジュール投稿を行う。

## 機能

- **アカウント管理**: 複数 Twitter アカウントの Cookie 登録・有効性チェック
- **ルールエンジン**: keyword / user / engagement / schedule トリガーによる自動アクション（like, RT, reply, follow, unfollow）
- **スケジュール投稿**: 日時指定 + 繰り返し（daily / weekly / custom）
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

### 3. Docker Compose で起動

```bash
docker compose up -d
```

- Backend API: `http://localhost:8000`
- Frontend UI: `http://localhost:5173`

### ローカル開発

```bash
# Backend
cd backend
uv sync
DATABASE_PATH=../data/twitter.db ENCRYPTION_KEY=<生成したキー> uv run uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

### テスト実行

```bash
cd backend
uv sync --all-extras
uv run pytest -v
```

## ディレクトリ構成

```
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── main.py            # FastAPI エントリポイント + API
│   ├── worker.py           # ルールエンジン
│   ├── scheduler.py        # スケジュール投稿管理
│   ├── executor.py         # twitter-cli コマンドラッパー
│   ├── db.py               # DB スキーマ・接続管理
│   ├── models.py           # Pydantic モデル
│   ├── crypto.py           # AES-GCM 暗号化
│   └── tests/              # pytest テスト
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── index.html
│   └── src/
│       ├── main.js         # SPA ルーター
│       ├── api.js          # API クライアント
│       └── pages/          # 各画面コンポーネント
└── data/
    └── twitter.db          # SQLite DB（自動生成）
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

## Cloudflare Tunnel 設定

既存の cloudflared にルート追加:

```yaml
ingress:
  - hostname: twitter.yomu.uk
    service: http://twitter-frontend:80
```

Cloudflare Access で OTP 認証を設定し、WebUI へのアクセスを制限。
