"""Bluesky posting via the official atproto SDK."""

import asyncio
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BlueskyResult:
    success: bool
    output: str
    error: str


def _login_and_post(identifier: str, app_password: str, text: str, images: list[str] | None) -> BlueskyResult:
    try:
        from atproto import Client, models

        client = Client()
        client.login(identifier, app_password)

        if images:
            blobs = []
            for path in images:
                with open(path, "rb") as f:
                    upload = client.upload_blob(f)
                blobs.append(models.AppBskyEmbedImages.Image(alt="", image=upload.blob))
            embed = models.AppBskyEmbedImages.Main(images=blobs)
            post = client.send_post(text=text, embed=embed)
        else:
            post = client.send_post(text=text)

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
