"""Bluesky posting via the official atproto SDK."""

import asyncio
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
                with open(path, "rb") as f:
                    upload = client.upload_blob(f)
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


async def post_bluesky(identifier: str, app_password: str, text: str, images: list[str] | None = None) -> BlueskyResult:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _login_and_post, identifier, app_password, text, images)


async def verify_bluesky(identifier: str, app_password: str) -> BlueskyResult:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _login_and_verify, identifier, app_password)
