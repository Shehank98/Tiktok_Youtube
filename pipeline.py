"""
Core headless pipeline: download TikTok → convert to Shorts → upload to YouTube.
No GUI dependencies. Used by both scheduler.py and Flask app.py.
"""
import json
import logging
import os
import shutil
import subprocess
import time
from datetime import date
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import db
import seo

logger = logging.getLogger("pipeline")

# ──────────────────────────────────────────────
# Config helpers
# ──────────────────────────────────────────────
SETTINGS_FILE = os.environ.get("SETTINGS_FILE", "converter_settings.json")

def load_settings() -> dict:
    with open(SETTINGS_FILE, "r") as f:
        return json.load(f)


# ──────────────────────────────────────────────
# YouTube auth helpers
# ──────────────────────────────────────────────
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_FILE = os.environ.get("TOKEN_FILE", "token.json")
CLIENT_SECRETS = os.environ.get("CLIENT_SECRETS_FILE", "client_secrets.json")


def get_youtube_service():
    """Return authenticated YouTube service. Raises if token.json missing."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    if not os.path.exists(TOKEN_FILE):
        raise RuntimeError("token.json not found — visit /auth to authenticate first.")

    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(creds)

    return build("youtube", "v3", credentials=creds)


def _save_token(creds):
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())


def start_auth_flow():
    """Return (auth_url, flow) for the web-based auth setup page."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
    flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
    auth_url, _ = flow.authorization_url(prompt="consent")
    return auth_url, flow


def finish_auth_flow(flow, code: str):
    """Exchange code for credentials and save token.json."""
    flow.fetch_token(code=code)
    _save_token(flow.credentials)


# ──────────────────────────────────────────────
# Download
# ──────────────────────────────────────────────
def download_tiktok_channel(url_or_user: str, count: int, dest_folder: str) -> list:
    """
    Download up to `count` videos from a TikTok channel/URL into dest_folder.
    Returns list of absolute paths to downloaded .mp4 files.
    """
    Path(dest_folder).mkdir(parents=True, exist_ok=True)

    if url_or_user.startswith("@"):
        url = f"https://www.tiktok.com/{url_or_user}"
    else:
        url = url_or_user

    output_template = os.path.join(dest_folder, "%(title).80B.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", "best[ext=mp4]",
        "-o", output_template,
        "--no-warnings",
        "-q",
        "--playlist-start", "1",
        "--playlist-end", str(count),
        "--max-downloads", str(count),
        "--break-on-existing",
        url,
    ]

    logger.info("Downloading from %s (max %d)…", url, count)
    t_start = time.time()

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if result.returncode not in (0, 101):  # 101 = max-downloads reached (ok)
            logger.warning("yt-dlp stderr: %s", result.stderr[:300])
    except subprocess.TimeoutExpired:
        logger.error("Download timed out after 15 min")
        return []

    # Collect videos downloaded in this session (modified within last hour)
    cutoff = t_start - 5
    videos = []
    for f in Path(dest_folder).iterdir():
        if f.suffix.lower() in (".mp4", ".mov", ".avi", ".mkv"):
            if f.stat().st_mtime >= cutoff:
                videos.append(str(f))

    logger.info("Downloaded %d video(s)", len(videos))
    return sorted(videos)


# ──────────────────────────────────────────────
# Video conversion helpers
# ──────────────────────────────────────────────
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
TOP_H = 384
MID_H = 1152
BOT_H = 384


def _load_font(size: int):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "arial.ttf",
        "Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _make_text_panel(hex_color: str, size: tuple, text: str, text_color: str, font_size: int):
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    img = Image.new("RGB", size, (r, g, b))
    if text:
        draw = ImageDraw.Draw(img)
        font = _load_font(font_size)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (size[0] - tw) // 2
        y = (size[1] - th) // 2
        tc = text_color.lstrip("#")
        tr, tg, tb = int(tc[0:2], 16), int(tc[2:4], 16), int(tc[4:6], 16)
        draw.text((x, y), text, fill=(tr, tg, tb), font=font)
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def _check_ffmpeg() -> bool:
    """Return True if ffmpeg/ffprobe are available on PATH."""
    try:
        subprocess.run(["ffprobe", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _merge_audio(processed_video: str, original_video: str) -> bool:
    """Copy audio from original into the processed video using ffmpeg."""
    if not _check_ffmpeg():
        logger.warning("  ffprobe/ffmpeg not found — video will have no audio. "
                       "Ensure ffmpeg is installed (nixpacks.toml adds it on Railway).")
        return False

    # Probe for audio stream
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "default=nk=1:nw=1", original_video],
        capture_output=True, text=True, timeout=30
    )
    if probe.returncode != 0 or not probe.stdout.strip():
        logger.info("  No audio in source; keeping silent output")
        return True

    final_path = processed_video.replace(".mp4", "_final.mp4")
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", processed_video,
        "-i", original_video,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart", "-shortest",
        final_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if res.returncode != 0:
        logger.warning("  ffmpeg audio merge error: %s", res.stderr[:200])
        return False
    os.replace(final_path, processed_video)
    return True


