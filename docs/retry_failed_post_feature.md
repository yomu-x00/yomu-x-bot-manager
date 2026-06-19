# 機能要件: failed 投稿の再投稿ボタン

## 概要

Schedule ページで `failed` 状態のスケジュール投稿に「再投稿」ボタンを追加し、
手動で再試行できるようにしてください。

---

## API変更

### POST /api/schedule/{id}/retry

`failed` 状態の投稿を即時再投稿する。

**成功時 Response 200**
```json
{ "status": "ok", "tweet": { "id": "...", "text": "..." } }
```

**エラー Response**
```json
{ "detail": "Scheduled post not found" }          // 404
{ "detail": "Post is not in failed status" }       // 409
```

投稿成功時はステータスを `posted` に更新し `posted_at` を記録する。
投稿失敗時はステータスを `failed` のままにして失敗理由をログに追記する。

---

## WebUI変更

Schedule ページの投稿一覧で、`failed` 状態の行に **「再投稿」ボタン** を追加。

- `pending` / `posted` の行には表示しない
- クリック後はローディング表示し、成功・失敗をトーストで通知
- 成功時は行のステータスを `posted` に更新して再投稿ボタンを非表示にする
