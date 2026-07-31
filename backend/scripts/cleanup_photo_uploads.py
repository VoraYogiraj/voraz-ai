"""
Deletes expired photo_uploads rows (past their delete_after retention date)
and removes the corresponding file from Supabase Storage.

Intended to run as a scheduled job (e.g. a Render Cron Job), not as part
of the FastAPI app process — no in-process scheduler needed.

Run manually with: python scripts/cleanup_photo_uploads.py
"""
import logging
from datetime import datetime, timezone
from services.supabase_client import get_supabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BUCKET = "customer-photos"


def cleanup_expired_photos() -> int:
    sb = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    expired = (
        sb.table("photo_uploads")
        .select("id, image_ref")
        .lt("delete_after", now)
        .execute()
    )

    rows = expired.data or []
    if not rows:
        logger.info("No expired photo_uploads rows found.")
        return 0

    deleted_count = 0
    for row in rows:
        row_id = row["id"]
        image_ref = row.get("image_ref")

        try:
            if image_ref:
                sb.storage.from_(BUCKET).remove([image_ref])
        except Exception as e:
            # Log and continue — don't let a storage failure block DB cleanup
            logger.error(f"Failed to delete storage object {image_ref}: {e}")

        try:
            sb.table("photo_uploads").delete().eq("id", row_id).execute()
            deleted_count += 1
        except Exception as e:
            logger.error(f"Failed to delete photo_uploads row {row_id}: {e}")

    logger.info(f"Cleaned up {deleted_count} expired photo_uploads rows.")
    return deleted_count


if __name__ == "__main__":
    cleanup_expired_photos()