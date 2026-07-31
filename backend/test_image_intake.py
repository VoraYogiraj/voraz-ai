"""
test_image_intake.py
Run from inside backend/:
    python test_image_intake.py

What this tests:
  1. Consent gate — confirms ConsentNotGivenError fires when consent_given=False
  2. Storage upload — image lands in Supabase Storage bucket 'customer-photos'
  3. Vision call — GPT-4o-mini returns valid colors/silhouettes from the known vocab
  4. DB write — photo_uploads row inserted with correct fields
  5. Return value — dict has expected keys and non-empty values

Pass the image path as the first CLI arg, or it defaults to the path below.
"""

import json
import sys
import os
from pathlib import Path

# ── allow bare imports from backend/ ──────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from agents.image_intake import (
    process_photo,
    ConsentNotGivenError,
    VALID_COLORS,
    VALID_SILHOUETTES,
)
from services.supabase_client import get_supabase

IMAGE_PATH = sys.argv[1] if len(sys.argv) > 1 else "test_sample.jpg"
TEST_SESSION_ID = "test-session-image-intake-001"

PASS = "✅"
FAIL = "❌"


def section(title):
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")


# ── 1. Load image ─────────────────────────────────────────────────────────────
section("1. Loading image from disk")
try:
    image_bytes = Path(IMAGE_PATH).read_bytes()
    file_ext = Path(IMAGE_PATH).suffix.lstrip(".") or "jpg"
    print(f"{PASS} Loaded {len(image_bytes):,} bytes  ext={file_ext}")
except FileNotFoundError:
    print(f"{FAIL} Image not found at: {IMAGE_PATH}")
    print("     Pass the path as: python test_image_intake.py <path/to/image.jpg>")
    sys.exit(1)


# ── 2. Consent gate ───────────────────────────────────────────────────────────
section("2. Consent gate (consent_given=False should raise)")
try:
    process_photo(TEST_SESSION_ID, image_bytes, consent_given=False)
    print(f"{FAIL} No error raised — consent gate is broken")
    sys.exit(1)
except ConsentNotGivenError as e:
    print(f"{PASS} ConsentNotGivenError raised correctly: {e}")
except Exception as e:
    print(f"{FAIL} Wrong exception type raised: {type(e).__name__}: {e}")
    sys.exit(1)


# ── 3. Full run with consent ───────────────────────────────────────────────────
section("3. Full process_photo() call (consent_given=True)")
print("     Uploading to Supabase Storage + calling GPT-4o-mini vision...")
try:
    result = process_photo(
        session_id=TEST_SESSION_ID,
        image_bytes=image_bytes,
        consent_given=True,
        customer_id=None,
        file_ext=file_ext,
    )
    print(f"{PASS} process_photo() returned without exception")
    print(f"     Result: {json.dumps(result, indent=4)}")
except Exception as e:
    print(f"{FAIL} process_photo() raised: {type(e).__name__}: {e}")
    sys.exit(1)


# ── 4. Validate returned values ───────────────────────────────────────────────
section("4. Validating returned signals")

errors = []

if not isinstance(result.get("undertone_colors"), list):
    errors.append("undertone_colors is not a list")
if not isinstance(result.get("body_shape_silhouettes"), list):
    errors.append("body_shape_silhouettes is not a list")
if result.get("confidence") not in ("low", "medium", "high"):
    errors.append(f"confidence value unexpected: {result.get('confidence')}")

# Check all returned values are from known vocab
for c in result.get("undertone_colors", []):
    if c not in VALID_COLORS:
        errors.append(f"undertone_colors contains unknown value: '{c}'")

for s in result.get("body_shape_silhouettes", []):
    if s not in VALID_SILHOUETTES:
        errors.append(f"body_shape_silhouettes contains unknown value: '{s}'")

if errors:
    for e in errors:
        print(f"{FAIL} {e}")
else:
    print(f"{PASS} All returned values are valid")
    print(f"     undertone_colors       : {result['undertone_colors']}")
    print(f"     body_shape_silhouettes : {result['body_shape_silhouettes']}")
    print(f"     confidence             : {result['confidence']}")


# ── 5. Confirm Supabase DB write ──────────────────────────────────────────────
section("5. Confirming photo_uploads row in Supabase")
try:
    supabase = get_supabase()
    rows = (
        supabase.table("photo_uploads")
        .select("session_id, image_ref, undertone_result, body_shape_result, consent_given, consent_timestamp, delete_after")
        .eq("session_id", TEST_SESSION_ID)
        .order("consent_timestamp", desc=True)
        .limit(1)
        .execute()
    )
    if rows.data:
        row = rows.data[0]
        print(f"{PASS} Row found in photo_uploads:")
        for k, v in row.items():
            print(f"     {k}: {v}")
        if not row.get("consent_given"):
            print(f"{FAIL} consent_given is not True in DB row")
        if not row.get("delete_after"):
            print(f"{FAIL} delete_after is missing in DB row")
    else:
        print(f"{FAIL} No row found in photo_uploads for session_id={TEST_SESSION_ID}")
except Exception as e:
    print(f"{FAIL} Supabase query failed: {type(e).__name__}: {e}")


# ── Summary ───────────────────────────────────────────────────────────────────
section("Done")
print("  If all steps show ✅, image_intake.py is end-to-end verified.")
print("  Any ❌ above needs fixing before building the /api/chat/photo endpoint.")
print()