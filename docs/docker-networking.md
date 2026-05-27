# Docker ネットワーキング メモ

複数サービスを mini PC で運用する際の Docker ネットワーク構成まとめ。

---

## 基本：プロジェクトごとに docker-compose.yml を持つ

```
~/projects/
├── yomu-x-bot-manager/
│   └── docker-compose.yml
├── discord-bot/
│   └── docker-compose.yml
└── scraper/
    └── docker-compose.yml
```

デフォルトでは各 Compose プロジェクトのネットワークは分離されており、互いに通信できない。

---

## サービス間通信の選択肢

### ① 1つの docker-compose.yml にまとめる

同じリポジトリで一緒に開発・デプロイするサービスに向いている。

```yaml
services:
  twitter-backend: ...
  discord-bot:
    build: ./discord-bot
    environment:
      - TWITTER_API=http://twitter-backend:8000  # サービス名で解決
```

- サービスごとに個別起動・停止・再ビルドは可能
- リポジトリが別の場合は管理しにくい

```bash
docker compose up -d twitter-backend     # これだけ起動
docker compose up --build discord-bot    # これだけ再ビルド
docker compose stop discord-bot          # これだけ停止
```

---

### ② 外部ネットワークで別 Compose と繋ぐ（推奨）

「外部ネットワーク」の「外部」= インターネットではなく「この compose ファイルの外」という意味。
通信は Docker 内仮想ネットワークで完結し、ホスト側にポートを開ける必要はない。

```
┌─ mini PC ──────────────────────────────────────────┐
│                                                     │
│  ┌─ shared-net (Docker内仮想ネットワーク) ─────────┐ │
│  │                                                 │ │
│  │  twitter-backend:8000                           │ │
│  │  discord-bot                                    │ │
│  │  scraper                                        │ │
│  │                                                 │ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

**セットアップ手順:**

```bash
# ネットワークを先に作る（1回だけ）
docker network create shared-net
```

```yaml
# yomu-x-bot-manager/docker-compose.yml
networks:
  shared-net:
    external: true   # 既存の shared-net に参加

services:
  twitter-backend:
    networks: [shared-net]
```

```yaml
# discord-bot/docker-compose.yml
networks:
  shared-net:
    external: true

services:
  discord-bot:
    networks: [shared-net]
    environment:
      - TWITTER_API=http://twitter-backend:8000  # サービス名で名前解決
```

各プロジェクトを独立して `docker compose up/down` でき、通信は Docker 内で閉じている。

---

### ③ ホストポート経由（疎結合）

依存関係を持たせたくない場合。ただしポートをホストに公開する必要がある。

```
http://host.docker.internal:8000   # コンテナからホストを指す
http://minipc-ip:8000              # 外部サービスから
```

---

## 使い分けまとめ

| ケース | 方法 |
|---|---|
| 同じリポジトリで一緒に開発 | ① まとめる |
| 別リポジトリ・独立デプロイしたい | ② 外部ネットワーク |
| 完全に疎結合にしたい | ③ ポート直叩き |

個人運用の mini PC なら **② を基本にして、密に連携するものだけ ① にまとめる** のがバランスよい。

---

## このプロジェクトの API を他サービスから呼ぶ

`WEBHOOK_SECRET` を設定しておくことで token 認証が効く。

```python
# 他サービス（同一 shared-net 内）から呼ぶ例
import httpx

async def post_tweet(text: str, account_id: int = 1):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://twitter-backend:8000/api/webhook/tweet",
            json={
                "account_id": account_id,
                "text": text,
                "token": "your_webhook_secret",
            },
        )
        resp.raise_for_status()
        return resp.json()
```

主な連携エントリポイント:

| 用途 | エンドポイント |
|---|---|
| ツイート投稿 | `POST /api/webhook/tweet` |
| スケジュール一括登録 | `POST /api/schedule/bulk` |
| 検索 | `GET /api/search?account_id=1&q=...` |
| ログ・統計取得 | `GET /api/logs` / `GET /api/stats` |

詳細は `docs/api.md` 参照。
