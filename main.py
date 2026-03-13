"""
M365 Roadmap -> NotebookLM pipeline
Fetches the most recent SharePoint RSS item, creates a notebook, generates
an Audio Overview (MP3), a Video Overview (MP4), and a Slide Deck (PDF + PPTX),
then saves all artefacts to ./outputs/ and publishes the video to YouTube via Vizard.ai.

Auth: set NOTEBOOKLM_AUTH_JSON env var (no Playwright needed on Railway).
"""

import asyncio
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import httpx
from notebooklm import NotebookLMClient

# -- Config --
RSS_URL = os.getenv(
    "RSS_URL",
    "https://www.microsoft.com/releasecommunications/api/v2/m365/rss?filters=SharePoint&statuses=InDevelopment,RollingOut,launched",
)

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/app/outputs"))
NOTEBOOK_TITLE = os.getenv("NOTEBOOK_TITLE", "SharePoint Roadmap Update")

AUDIO_FORMAT = os.getenv("AUDIO_FORMAT", "deep-dive")
AUDIO_INSTRUCTIONS = os.getenv(
    "AUDIO_INSTRUCTIONS",
    "Make it informative and accessible for IT admins and end-users alike.",
)

SLIDE_FORMAT = os.getenv("SLIDE_FORMAT", "detailed")

VIZARD_API_KEY = os.getenv("VIZARD_API_KEY", "")
VIZARD_SOCIAL_ID = os.getenv("VIZARD_SOCIAL_ID", "")
VIZARD_BASE = "https://elai.vizard.ai/api/open/v1"


# -- Helpers --
def fetch_rss_item(url: str) -> dict:
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


def vizard_publish_to_youtube(video_path: Path, title: str):
    if not VIZARD_API_KEY or not VIZARD_SOCIAL_ID:
        print("  WARNING: VIZARD_API_KEY or VIZARD_SOCIAL_ID not set -- skipping YouTube publish.")
        return None

    headers = {"Authorization": f"Bearer {VIZARD_API_KEY}"}

    print("  Uploading video to Vizard.ai ...")
    with httpx.Client(timeout=300) as client:
        with open(video_path, "rb") as f:
            upload_resp = client.post(
                f"{VIZARD_BASE}/video/upload",
                headers=headers,
                files={"file": (video_path.name, f, "video/mp4")},
                data={"title": title},
            )
        upload_resp.raise_for_status()
        upload_data = upload_resp.json()
        print(f"  Upload response: {upload_data}")

    video_id = (
        upload_data.get("data", {}).get("videoId")
        or upload_data.get("videoId")
        or upload_data.get("id")
    )
    if not video_id:
        print("  WARNING: Could not extract video ID from Vizard upload response.")
        return None

    print(f"  Vizard video ID: {video_id}")
    print(f"  Publishing to YouTube via Vizard (social ID: {VIZARD_SOCIAL_ID}) ...")
    with httpx.Client(timeout=60) as client:
        pub_resp = client.post(
            f"{VIZARD_BASE}/video/{video_id}/publish",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "socialId": VIZARD_SOCIAL_ID,
                "platform": "youtube",
                "title": title,
                "description": f"Auto-generated SharePoint roadmap update via NotebookLM. {title}",
                "privacyStatus": "public",
            },
        )
        pub_resp.raise_for_status()
        pub_data = pub_resp.json()
        print(f"  Publish response: {pub_data}")

    print("  Published to YouTube successfully!")
    return video_id


# -- Pipeline --
async def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching RSS feed ...")
    item = fetch_rss_item(RSS_URL)
    print(f"  Title   : {item['title']}")
    print(f"  Link    : {item['link']}")
    print(f"  Updated : {item['updated']}")

    notebook_title = os.getenv("NOTEBOOK_TITLE") or item["title"] or NOTEBOOK_TITLE

    print("\nConnecting to NotebookLM ...")
    async with await NotebookLMClient.from_storage() as client:

        print(f"Creating notebook: {notebook_title!r} ...")
        nb = await client.notebooks.create(notebook_title)
        nb_id = nb.id
        print(f"  Notebook ID: {nb_id}")

        print(f"\nAdding source URL: {item['link']} ...")
        await client.sources.add_url(nb_id, item["link"], wait=True)
        print("  Source added and indexed")

        print(f"\nGenerating Audio Overview ({AUDIO_FORMAT}) ...")
        audio_status = await client.artifacts.generate_audio(
            nb_id,
            audio_overview_type=AUDIO_FORMAT,
            instructions=AUDIO_INSTRUCTIONS,
        )
        await client.artifacts.wait_for_completion(nb_id, audio_status.task_id)
        print("  Audio ready")
        audio_path = OUTPUT_DIR / f"audio_{ts()}.mp3"
        await client.artifacts.download_audio(nb_id, str(audio_path))
        print(f"  Saved -> {audio_path}")

        print("\nGenerating Video Overview ...")
        video_path = None
        try:
            video_status = await client.artifacts.generate_video(nb_id)
            await client.artifacts.wait_for_completion(nb_id, video_status.task_id)
            print("  Video ready")
            video_path = OUTPUT_DIR / f"video_{ts()}.mp4"
            await client.artifacts.download_video(nb_id, str(video_path))
            print(f"  Saved -> {video_path}")
        except Exception as e:
            print(f"  WARNING: Video generation failed (skipping): {e}")

        if video_path and video_path.exists():
            print("\nPublishing to YouTube via Vizard.ai ...")
            try:
                vizard_publish_to_youtube(video_path, notebook_title)
            except Exception as e:
                print(f"  WARNING: Vizard publish failed (skipping): {e}")
        else:
            print("\nSkipping Vizard publish -- no video file available.")

        print(f"\nGenerating Slide Deck ({SLIDE_FORMAT}) ...")
        slide_status = await client.artifacts.generate_slide_deck(
            nb_id,
            slide_deck_type=SLIDE_FORMAT,
        )
        await client.artifacts.wait_for_completion(nb_id, slide_status.task_id)
        print("  Slides ready")

        pdf_path = OUTPUT_DIR / f"slides_{ts()}.pdf"
        pptx_path = OUTPUT_DIR / f"slides_{ts()}.pptx"
        await client.artifacts.download_slide_deck(nb_id, str(pdf_path), output_format="pdf")
        print(f"  Saved PDF  -> {pdf_path}")
        await client.artifacts.download_slide_deck(nb_id, str(pptx_path), output_format="pptx")
        print(f"  Saved PPTX -> {pptx_path}")

    print("\nAll done!")
    print(f"  Outputs in: {OUTPUT_DIR}")
    for f in sorted(OUTPUT_DIR.iterdir()):
        size_kb = f.stat().st_size // 1024
        print(f"  {f.name} ({size_kb} KB)")


if __name__ == "__main__":
    asyncio.run(run())
