"""Bluesky posting via the official atproto SDK."""

import asyncio
import io
import json
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Bluesky のハッシュタグ：ASCII + 日本語など Unicode 文字に対応
_HASHTAG_RE = re.compile(r'#([^\s -⁯⸀-⹿!?,.:;\'\"()\[\]{}]+)')
_MENTION_RE = re.compile(r'@([\w.-]+\.\w+)')


@dataclass
class BlueskyResult:
    success: bool
    output: str
    error: str


def _build_facets(client, text: str) -> list:
    """テキストから #hashtag と @mention を検出して Bluesky facets を生成する。"""
    from atproto import models

    facets = []
    text_bytes = text.encode("utf-8")

    # ハッシュタグ
    for m in _HASHTAG_RE.finditer(text):
        tag = m.group(1)
        byte_start = len(text[:m.start()].encode("utf-8"))
        byte_end = len(text[:m.end()].encode("utf-8"))
        facets.append(models.AppBskyRichtextFacet.Main(
            features=[models.AppBskyRichtextFacet.Tag(tag=tag)],
            index=models.AppBskyRichtextFacet.ByteSlice(byteStart=byte_start, byteEnd=byte_end),
        ))

    # メンション（handle を DID に解決、失敗はスキップ）
    for m in _MENTION_RE.finditer(text):
        handle = m.group(1)
        try:
            resolved = client.resolve_handle(handle=handle)
            byte_start = len(text[:m.start()].encode("utf-8"))
            byte_end = len(text[:m.end()].encode("utf-8"))
            facets.append(models.AppBskyRichtextFacet.Main(
                features=[models.AppBskyRichtextFacet.Mention(did=resolved.did)],
                index=models.AppBskyRichtextFacet.ByteSlice(byteStart=byte_start, byteEnd=byte_end),
            ))
        except Exception:
            pass

    return facets or None


BLUESKY_MAX_BLOB = 2_000_000  # 2MB


def _compress_image(path: str) -> bytes:
    """画像を Bluesky の上限（2MB）以下に収まるよう圧縮して bytes で返す。"""
    from PIL import Image

    with open(path, "rb") as f:
        data = f.read()

    if len(data) <= BLUESKY_MAX_BLOB:
        return data

    img = Image.open(io.BytesIO(data)).convert("RGB")

    # JPEG 品質を下げながら圧縮
    for quality in (85, 75, 65, 55, 45):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        if buf.tell() <= BLUESKY_MAX_BLOB:
            logger.info("Compressed image %s to %d bytes (quality=%d)", path, buf.tell(), quality)
            return buf.getvalue()

    # それでも超える場合は縮小
    w, h = img.size
    for scale in (0.8, 0.65, 0.5):
        resized = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=65, optimize=True)
        if buf.tell() <= BLUESKY_MAX_BLOB:
            logger.info("Resized image %s to %.0f%% (%d bytes)", path, scale * 100, buf.tell())
            return buf.getvalue()

    # 最終手段
    buf = io.BytesIO()
    img.resize((int(w * 0.4), int(h * 0.4)), Image.LANCZOS).save(buf, format="JPEG", quality=55)
    return buf.getvalue()


def _login_and_post(identifier: str, app_password: str, text: str, images: list[str] | None) -> BlueskyResult:
    try:
        from atproto import Client, models

        client = Client()
        client.login(identifier, app_password)

        facets = _build_facets(client, text)

        embed = None
        if images:
            blobs = []
            for path in images:
                data = _compress_image(path)
                upload = client.upload_blob(data)
                blobs.append(models.AppBskyEmbedImages.Image(alt="", image=upload.blob))
            embed = models.AppBskyEmbedImages.Main(images=blobs)

        post = client.send_post(text=text, facets=facets, embed=embed)
        return BlueskyResult(success=True, output=str(post.uri), error="")
    except Exception as e:
        logger.error("Bluesky post failed: %s", e)
        return BlueskyResult(success=False, output="", error=str(e))