def convert_to_shorts(video_path: str, output_folder: str, settings: dict) -> str:
    """
    Convert a video to YouTube Shorts format (1080×1920) with text overlays.
    Returns path to the output file.
    """
    Path(output_folder).mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0 or fps > 60:
        fps = 30
    fps = round(fps)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    logger.info("  Source: %dx%d @ %dfps", width, height, fps)

    top_img = _make_text_panel(
        settings.get("top_bg_color", "#000000"),
        (OUTPUT_WIDTH, TOP_H),
        settings.get("top_text", "Viral"),
        settings.get("top_text_color", "#FFFFFF"),
        int(settings.get("top_font_size", 80)),
    )
    bot_img = _make_text_panel(
        settings.get("bottom_bg_color", "#000000"),
        (OUTPUT_WIDTH, BOT_H),
        settings.get("bottom_text", "Subscribe"),
        settings.get("bottom_text_color", "#FFFFFF"),
        int(settings.get("bottom_font_size", 80)),
    )

    aspect = width / height
    target_aspect = OUTPUT_WIDTH / MID_H
    if aspect > target_aspect:
        new_w = OUTPUT_WIDTH
        new_h = int(new_w / aspect)
    else:
        new_h = MID_H
        new_w = int(new_h * aspect)
    if new_w % 2:
        new_w -= 1
    if new_h % 2:
        new_h -= 1
    x_off = (OUTPUT_WIDTH - new_w) // 2
    y_off = (MID_H - new_h) // 2

    base = os.path.splitext(os.path.basename(video_path))[0]
    out_path = os.path.join(output_folder, f"shorts_{base}.mp4")
    if os.path.exists(out_path):
        os.remove(out_path)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(out_path, fourcc, fps, (OUTPUT_WIDTH, OUTPUT_HEIGHT))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError("Cannot create output video writer")

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        resized = cv2.resize(frame, (new_w, new_h))
        mid = np.zeros((MID_H, OUTPUT_WIDTH, 3), dtype=np.uint8)
        mid[y_off:y_off + new_h, x_off:x_off + new_w] = resized
        out_frame = np.vstack([top_img, mid, bot_img])
        writer.write(out_frame)

    cap.release()
    writer.release()

    logger.info("  Merging audio…")
    _merge_audio(out_path, video_path)

    if not os.path.exists(out_path):
        raise RuntimeError("Output file not created")

    size_mb = os.path.getsize(out_path) / 1024 / 1024
    logger.info("  Saved %.1f MB → %s", size_mb, out_path)
    return out_path


# ──────────────────────────────────────────────
# Upload
# ──────────────────────────────────────────────
def upload_to_youtube(video_path: str, title: str, description: str, tags: list,
                      privacy: str = "public") -> str:
    """Upload video to YouTube. Returns video ID. Raises on failure."""
    from googleapiclient.http import MediaFileUpload

    service = get_youtube_service()

    safe_tags = [t.strip() for t in tags if t.strip()][:30]
    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": safe_tags,
            "categoryId": "24",  # Entertainment
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(video_path, chunksize=5 * 1024 * 1024,
                            resumable=True, mimetype="video/mp4")
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        _, response = request.next_chunk()

    vid_id = response["id"]
    logger.info("  Uploaded → https://youtube.com/watch?v=%s", vid_id)
    return vid_id


