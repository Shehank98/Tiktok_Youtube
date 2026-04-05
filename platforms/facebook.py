"""
Facebook Reels uploader via Meta Graph API.

Required environment variables (set in Railway):
  FACEBOOK_PAGE_ID        — Your Facebook Page ID (numeric)
  FACEBOOK_ACCESS_TOKEN   — Page Access Token with pages_manage_posts,
                            pages_read_engagement scopes
  PUBLIC_BASE_URL         — Public URL of this Railway app (e.g. https://myapp.railway.app)

One-time setup:
  1. Create a Facebook Developer App at https://developers.facebook.com
  2. Add "Facebook Login for Business" or "Pages API" product
  3. Get a long-lived Page Access Token for your Facebook Page
  4. Get your Facebook Page ID (visible in Page settings → About)
  5. Set the env vars above in Railway → Variables

Facebook Reels upload flow:
  Step 1: POST /{page-id}/video_reels?upload_phase=start  → get upload_url + video_id
  Step 2: PUT {upload_url}  with raw video bytes
  Step 3: POST /{page-id}/video_reels?upload_phase=finish  → publish
"""
import logging
import os

import requests

logger = logging.getLogger("platforms.facebook")

GRAPH_API = "https://graph.facebook.com/v18.0"


def upload_reel(video_path: str, description: str) -> str:
    """
    Upload a Reels video to a Facebook Page.
    Returns the Facebook video ID on success. Raises on failure.
    """
    page_id = os.environ.get("FACEBOOK_PAGE_ID", "").strip()
    access_token = os.environ.get("FACEBOOK_ACCESS_TOKEN", "").strip()

    if not page_id or not access_token:
        raise RuntimeError(
            "FACEBOOK_PAGE_ID and FACEBOOK_ACCESS_TOKEN env vars are required. "
            "See platforms/facebook.py for setup instructions."
        )

    filename = os.path.basename(video_path)
    file_size = os.path.getsize(video_path)

    # ── Step 1: Initialize upload session ───────────────────────
    logger.info("  [Facebook] Starting Reels upload for %s (%d bytes)", filename, file_size)
    r = requests.post(
        f"{GRAPH_API}/{page_id}/video_reels",
        params={
            "upload_phase": "start",
            "access_token": access_token,
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    upload_url = data.get("upload_url")
    video_id = data.get("video_id")
    if not upload_url or not video_id:
        raise RuntimeError(f"Missing upload_url/video_id in start response: {r.text}")
    logger.info("  [Facebook] Upload session created, video_id: %s", video_id)

    # ── Step 2: Upload video binary ──────────────────────────────
    logger.info("  [Facebook] Uploading video bytes…")
    with open(video_path, "rb") as fh:
        upload_resp = requests.put(
            upload_url,
            data=fh,
            headers={
                "Authorization": f"OAuth {access_token}",
                "offset": "0",
                "file_size": str(file_size),
            },
            timeout=600,
        )
    upload_resp.raise_for_status()
    logger.info("  [Facebook] Video bytes uploaded successfully")

    # ── Step 3: Publish ──────────────────────────────────────────
    logger.info("  [Facebook] Publishing Reel…")
    finish = requests.post(
        f"{GRAPH_API}/{page_id}/video_reels",
        params={
            "upload_phase": "finish",
            "video_id": video_id,
            "access_token": access_token,
        },
        data={
            "video_id": video_id,
            "description": description[:63206],  # Facebook description limit
            "published": "true",
        },
        timeout=60,
    )
    finish.raise_for_status()

    logger.info("  [Facebook] Published! Video ID: %s", video_id)
    return video_id
