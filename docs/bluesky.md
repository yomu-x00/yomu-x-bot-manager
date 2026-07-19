# Bluesky 対応

## アカウント登録

1. Accounts → **Add Account**
2. プラットフォームで **Bluesky** を選択
3. **Identifier**: handle（例: `user.bsky.social`）またはメールアドレス
4. **App Password**: Bluesky の設定 →「アプリパスワード」で発行（`xxxx-xxxx-xxxx-xxxx` 形式）

メインパスワードではなくアプリパスワードを使うこと。

---

## ハッシュタグ・メンションについて

### X（Twitter）との違い

X では `#タグ` や `@ユーザー` をテキストに書くだけで自動的にリンクになる。  
**Bluesky では自動認識されない**。

Bluesky の AT Protocol では、投稿データに **facets**（ファセット）という追加情報を含める必要がある。  
facets は「テキストの何バイト目から何バイト目がハッシュタグ/メンションか」を明示するメタデータ。

```json
{
  "text": "#ウマ娘 おはよう",
  "facets": [
    {
      "$type": "app.bsky.richtext.facet",
      "index": { "byteStart": 0, "byteEnd": 12 },
      "features": [{ "$type": "app.bsky.richtext.facet#tag", "tag": "ウマ娘" }]
    }
  ]
}
```

facets を付けないと `#ウマ娘` はただの文字列になり、タグとして機能しない。

### 本システムでの対応

`backend/bluesky_executor.py` の `_build_facets()` が投稿テキストを解析して facets を自動生成する。

| 種別 | 検出パターン | 処理 |
|---|---|---|
| ハッシュタグ | `#タグ名`（日本語・ASCII 対応） | Tag facet を生成 |
| メンション | `@handle.bsky.social` 形式 | handle → DID を解決して Mention facet を生成 |

メンションは DID 解決に失敗した場合（存在しない handle など）はスキップされ、ただのテキストとして投稿される。

### バイトオフセットの注意

facets のインデックスは**文字数ではなくバイト数（UTF-8）**で指定する。  
日本語1文字は UTF-8 で 3 バイトになるため、文字数でカウントすると位置がズレる。  
`_build_facets()` は `text[:pos].encode("utf-8")` でバイト位置を計算している。

---

## 制限事項

| 機能 | X | Bluesky |
|---|---|---|
| スケジュール投稿 | ✅ | ✅ |
| 画像付き投稿 | ✅ | ✅ |
| 即時投稿 | ✅ | ✅ |
| 投稿末尾テキスト | ✅ | ✅ |
| Timeline 表示 | ✅ | ❌（未対応） |
| ツイート削除 | ✅ | ❌（未対応） |
| Cookie 失効検知 | ✅ | ✅（App Password の有効性を確認） |
