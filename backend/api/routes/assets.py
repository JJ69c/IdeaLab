"""Asset upload route — handles image uploads for reference assets."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.config import settings
from backend.db.database import SyncSession
from backend.db.models import Asset

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assets", tags=["assets"])

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}

EXTENSION_MAP = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


@router.post("/upload")
async def upload_asset(file: UploadFile, asset_type: str = "prototype"):
    """Upload a reference asset image.

    Accepts JPEG, PNG, WebP, or GIF up to 5MB. Returns the asset ID
    to be included in the simulation creation request.
    """
    # Validate content type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. "
                   f"Accepted: JPEG, PNG, WebP, GIF.",
        )

    # Validate asset type
    valid_types = {"website", "app_ui", "product_photo", "packaging", "prototype", "marketing_visual"}
    if asset_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid asset_type: {asset_type}. Valid: {', '.join(sorted(valid_types))}",
        )

    # Read file with size limit
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    data = await file.read()
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({len(data) / 1024 / 1024:.1f}MB). Max: {settings.max_upload_size_mb}MB.",
        )

    # Ensure upload directory exists
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Save file with unique name
    asset_id = str(uuid.uuid4())
    ext = EXTENSION_MAP.get(file.content_type, ".bin")
    filename = f"{asset_id}{ext}"
    file_path = upload_dir / filename

    file_path.write_bytes(data)

    # Persist metadata to DB
    db: Session = SyncSession()
    try:
        record = Asset(
            id=asset_id,
            filename=filename,
            original_name=file.filename or "unknown",
            asset_type=asset_type,
            file_path=str(file_path),
        )
        db.add(record)
        db.commit()
    except Exception:
        logger.exception("Failed to persist asset record")
        # Clean up the file if DB write fails
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Failed to save asset")
    finally:
        db.close()

    logger.info("Uploaded asset %s (%s, %.1fKB)", asset_id, asset_type, len(data) / 1024)
    return {"id": asset_id, "filename": filename, "asset_type": asset_type}
