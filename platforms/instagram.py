"""
Instagram Reels uploader via Meta Graph API.

Required environment variables (set in Railway):
  INSTAGRAM_USER_ID       — Your Instagram Professional account user ID
  INSTAGRAM_ACCESS_TOKEN  — Long-lived Page Access Token with instagram_basic,
                            instagram_content_publish scopes
  PUBLIC_BASE_URL         — Public URL of this Railway app (e.g. https://myapp.railway.app)
                            Used so Instagram can fetch the video file.

One-time setup:
  1. Create a Facebook Developer App at https://developers.facebook.com
  2. Add "Instagram Graph API" product
  3. Connect your Instagram Business/Creator account to a Facebook Page
  4. Generate a long-lived Page Access Token (never expires if refreshed)
  5. Get your Instagram User ID from the API
  6. Set the env vars above in Railway → Variables

Instagram Reels upload flow:
  Step 1: POST /v18.0/{user-id}/media  → create container (returns creation_id)
  Step 2: Poll /v18.0/{creation_id}?fields=status_code until FINISHED
  Step 3: POST /v18.0/{user-id}/media_publish  → publish

NOTE: The video must be reachable at a public HTTPS URL.
      This module uses PUBLIC_BASE_URL + /videos/<filename> served by app.py.
"""
import logging
import os
import time

import requests

logger = logging.getLogger("platforms.instagram")

GRAPH_API = "https://graph.facebook.com/v18.0"


def upload_reel(video_path: str, caption: str) -> str:
    """
    Upload a Reels video to Instagram.
    Returns the Instagram media ID on success. Raises on failure.
    """
    user_id = os.environ.get("INSTAGRAM_USER_ID", "").strip()
    access_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    base_url = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")

    if not user_id or not access_token:
        raise RuntimeError(
            "INSTAGRAM_USER_ID and INSTAGRAM_ACCESS_TOKEN env vars are required. "
            "See platforms/instagram.py for setup instructions."
        )
    if not base_url:
        raise RuntimeError(
            "PUBLIC_BASE_URL env var is required so Instagram can fetch the video. "
            "Set it to your Railway app URL, e.g. https://myapp.railway.app"
        )

    filename = os.path.basename(video_path)
    video_url = f"{base_url}/videos/{filename}"

    # ── Step 1: Create media container ──────────────────────────
    logger.info("  [Instagram] Creating Reels container for %s", filename)
    r = requests.post(
        f"{GRAPH_API}/{user_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption[:2200],  # Instagram caption limit
            "share_to_feed": "true",
            "access_token": access_token,
        },
        timeout=60,
    )
    r.raise_for_status()
    creation_id = r.json().get("id")
    if not creation_id:
        raise RuntimeError(f"No creation_id in response: {r.text}")
    logger.info("  [Instagram] Container created: %s", creation_id)

    # ── Step 2: Poll until processing is FINISHED ────────────────
    logger.info("  [Instagram] Waiting for processing…")
    for attempt in range(30):
        time.sleep(10)
        poll = requests.get(
            f"{GRAPH_API}/{creation_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=30,
        )
        poll.raise_for_status()
        status = poll.json().get("status_code", "")
        logger.info("  [Instagram] Status: %s (attempt %d/30)", status, attempt + 1)
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise RuntimeError("Instagram processing failed with ERROR status")
    else:
        raise RuntimeError("Instagram video processing timed out after 5 minutes")

    # ── Step 3: Publish ──────────────────────────────────────────
    logger.info("  [Instagram] Publishing…")
    pub = requests.post(
        f"{GRAPH_API}/{user_id}/media_publish",
        data={
            "creation_id": creation_id,
            "access_token": access_token,
        },
        timeout=60,
    )
    pub.raise_for_status()
    media_id = pub.json().get("id")
    if not media_id:
        raise RuntimeError(f"No media ID in publish response: {pub.text}")

    logger.info("  [Instagram] Published! Media ID: %s", media_id)
    return media_id