def _login_and_verify(identifier: str, app_password: str) -> BlueskyResult:
    try:
        from atproto import Client

        client = Client()
        profile = client.login(identifier, app_password)
        return BlueskyResult(success=True, output=profile.handle, error="")
    except Exception as e:
        logger.error("Bluesky verify failed: %s", e)
        return BlueskyResult(success=False, output="", error=str(e))


def _post_uri(did: str, rkey: str) -> str:
    return f"at://{did}/app.bsky.feed.post/{rkey}"


def _feed_item_to_dict(post) -> dict:
    """Bluesky の PostView を Timeline 画面が扱える dict に変換する。"""
    record = getattr(post, "record", None)
    author = getattr(post, "author", None)

    media = []
    embed = getattr(post, "embed", None)
    # 画像付き投稿は embed.images、引用+画像は embed.media.images に入る
    for holder in (embed, getattr(embed, "media", None)):
        for img in getattr(holder, "images", None) or []:
            url = getattr(img, "fullsize", None) or getattr(img, "thumb", None)
            if url:
                media.append({"type": "photo", "url": url})

    return {
        # rkey を id として扱う（AT URI はスラッシュを含み URL パスに載せられないため）
        "id": str(post.uri).rsplit("/", 1)[-1],
        "uri": str(post.uri),
        "text": getattr(record, "text", "") or "",
        "createdAtISO": getattr(record, "created_at", None) or getattr(post, "indexed_at", "") or "",
        "media": media,
        "author": {
            "name": getattr(author, "display_name", "") or "",
            "screenName": getattr(author, "handle", "") or "",
            "profileImageUrl": getattr(author, "avatar", "") or "",
        },
        "metrics": {
            "likes": getattr(post, "like_count", 0) or 0,
            "retweets": getattr(post, "repost_count", 0) or 0,
            "replies": getattr(post, "reply_count", 0) or 0,
        },
    }


def _login_and_get_posts(identifier: str, app_password: str, count: int) -> BlueskyResult:
    try:
        from atproto import Client

        client = Client()
        profile = client.login(identifier, app_password)
        feed = client.get_author_feed(actor=profile.did, limit=count)

        posts = []
        for item in feed.feed:
            # リポスト（reason 付き）と他人の投稿は削除対象にならないので除外する
            if getattr(item, "reason", None):
                continue
            if getattr(item.post.author, "did", None) != profile.did:
                continue
            posts.append(_feed_item_to_dict(item.post))

        return BlueskyResult(success=True, output=json.dumps(posts), error="")
    except Exception as e:
        logger.error("Bluesky get_author_feed failed: %s", e)
        return BlueskyResult(success=False, output="", error=str(e))


def _login_and_delete(identifier: str, app_password: str, rkey: str) -> BlueskyResult:
    try:
        from atproto import Client

        client = Client()
        profile = client.login(identifier, app_password)
        uri = rkey if rkey.startswith("at://") else _post_uri(profile.did, rkey)
        if not client.delete_post(uri):
            return BlueskyResult(success=False, output="", error=f"Failed to delete {uri}")
        return BlueskyResult(success=True, output=uri, error="")
    except Exception as e:
        logger.error("Bluesky delete failed: %s", e)
        return BlueskyResult(success=False, output="", error=str(e))


async def post_bluesky(identifier: str, app_password: str, text: str, images: list[str] | None = None) -> BlueskyResult:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _login_and_post, identifier, app_password, text, images)


async def verify_bluesky(identifier: str, app_password: str) -> BlueskyResult:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _login_and_verify, identifier, app_password)


async def get_bluesky_posts(identifier: str, app_password: str, count: int = 20) -> BlueskyResult:
    """自分の投稿一覧を JSON 文字列（Timeline 画面と同じ形式）で返す。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _login_and_get_posts, identifier, app_password, count)


async def delete_bluesky_post(identifier: str, app_password: str, rkey: str) -> BlueskyResult:
    """rkey（または AT URI）で指定した自分の投稿を削除する。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _login_and_delete, identifier, app_password, rkey)
