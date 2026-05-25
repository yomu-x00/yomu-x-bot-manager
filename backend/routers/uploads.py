"""Upload management API routes."""

import os
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _get_upload_dir() -> Path:
    upload_dir = Path(os.environ.get("DATABASE_PATH", "/app/data/twitter.db")).parent / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


@router.post("", status_code=201)
async def upload_file(file: UploadFile = File(...)):
    """画像ファイルをアップロードする。返却された path をスケジュール投稿の image_paths に使用する。"""
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext or '(none)'}")

    upload_dir = _get_upload_dir()
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = upload_dir / filename
    content = await file.read()
    dest.write_bytes(content)
    return {
        "filename": filename,
        "path": str(dest),
        "size": len(content),
        "content_type": file.content_type,
    }


@router.get("")
def list_uploads():
    """アップロード済みファイルの一覧を返す。"""
    upload_dir = _get_upload_dir()
    files = []
    for f in sorted(upload_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.is_file() and f.suffix.lower() in _ALLOWED_EXTENSIONS:
            stat = f.stat()
            files.append({
                "filename": f.name,
                "path": str(f),
                "size": stat.st_size,
                "uploaded_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    return {"files": files, "total": len(files)}


@router.get("/{filename}")
def serve_upload(filename: str):
    """アップロード済みファイルを返す。"""
    upload_dir = _get_upload_dir()
    path = upload_dir / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if path.parent != upload_dir:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return FileResponse(path)


@router.delete("/{filename}", status_code=204)
def delete_upload(filename: str):
    """アップロード済みファイルを削除する。"""
    upload_dir = _get_upload_dir()
    path = upload_dir / filename
    if path.parent != upload_dir:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    path.unlink()