# ──────────────────────────────────────────────
# Retry helper
# ──────────────────────────────────────────────
def with_retry(fn, *args, retries=3, delay=30, **kwargs):
    for attempt in range(1, retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt == retries:
                raise
            logger.warning("  Attempt %d failed (%s). Retrying in %ds…", attempt, e, delay)
            time.sleep(delay * attempt)


# ──────────────────────────────────────────────
# Main pipeline entry point
# ──────────────────────────────────────────────
def run_pipeline(log_callback=None):
    """
    Full pipeline: download → convert → upload.
    log_callback(msg) is called for status updates (used by Flask SSE log).
    """
    def log(msg):
        logger.info(msg)
        if log_callback:
            log_callback(msg)

    settings = load_settings()
    channels = settings.get("tiktok_channels", [])
    if not channels:
        log("No TikTok channels configured. Add them in Settings.")
        return

    limit = int(settings.get("upload_limit_per_day", 3))
    today_count = db.get_daily_count()
    if today_count >= limit:
        log(f"Daily upload limit reached ({today_count}/{limit}). Skipping run.")
        return

    remaining = limit - today_count
    count_per_run = int(settings.get("download_count_per_run", 3))
    to_download = min(remaining, count_per_run)

    download_folder = settings.get("download_folder", "./downloads")
    output_folder = settings.get("output_folder", "./output")
    title_template = settings.get("youtube_title", "#{count} Viral Short")
    tags = [t.strip() for t in settings.get("youtube_tags", "shorts,viral").split(",")]
    privacy = settings.get("privacy_status", "public")
    enable_youtube = settings.get("enable_youtube", True)
    enable_instagram = settings.get("enable_instagram", False)
    enable_facebook = settings.get("enable_facebook", False)

    # Pick a channel (round-robin via a simple counter file)
    channel = channels[0] if len(channels) == 1 else _pick_channel(channels)

    log(f"[pipeline] Starting — channel: {channel}, download: {to_download}")

    videos = download_tiktok_channel(channel, to_download, download_folder)
    if not videos:
        log("[pipeline] No videos downloaded. Aborting.")
        return

    uploaded = 0
    for video_path in videos:
        fname = os.path.basename(video_path)
        if db.already_uploaded(fname):
            log(f"  Skipping {fname} (already uploaded)")
            continue

        log(f"  Converting {fname}…")
        try:
            out_path = convert_to_shorts(video_path, output_folder, settings)
        except Exception as e:
            log(f"  Convert failed for {fname}: {e}")
            db.record_upload(fname, "", "", "failed")
            continue

        # Build title and description
        total_ever = db.get_daily_count() + 1
        title = seo.generate_title(title_template, total_ever)
        description = seo.generate_description(total_ever)

        log(f"  Uploading {os.path.basename(out_path)}…")
        yt_id = ""
        upload_ok = False

        # ── YouTube ──────────────────────────────────────────────
        if enable_youtube:
            try:
                yt_id = with_retry(upload_to_youtube, out_path, title, description, tags, privacy)
                log(f"  YouTube → youtube.com/watch?v={yt_id}")
                upload_ok = True
            except Exception as e:
                log(f"  YouTube upload failed: {e}")

        # ── Instagram ─────────────────────────────────────────────
        if enable_instagram:
            try:
                from platforms.instagram import upload_reel as ig_upload
                ig_id = with_retry(ig_upload, out_path, description)
                log(f"  Instagram → reel published (id: {ig_id})")
                upload_ok = True
            except Exception as e:
                log(f"  Instagram upload failed: {e}")

        # ── Facebook ──────────────────────────────────────────────
        if enable_facebook:
            try:
                from platforms.facebook import upload_reel as fb_upload
                fb_id = with_retry(fb_upload, out_path, description)
                log(f"  Facebook → reel published (id: {fb_id})")
                upload_ok = True
            except Exception as e:
                log(f"  Facebook upload failed: {e}")

        if upload_ok:
            db.record_upload(fname, yt_id, title, "success")
            # Move to uploaded/ folder
            uploaded_dir = os.path.join(output_folder, "uploaded")
            Path(uploaded_dir).mkdir(parents=True, exist_ok=True)
            shutil.move(out_path, os.path.join(uploaded_dir, os.path.basename(out_path)))
            log(f"  Done — moved to uploaded/")
            uploaded += 1
        else:
            db.record_upload(fname, "", title, "failed")

        if db.get_daily_count() >= limit:
            log(f"  Daily limit reached ({limit}). Stopping early.")
            break

    log(f"[pipeline] Run complete. Uploaded {uploaded} video(s) today total: {db.get_daily_count()}/{limit}.")


def _pick_channel(channels: list) -> str:
    """Simple round-robin channel picker using a counter file."""
    counter_file = ".channel_counter"
    idx = 0
    if os.path.exists(counter_file):
        try:
            with open(counter_file) as f:
                idx = int(f.read().strip())
        except Exception:
            idx = 0
    chosen = channels[idx % len(channels)]
    with open(counter_file, "w") as f:
        f.write(str((idx + 1) % len(channels)))
    return chosen
