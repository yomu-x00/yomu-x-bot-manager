# デプロイガイド（Ubuntu Server + Cloudflare Tunnel）

個人運用向けの mini PC（Ubuntu Server）へのデプロイ手順。

---

## 前提

- mini PC に Ubuntu Server がインストール済み
- SSH でアクセスできる状態
- ローカル PC に Git・Docker が入っていること

---

## 1. mini PC 側の準備

### Docker のインストール

```bash
# mini PC に SSH でログイン
ssh user@minipc-ip

# Docker 公式スクリプトでインストール
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# 反映のため一度ログアウト → 再ログイン
```

### リポジトリのクローン

```bash
git clone https://github.com/yourname/yomu-x-bot-manager.git
cd yomu-x-bot-manager
```

---

## 2. 環境変数の設定

```bash
cp backend/.env.example backend/.env
```

`backend/.env` を編集：

```bash
# ENCRYPTION_KEY の生成（ローカル or mini PC どちらでもよい）
# ※ローカルで Cookie を登録済みなら、ローカル側と同じ値を使うこと
docker run --rm python:3.12-slim python -c \
  "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

```env
DATABASE_PATH=/app/data/twitter.db
ENCRYPTION_KEY=生成したキーをここに貼る
WEBHOOK_SECRET=任意の文字列（外部からのWebhookを使わないなら空でもよい）
```

> **重要**: ローカルで Cookie 登録済みの DB を移行する場合は、ローカルの `.env` と同じ `ENCRYPTION_KEY` を使う（違うと Cookie の復号に失敗する）。

---

## 3. Cookie の移行（ローカル → mini PC）

ローカルで一度 WebUI から Cookie を登録しておけば、DB ごと移行できるため mini PC 側での再入力が不要。

### ローカルで先に Cookie を登録する

```bash
# ローカルで起動
./dev.sh
# http://localhost:8000 にアクセスしてアカウント登録
```

### DB を mini PC にコピー

```bash
# ローカル PC から実行
scp data/twitter.db user@minipc-ip:/path/to/yomu-x-bot-manager/data/twitter.db
```

`data/` ディレクトリが存在しない場合は先に作成：

```bash
ssh user@minipc-ip "mkdir -p /path/to/yomu-x-bot-manager/data"
```

---

## 4. Docker Compose で起動

```bash
# mini PC 側で実行
cd yomu-x-bot-manager
docker compose up -d --build
```

起動確認：

```bash
docker compose ps
curl http://localhost:8000/api/health
# → {"status": "ok", ...}
```

ログ確認：

```bash
docker compose logs -f twitter-backend
```

---

## 5. Cloudflare Tunnel のセットアップ

Cloudflare Tunnel を使うと、ポート開放・固定IP不要で外部からアクセスできる。

### 前提

- Cloudflare にドメインが登録済みであること
- [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) が mini PC にインストール済みであること

### cloudflared のインストール

```bash
# Ubuntu (amd64)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
```

### ログイン・トンネルの作成

```bash
# Cloudflare にログイン（ブラウザが開く）
cloudflared tunnel login

# トンネルを作成
cloudflared tunnel create yomu-bot

# トンネル ID を確認（次の設定ファイルで使用）
cloudflared tunnel list
```

### 設定ファイルの作成

`~/.cloudflared/config.yml` を作成：

```yaml
tunnel: <TUNNEL_ID>  # cloudflared tunnel list で確認した ID
credentials-file: /home/user/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: bot.yourdomain.com
    service: http://localhost:8000
  - service: http_status:404
```

### DNS レコードの登録

```bash
cloudflared tunnel route dns yomu-bot bot.yourdomain.com
```

### systemd サービスとして登録（自動起動）

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared

# 動作確認
sudo systemctl status cloudflared
```

これで `https://bot.yourdomain.com` からアクセスできるようになる。

---

## 6. Cloudflare Access で認証を追加（推奨）

WebUI を外部公開するため、Cloudflare Zero Trust の Access で認証を設定する。

1. [Cloudflare Zero Trust ダッシュボード](https://one.dash.cloudflare.com/) にアクセス
2. **Access → Applications → Add an application**
3. **Self-hosted** を選択
4. Application domain: `bot.yourdomain.com`
5. Policy: **Allow** → **Emails** → 自分のメールアドレスを指定
6. 保存

以降、`bot.yourdomain.com` にアクセスするとメール認証が求められる。

---

## 7. アップデート手順

```bash
# mini PC 側で実行
cd yomu-x-bot-manager
git pull origin main
docker compose up -d --build
```

DB はボリュームマウント（`./data`）なのでデータは保持される。

---

## トラブルシューティング

| 症状 | 確認コマンド | 対処 |
|---|---|---|
| コンテナが起動しない | `docker compose logs twitter-backend` | `.env` の `ENCRYPTION_KEY` が設定されているか確認 |
| Cookie が復号できない | ログに `InvalidToken` | ローカルと mini PC の `ENCRYPTION_KEY` が一致しているか確認 |
| Tunnel がつながらない | `sudo systemctl status cloudflared` | `cloudflared tunnel list` でトンネルが active か確認 |
| `http://localhost:8000` には繋がるが外部から繋がらない | `cloudflared tunnel info yomu-bot` | DNS レコードが反映されているか確認（最大5分程度） |
