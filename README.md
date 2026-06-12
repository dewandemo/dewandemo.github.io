# Community Health Dashboard

A static GitHub Pages dashboard for Discourse community health metrics.

Credentials **never reach the browser** — a GitHub Actions workflow fetches data server-side and writes static JSON files that the page reads.

## Architecture

```
GitHub Actions (scheduled + manual)
  └── scripts/fetch_data.py   ← uses secrets, calls Discourse API
        └── data/*.json        ← committed to repo
              └── index.html   ← reads JSON, no credentials, no API calls
```

## What it shows

| Tab               | Description                                                       |
| ----------------- | ----------------------------------------------------------------- |
| **30-day Health** | KPI cards: new topics, active users, replies, likes               |
| **Response Time** | Per-topic time-to-first-engagement (reply, reaction, or solution) |
| **Solved Topics** | Solve rate and avg time-to-solve per category                     |
| **Contributors**  | Top 10 reply contributors in the last 30 days                     |

## Setup

### 1. Fork / push to GitHub

Push this repo to GitHub. GitHub Pages will serve `index.html` from the root of `main`.

### 2. Enable GitHub Pages

Go to **Settings → Pages → Source** and set it to **Deploy from branch → main → / (root)**.

### 3. Add secrets

Go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret name              | Value                                                        |
| ------------------------ | ------------------------------------------------------------ |
| `DISCOURSE_URL`          | `https://your-community.discourse.group` (no trailing slash) |
| `DISCOURSE_API_KEY`      | Your Discourse API key (Admin → API → New API Key)           |
| `DISCOURSE_API_USERNAME` | The admin username the key belongs to                        |

The API key needs **All Users** scope and the **Data Explorer** plugin must be installed.

### 4. Run the workflow

Go to **Actions → Refresh community data → Run workflow**.  
The workflow commits `data/*.json` to the repo, and GitHub Pages serves the updated files.

The workflow also runs automatically every 6 hours via cron.

### 5. Open the dashboard

Visit `https://dewandemo.github.io/`.

## Refreshing data

Click **Refresh data** in the top-right corner — it opens the GitHub Actions workflow page where you can trigger a manual run. After the run completes (~30 seconds), reload the dashboard page.

## Running locally

```bash
git clone https://github.com/dewandemo/dewandemo.github.io.git
cd dewandemo.github.io

# Fetch data locally (requires env vars)
export DISCOURSE_URL="https://your-community.discourse.group"
export DISCOURSE_API_KEY="your_api_key"
export DISCOURSE_API_USERNAME="your_admin_username"
python3 scripts/fetch_data.py

# Serve the dashboard
python3 -m http.server 8080
# Open http://localhost:8080
```
