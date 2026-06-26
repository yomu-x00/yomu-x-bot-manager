# サーバーダウン対策ドキュメント

## ダウン履歴と原因分析

DB の `posted_at` から推定したダウン履歴と真因：

| 期間 | 遅延 | 真因 |
|---|---|---|
| 6/13 | ~4h | コンテナ停止（手動 or 再起動）→ 起動時バッチ投稿 |
| 6/16 21:00 の1件のみ | 67h | コンテナが短時間停止した際に pending のまま残留。同期間の他の投稿は正常 |
| 6/26 08:00 | 8.6h | twitter-cli の `ClientTransaction` 一時エラー → failed → 手動 retry |
| 6/26 19:00 | 1h | 同上 |
| 6/23 19:00 | failed のまま | 同上、retry されず |

**コンテナはクラッシュしていない**（`RestartCount = 0`）。  
ダウンの大半は `docker compose down` による手動停止か twitter-cli の一時エラーが原因。

---

## 実施済み対策

### 1. `restart: always` に変更（docker-compose.yml）

```yaml
restart: always  # unless-stopped から変更
```

`unless-stopped` は `docker compose down` や `docker stop` で止めると再起動しない。  
`always` にすることで手動停止後も Docker daemon 再起動後も自動復帰する。

### 2. Docker live-restore 有効化（/etc/docker/daemon.json）

```json
{ "live-restore": true }
```

Docker daemon 自体の再起動・アップデート中もコンテナが維持される。  
適用コマンド: `sudo systemctl reload docker`

### 3. systemd サービスで OS 起動時自動起動（/etc/systemd/system/twitter-bot.service）

```ini
[Unit]
Description=Twitter Bot Manager (docker compose)
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/viber/work/yomu-x-bot-manager
ExecStart=/usr/bin/docker compose up -d --remove-orphans
ExecStop=/usr/bin/docker compose stop
User=viber

[Install]
WantedBy=multi-user.target
```

OS 再起動後に `docker compose up -d` が自動実行される。  
有効化: `sudo systemctl enable --now twitter-bot.service`

### 4. twitter-cli リトライ（backend/scheduler.py）

環境変数で制御：

| 変数 | デフォルト | 意味 |
|---|---|---|
| `POST_MAX_RETRIES` | 3 | 投稿失敗時の最大リトライ回数 |
| `POST_RETRY_DELAY` | 10 | リトライ間隔（秒） |

`ClientTransaction` の初期化失敗など一時的なエラーに対して、即 `failed` にせず最大3回リトライする。

### 5. 古い pending のスキップ（backend/scheduler.py）

環境変数 `STALE_POST_MINUTES`（デフォルト: 60）分以上前の pending 投稿は  
起動時に `failed` 扱いでスキップし、バッチ投稿を防ぐ。

```
STALE_POST_MINUTES=60  # .env または docker-compose.yml で変更可
```

---

## 今後実装予定の対策

### A. Docker healthcheck の追加

`/api/health` エンドポイントが既に存在するため、これを使って  
「プロセスは起動しているが仕事をしていない」状態を検知できる。

```yaml
# docker-compose.yml の twitter-backend に追加
healthcheck:
  test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')\""]
  interval: 5m
  timeout: 10s
  retries: 3
  start_period: 30s
```

healthcheck が3回連続失敗するとコンテナが `unhealthy` になり、`restart: always` と組み合わせることで自動再起動される。

### B. healthcheck.py によるスケジューラー死活確認

HTTP ではなく「最後のスケジューラー実行が N 分以内か」を確認するスクリプト。  
APScheduler が内部でフリーズした場合も検知できる。

```python
# backend/healthcheck.py（未実装）
import sqlite3, sys
from datetime import datetime, timedelta

conn = sqlite3.connect("/app/data/twitter.db")
row = conn.execute("SELECT MAX(posted_at) FROM scheduled_posts").fetchone()
last = row[0]
if last is None:
    sys.exit(0)  # 投稿なし = 正常
last_dt = datetime.fromisoformat(last)
if datetime.now() - last_dt > timedelta(hours=2):
    # 2時間以上スケジューラーが動いていない
    sys.exit(1)
sys.exit(0)
```

### C. 外形監視（UptimeRobot）

無料プランで `/api/health` エンドポイントを5分ごとに監視し、  
ダウン時にメール・Slack 通知を受け取る。

- URL: `https://x-bot-manager.yomu.uk/api/health`
- 期待レスポンス: `{"status": "ok", ...}`
- 通知先: メール or Discord Webhook

### D. メインループの例外保護

現在 uvicorn + FastAPI のプロセスは例外で落ちることはほぼないが、  
APScheduler のジョブ例外は `main.py` の `_scheduler_job` で既にキャッチ済み：

```python
async def _scheduler_job() -> None:
    try:
        ...
    except Exception:
        logger.exception("Scheduler job failed")  # 落とさずログだけ
```

追加で考慮する場合は、APScheduler の `misfire_grace_time` を設定して  
スケジューラーが遅延した場合の挙動を制御する：

```python
scheduler.add_job(
    _scheduler_job,
    "interval",
    minutes=1,
    id="scheduler",
    misfire_grace_time=30,  # 30秒以内の遅延は正常実行
    coalesce=True,          # 溜まったジョブは1回にまとめる
)
```

---

## 保護レイヤーまとめ

```
OS 起動
  └─ systemd: twitter-bot.service → docker compose up -d
       └─ Docker: restart: always → クラッシュ・停止時に自動再起動
            └─ Docker: live-restore → daemon 再起動中もコンテナ維持
                 └─ healthcheck (予定) → 内部フリーズを検知して再起動
                      └─ UptimeRobot (予定) → 外部から死活監視・アラート
```

## デプロイ時の注意

コンテナを止めずにコードを反映する場合は `docker compose down` は使わず：

```bash
# NG: docker compose down → コンテナ削除 → up -d で再作成（空白時間が発生）
# OK: ファイルをコピーして restart のみ
docker compose cp backend/. twitter-backend:/app/
docker compose restart twitter-backend
```
