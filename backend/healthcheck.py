"""Docker HEALTHCHECK スクリプト。

終了コード:
  0 = healthy
  1 = unhealthy
"""

import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

HEARTBEAT_FILE = Path("/app/data/.scheduler_heartbeat")
HEARTBEAT_MAX_AGE_MINUTES = 5  # scheduler は1分ごとに動くので5分なら余裕あり
HEALTH_URL = "http://localhost:8000/api/health"


def check_http() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=5) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[healthcheck] HTTP check failed: {e}", file=sys.stderr)
        return False


def check_scheduler_heartbeat() -> bool:
    if not HEARTBEAT_FILE.exists():
        # 起動直後はファイルがない場合があるので警告のみ
        print("[healthcheck] Heartbeat file not found (may be starting up)", file=sys.stderr)
        return True
    try:
        last = datetime.fromisoformat(HEARTBEAT_FILE.read_text().strip())
        age = datetime.now() - last
        if age > timedelta(minutes=HEARTBEAT_MAX_AGE_MINUTES):
            print(
                f"[healthcheck] Scheduler heartbeat stale: last run {age.seconds // 60}m ago",
                file=sys.stderr,
            )
            return False
        return True
    except Exception as e:
        print(f"[healthcheck] Heartbeat check error: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    ok = check_http() and check_scheduler_heartbeat()
    sys.exit(0 if ok else 1)
