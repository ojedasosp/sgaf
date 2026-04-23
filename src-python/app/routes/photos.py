"""Photo management routes for SGAF.

All endpoints require JWT authentication via @require_auth.
Photos are stored as files on disk; the DB stores the destination path.

Endpoints:
    GET  /api/v1/photos/?asset_id=<id>   — list photos for an asset
    POST /api/v1/photos/                  — register a new photo
    DELETE /api/v1/photos/<photo_id>      — delete a photo
    PATCH  /api/v1/photos/<photo_id>/primary — set photo as primary
"""

import os
import shutil
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import delete, func, insert, select, update

from app.config import Config
from app.database import get_db
from app.middleware import require_auth
from app.models.tables import asset_photos, fixed_assets
from app.utils.audit_logger import AuditLogger

photos_bp = Blueprint("photos", __name__, url_prefix="/api/v1/photos")

_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
_audit_logger = AuditLogger()


def _photos_dir(asset_id: int) -> str:
    """Return (and create) the directory for an asset's photos."""
    if Config.DB_PATH:
        base = os.path.dirname(Config.DB_PATH)
    else:
        base = os.path.expanduser("~")
    path = os.path.join(base, "photos", str(asset_id))
    os.makedirs(path, exist_ok=True)
    return path


def _row_to_dict(row) -> dict:
    return dict(row._mapping)


@photos_bp.get("/")
@require_auth
def list_photos():
    """GET /api/v1/photos/?asset_id=<id> — list photos for an asset."""
    asset_id_raw = request.args.get("asset_id")
    if not asset_id_raw:
        return jsonify({"error": "VALIDATION_ERROR", "message": "asset_id is required", "field": "asset_id"}), 400
    try:
        asset_id = int(asset_id_raw)
    except ValueError:
        return jsonify({"error": "VALIDATION_ERROR", "message": "asset_id must be an integer", "field": "asset_id"}), 400

    with get_db() as conn:
        asset_row = conn.execute(
            select(fixed_assets.c.asset_id).where(fixed_assets.c.asset_id == asset_id)
        ).fetchone()
        if asset_row is None:
            return jsonify({"error": "NOT_FOUND", "message": "Asset not found"}), 404

        rows = conn.execute(
            select(asset_photos)
            .where(asset_photos.c.asset_id == asset_id)
            .order_by(asset_photos.c.uploaded_at.desc())
        ).fetchall()

    return jsonify({"data": [_row_to_dict(r) for r in rows]}), 200


@photos_bp.post("/")
@require_auth
def upload_photo():
    """POST /api/v1/photos/ — register a new photo for an asset.

    Body: {asset_id: int, file_path: str}

    The backend copies the file from file_path to the managed photos directory
    and stores the destination path in the DB.
    """
    data = request.get_json(silent=True) or {}

    asset_id_raw = data.get("asset_id")
    file_path = data.get("file_path", "")

    if asset_id_raw is None:
        return jsonify({"error": "VALIDATION_ERROR", "message": "asset_id is required", "field": "asset_id"}), 400
    if not isinstance(asset_id_raw, int) or asset_id_raw <= 0:
        return jsonify({"error": "VALIDATION_ERROR", "message": "asset_id must be a positive integer", "field": "asset_id"}), 400
    if not file_path or not isinstance(file_path, str):
        return jsonify({"error": "VALIDATION_ERROR", "message": "file_path is required", "field": "file_path"}), 400
    if not os.path.isfile(file_path):
        return jsonify({"error": "VALIDATION_ERROR", "message": "file_path does not exist on disk", "field": "file_path"}), 400

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        return jsonify({
            "error": "VALIDATION_ERROR",
            "message": f"File type not allowed. Allowed: {', '.join(_ALLOWED_EXTENSIONS)}",
            "field": "file_path",
        }), 400

    # Compute destination path before opening DB connection
    dest_dir = _photos_dir(asset_id_raw)
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%dT%H%M%S")
    filename = os.path.basename(file_path)
    dest_path = os.path.join(dest_dir, f"{ts}_{filename}")

    # F1: Guard against path traversal in the destination filename
    real_dest = os.path.realpath(dest_path)
    real_dest_dir = os.path.realpath(dest_dir)
    if not real_dest.startswith(real_dest_dir + os.sep):
        return jsonify({"error": "VALIDATION_ERROR", "message": "Invalid file path", "field": "file_path"}), 400

    with get_db() as conn:
        asset_row = conn.execute(
            select(fixed_assets.c.asset_id).where(fixed_assets.c.asset_id == asset_id_raw)
        ).fetchone()
        if asset_row is None:
            return jsonify({"error": "NOT_FOUND", "message": "Asset not found"}), 404

        uploaded_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        # F3: Insert with is_primary=0 first, then promote after seeing count — avoids SELECT→INSERT race
        result = conn.execute(
            insert(asset_photos).values(
                asset_id=asset_id_raw,
                file_path=dest_path,
                is_primary=0,
                uploaded_at=uploaded_at,
            )
        )
        new_id = result.inserted_primary_key[0]

        # If this is the only photo for the asset, make it primary
        count = conn.execute(
            select(func.count()).select_from(asset_photos).where(asset_photos.c.asset_id == asset_id_raw)
        ).scalar()
        if count == 1:
            conn.execute(
                update(asset_photos).where(asset_photos.c.photo_id == new_id).values(is_primary=1)
            )

        new_row = conn.execute(
            select(asset_photos).where(asset_photos.c.photo_id == new_id)
        ).fetchone()

        conn.commit()

    # F2: Copy file to disk only after the DB record is committed — no orphan on DB failure
    try:
        shutil.copy2(file_path, dest_path)
    except OSError as exc:
        # Roll back the DB record if the file copy fails
        with get_db() as conn:
            conn.execute(delete(asset_photos).where(asset_photos.c.photo_id == new_id))
            conn.commit()
        return jsonify({"error": "SERVER_ERROR", "message": f"Failed to copy photo file: {exc}"}), 500

    # F8: Audit log for photo creation
    _audit_logger.log_change(
        entity_type="asset_photo",
        entity_id=new_id,
        action="CREATE",
        new_value=dest_path,
        actor="system",
    )

    return jsonify({"data": _row_to_dict(new_row)}), 201


