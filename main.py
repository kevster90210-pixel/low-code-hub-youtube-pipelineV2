"""
M365 Roadmap → NotebookLM pipeline
Fetches the Microsoft 365 RSS item, creates a notebook, generates
an Audio Overview (MP3) and a Slide Deck (PDF + PPTX), then saves
all artefacts to ./outputs/.

Auth: set NOTEBOOKLM_AUTH_JSON env var (no Playwright needed on Railway).
"""

import asyncio
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import httpx
from notebooklm import NotebookLMClient

# ── Config ────────────────────────────────────────────────────────────────────
RSS_URL = os.getenv(
    "RSS_URL",
    "https://www.microsoft.com/releasecommunications/api/v2/m365/rss/492622",
)
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/app/outputs"))
NOTEBOOK_TITLE = os.getenv("NOTEBOOK_TITLE", "M365 Roadmap – Next-Gen File Sharing")

# Audio options (deep-dive | brief | critique | debate)
AUDIO_FORMAT = os.getenv("AUDIO_FORMAT", "deep-dive")
AUDIO_INSTRUCTIONS = os.getenv(
    "AUDIO_INSTRUCTIONS",
    "Make it informative and accessible for IT admins and end-users alike.",
)

# Slide-deck options (detailed | presenter)
SLIDE_FORMAT = os.getenv("SLIDE_FORMAT", "detailed")


# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch_rss_item(url: str) -> dict:
    """Return the first RSS <item> as a dict with keys: title, link, description, pubDate."""
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        resp = client.get(url)
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    item = root.find(".//item")
    if item is None:
        raise ValueError("No <item> found in RSS feed")

    return {
        "title": (item.findtext("title") or "").strip(),
        "link": (item.findtext("link") or "").strip(),
        "description": (item.findtext("description") or "").strip(),
        "pubDate": (item.findtext("pubDate") or "").strip(),
        "updated": (item.find("atom:updated", ns) or item).text or "",
    }


def ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Fetch RSS
    print("📡  Fetching RSS feed …")
    item = fetch_rss_item(RSS_URL)
    print(f"    Title   : {item['title']}")
    print(f"    Link    : {item['link']}")
    print(f"    Updated : {item['updated']}")

    # 2. Connect to NotebookLM
    print("\n🔑  Connecting to NotebookLM …")
    async with await NotebookLMClient.from_storage() as client:

        # 3. Create notebook
        print(f"📒  Creating notebook: "{NOTEBOOK_TITLE}" …")
        nb = await client.notebooks.create(NOTEBOOK_TITLE)
        nb_id = nb.id
        print(f"    Notebook ID: {nb_id}")

        # 4. Add the roadmap page as a URL source
        print(f"\n🔗  Adding source URL: {item['link']} …")
        await client.sources.add_url(nb_id, item["link"], wait=True)
        print("    Source added and indexed ✓")

        # 5. Generate Audio Overview
        print(f"\n🎙️  Generating Audio Overview ({AUDIO_FORMAT}) …")
        audio_status = await client.artifacts.generate_audio(
            nb_id,
            audio_overview_type=AUDIO_FORMAT,
            instructions=AUDIO_INSTRUCTIONS,
        )
        print(f"    Task ID: {audio_status.task_id} — waiting for completion …")
        await client.artifacts.wait_for_completion(nb_id, audio_status.task_id)
        print("    Audio ready ✓")

        audio_path = OUTPUT_DIR / f"audio_{ts()}.mp3"
        await client.artifacts.download_audio(nb_id, str(audio_path))
        print(f"    Saved → {audio_path}")

        # 6. Generate Slide Deck
        print(f"\n📊  Generating Slide Deck ({SLIDE_FORMAT}) …")
        slide_status = await client.artifacts.generate_slide_deck(
            nb_id,
            slide_deck_type=SLIDE_FORMAT,
        )
        print(f"    Task ID: {slide_status.task_id} — waiting for completion …")
        await client.artifacts.wait_for_completion(nb_id, slide_status.task_id)
        print("    Slides ready ✓")

        # Download both PDF and PPTX
        pdf_path = OUTPUT_DIR / f"slides_{ts()}.pdf"
        pptx_path = OUTPUT_DIR / f"slides_{ts()}.pptx"

        await client.artifacts.download_slide_deck(nb_id, str(pdf_path), output_format="pdf")
        print(f"    Saved PDF  → {pdf_path}")

        await client.artifacts.download_slide_deck(nb_id, str(pptx_path), output_format="pptx")
        print(f"    Saved PPTX → {pptx_path}")

    print("\n✅  All done!")
    print(f"    Outputs in: {OUTPUT_DIR}")
    for f in sorted(OUTPUT_DIR.iterdir()):
        size_kb = f.stat().st_size // 1024
        print(f"      {f.name}  ({size_kb} KB)")


if __name__ == "__main__":
    asyncio.run(run())
