# M365 Roadmap → NotebookLM Pipeline

Fetches the Microsoft 365 "Next Generation of File & Folder Sharing" roadmap
item via RSS, then uses **notebooklm-py** to:

1. Create a NotebookLM notebook
2. Add the roadmap page as a source
3. Generate an **Audio Overview** (MP3 podcast)
4. Generate a **Slide Deck** (PDF + editable PPTX)
5. Save everything to `/app/outputs/`

Designed to run as a one-shot **Railway** worker job.

---

## 🚂 Deploy to Railway (2 steps)

### Step 1 — Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
gh repo create m365-notebooklm-pipeline --private --push
```

### Step 2 — Set environment variables in Railway

Connect the GitHub repo in Railway, then add these variables under
**Settings → Variables**:

| Variable | Value | Required |
|---|---|---|
| `NOTEBOOKLM_AUTH_JSON` | Your Google session JSON (see `.env.example`) | ✅ |
| `RSS_URL` | `https://www.microsoft.com/releasecommunications/api/v2/m365/rss/492622` | default set |
| `NOTEBOOK_TITLE` | Custom name for the notebook | optional |
| `AUDIO_FORMAT` | `deep-dive` / `brief` / `critique` / `debate` | default: `deep-dive` |
| `AUDIO_INSTRUCTIONS` | Custom prompt for the audio host | optional |
| `SLIDE_FORMAT` | `detailed` / `presenter` | default: `detailed` |

> ⚠️ **Session expiry** — Google sessions typically last 1–2 weeks.
> When it expires, re-export cookies and update the Railway variable.

### Run as one-shot or on a schedule

`restartPolicyType: NEVER` means the container exits cleanly after the pipeline
finishes. To run on a schedule (e.g. weekly):

- Railway → your service → **Settings → Cron**
- Example: `0 9 * * 1` (every Monday at 9 AM UTC)

---

## 📦 Retrieve outputs

Railway's ephemeral storage resets between runs. Options:

**Option A – Volume mount (recommended)**
Add a Railway Volume and mount it at `/app/outputs`.

**Option B – Upload to cloud storage**
Extend `main.py` to push generated files to S3 / Azure Blob / GCS.

---

## 🏃 Run locally

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env: paste your storage_state.json into NOTEBOOKLM_AUTH_JSON
set -a && source .env && set +a
python main.py
```

---

## 🌲 Project structure

```
.
├── main.py          # Pipeline script
├── requirements.txt
├── Dockerfile
├── railway.json
├── .env.example
└── README.md
```

---

## ⚠️ Disclaimer

Uses **notebooklm-py**, an unofficial library. Not affiliated with Google.
APIs may break without notice. Recommended: use a dedicated Google account.