@photos_bp.delete("/<int:photo_id>")
@require_auth
def delete_photo(photo_id: int):
    """DELETE /api/v1/photos/<photo_id> — delete a photo and its file."""
    with get_db() as conn:
        row = conn.execute(
            select(asset_photos).where(asset_photos.c.photo_id == photo_id)
        ).fetchone()
        if row is None:
            return jsonify({"error": "NOT_FOUND", "message": "Photo not found"}), 404

        photo = _row_to_dict(row)
        asset_id = photo["asset_id"]
        was_primary = photo["is_primary"] == 1

        # Delete DB record first
        conn.execute(delete(asset_photos).where(asset_photos.c.photo_id == photo_id))

        # If it was primary and there are remaining photos, assign primary to most recent
        if was_primary:
            next_photo = conn.execute(
                select(asset_photos.c.photo_id)
                .where(asset_photos.c.asset_id == asset_id)
                .order_by(asset_photos.c.uploaded_at.desc())
                .limit(1)
            ).fetchone()
            if next_photo:
                conn.execute(
                    update(asset_photos)
                    .where(asset_photos.c.photo_id == next_photo.photo_id)
                    .values(is_primary=1)
                )

        conn.commit()

    # Remove file from disk (best effort — don't fail if already gone)
    try:
        if os.path.isfile(photo["file_path"]):
            os.remove(photo["file_path"])
    except OSError:
        pass

    # F8: Audit log for photo deletion
    _audit_logger.log_change(
        entity_type="asset_photo",
        entity_id=photo_id,
        action="DELETE",
        old_value=photo["file_path"],
        actor="system",
    )

    return "", 204


@photos_bp.patch("/<int:photo_id>/primary")
@require_auth
def set_primary(photo_id: int):
    """PATCH /api/v1/photos/<photo_id>/primary — mark a photo as primary."""
    with get_db() as conn:
        row = conn.execute(
            select(asset_photos).where(asset_photos.c.photo_id == photo_id)
        ).fetchone()
        if row is None:
            return jsonify({"error": "NOT_FOUND", "message": "Photo not found"}), 404

        asset_id = row.asset_id

        # Atomically unset all primaries for this asset, then set the target
        conn.execute(
            update(asset_photos)
            .where(asset_photos.c.asset_id == asset_id)
            .values(is_primary=0)
        )
        conn.execute(
            update(asset_photos)
            .where(asset_photos.c.photo_id == photo_id)
            .values(is_primary=1)
        )
        conn.commit()

        updated = conn.execute(
            select(asset_photos).where(asset_photos.c.photo_id == photo_id)
        ).fetchone()

    return jsonify({"data": _row_to_dict(updated)}), 200
