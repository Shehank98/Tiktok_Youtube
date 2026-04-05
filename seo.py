"""
SEO helper: generate rotating video descriptions with affiliate links and hashtags.
Used by pipeline.py to auto-fill YouTube / Instagram / Facebook captions.
"""
import json
import os
import random

SETTINGS_FILE = os.environ.get("SETTINGS_FILE", "converter_settings.json")

_DEFAULT_HASHTAG_SETS = [
    "#shorts #viral #trending #foryou #fyp #entertainment",
    "#shorts #viral #satisfying #trending #musthave #fyp",
    "#shorts #trending #amazing #viral #youtubeshorts #foryou",
    "#shorts #fyp #viral #explore #reels #entertainment",
]


def _load_settings() -> dict:
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def generate_description(video_index: int = 0) -> str:
    """
    Build a video description with:
      - base call-to-action
      - rotating affiliate link (round-robin by video_index)
      - random hashtag set

    video_index should be the total upload count so the affiliate link
    rotates evenly across uploads.
    """
    settings = _load_settings()

    # Affiliate links list: [{"label": "...", "url": "..."}]
    affiliate_links = settings.get("affiliate_links", [])

    # Hashtag sets: list of hashtag strings
    hashtag_sets = settings.get("hashtag_sets", _DEFAULT_HASHTAG_SETS)
    if not hashtag_sets:
        hashtag_sets = _DEFAULT_HASHTAG_SETS

    lines = [
        "Watch and enjoy!",
        "",
        "LIKE ❤️  SUBSCRIBE 🔔  COMMENT 💬  SHARE 🔁",
    ]

    # Affiliate link — round-robin
    if affiliate_links:
        link = affiliate_links[video_index % len(affiliate_links)]
        label = link.get("label", "Check this out")
        url = link.get("url", "").strip()
        if url:
            lines += ["", f"🔗 {label}: {url}"]

    # Hashtags — random pick
    lines += ["", random.choice(hashtag_sets)]

    return "\n".join(lines)


def generate_title(template: str, count: int) -> str:
    """
    Replace #{count} (or bare #) in title template with the upload number.
    e.g. '#{count} Viral Short' → '42 Viral Short'
    """
    title = template.replace("#{count}", str(count))
    # Also handle bare # at start (legacy format)
    if title.startswith("#") and not title.startswith("#shorts"):
        title = str(count) + title[1:]
    return title[:100]
