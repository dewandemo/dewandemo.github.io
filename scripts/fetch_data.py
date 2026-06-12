#!/usr/bin/env python3
"""
Fetches community health data from Discourse Data Explorer and writes
results to data/*.json. Runs in GitHub Actions — credentials never
reach the browser.

Required env vars: DISCOURSE_URL, DISCOURSE_API_KEY, DISCOURSE_API_USERNAME
"""

import json
import os
import sys
import requests
from datetime import datetime, timezone

DISCOURSE_URL = os.environ.get("DISCOURSE_URL", "").rstrip("/")
API_KEY       = os.environ.get("DISCOURSE_API_KEY", "")
API_USERNAME  = os.environ.get("DISCOURSE_API_USERNAME", "")

missing = [k for k, v in {"DISCOURSE_URL": DISCOURSE_URL, "DISCOURSE_API_KEY": API_KEY, "DISCOURSE_API_USERNAME": API_USERNAME}.items() if not v]
if missing:
    print(f"ERROR: Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
    sys.exit(1)

print(f"Connecting to {DISCOURSE_URL} as {API_USERNAME}")

QUERIES = {
    "health": {
        "name": "Dashboard – 30-day Health",
        "sql": """SELECT
  (SELECT COUNT(*) FROM topics WHERE deleted_at IS NULL AND created_at > NOW() - INTERVAL '30 days' AND archetype = 'regular') AS new_topics,
  (SELECT COUNT(DISTINCT user_id) FROM posts WHERE deleted_at IS NULL AND created_at > NOW() - INTERVAL '30 days' AND user_id > 0) AS active_users,
  (SELECT COUNT(*) FROM posts WHERE deleted_at IS NULL AND created_at > NOW() - INTERVAL '30 days' AND post_number > 1 AND post_type = 1) AS replies,
  (SELECT COUNT(*) FROM post_actions WHERE post_action_type_id = 2 AND deleted_at IS NULL AND created_at > NOW() - INTERVAL '30 days') AS likes""",
    },
    "response": {
        "name": "Dashboard – Response Time",
        "sql": """WITH first_reply AS (
  SELECT p.topic_id, MIN(p.created_at) AS first_reply_at
  FROM posts p WHERE p.post_number > 1 AND p.post_type = 1 AND p.deleted_at IS NULL
  GROUP BY p.topic_id
),
first_reaction AS (
  SELECT p.topic_id, MIN(pa.created_at) AS first_reaction_at
  FROM post_actions pa JOIN posts p ON pa.post_id = p.id
  WHERE pa.post_action_type_id = 2 AND p.post_number = 1 AND pa.deleted_at IS NULL
  GROUP BY p.topic_id
),
solution AS (
  SELECT st.topic_id, MIN(ta.created_at) AS solved_at
  FROM discourse_solved_solved_topics st
  JOIN discourse_solved_topic_answers ta ON ta.solved_topic_id = st.id
  GROUP BY st.topic_id
)
SELECT c.name AS category, t.id AS topic_id, t.title, t.created_at AS topic_created_at,
  fr.first_reply_at, fre.first_reaction_at, s.solved_at,
  LEAST(fr.first_reply_at, fre.first_reaction_at, s.solved_at) AS first_engagement_at,
  ROUND(EXTRACT(EPOCH FROM LEAST(fr.first_reply_at, fre.first_reaction_at, s.solved_at) - t.created_at)/3600, 2) AS time_to_first_engagement
FROM topics t JOIN categories c ON c.id = t.category_id
LEFT JOIN first_reply fr ON fr.topic_id = t.id
LEFT JOIN first_reaction fre ON fre.topic_id = t.id
LEFT JOIN solution s ON s.topic_id = t.id
WHERE t.deleted_at IS NULL AND t.archetype = 'regular'
  AND coalesce(fr.first_reply_at, fre.first_reaction_at, s.solved_at) IS NOT NULL
ORDER BY t.created_at DESC LIMIT 100""",
    },
    "solved": {
        "name": "Dashboard – Solved Topics",
        "sql": """SELECT c.name AS category,
  COUNT(DISTINCT t.id) AS total_topics,
  COUNT(DISTINCT st.topic_id) AS solved_topics,
  ROUND(100.0 * COUNT(DISTINCT st.topic_id) / NULLIF(COUNT(DISTINCT t.id),0), 1) AS solve_rate_pct,
  ROUND(AVG(EXTRACT(EPOCH FROM ta.created_at - t.created_at)/3600), 1) AS avg_hours_to_solve
FROM topics t JOIN categories c ON c.id = t.category_id
LEFT JOIN discourse_solved_solved_topics st ON st.topic_id = t.id
LEFT JOIN discourse_solved_topic_answers ta ON ta.solved_topic_id = st.id
WHERE t.deleted_at IS NULL AND t.archetype = 'regular'
GROUP BY c.name ORDER BY total_topics DESC LIMIT 15""",
    },
    "contributors": {
        "name": "Dashboard – Top Contributors",
        "sql": """SELECT u.username, COUNT(DISTINCT p.id) AS reply_count,
  COUNT(DISTINCT p.topic_id) AS topics_participated
FROM posts p JOIN users u ON u.id = p.user_id
WHERE p.post_number > 1 AND p.post_type = 1 AND p.deleted_at IS NULL
  AND p.created_at > NOW() - INTERVAL '30 days' AND u.id > 0
GROUP BY u.username ORDER BY reply_count DESC LIMIT 10""",
    },
}


SESSION = requests.Session()
SESSION.headers.update({
    "Api-Key":      API_KEY,
    "Api-Username": API_USERNAME,
    "Content-Type": "application/json",
})


def api(path, method="GET", body=None):
    url  = f"{DISCOURSE_URL}{path}"
    resp = SESSION.request(method, url, json=body, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code} {method} {url}:\n{resp.text[:500]}")
    if not resp.text.strip():
        raise RuntimeError(f"Empty response for {method} {url}")
    try:
        return resp.json()
    except requests.exceptions.JSONDecodeError:
        raise RuntimeError(f"Non-JSON response for {method} {url}:\n{resp.text[:500]}")


def find_or_create_query(key):
    name = QUERIES[key]["name"]
    existing = api("/admin/plugins/explorer/queries")
    for q in existing.get("queries", []):
        if q["name"] == name:
            print(f"  Reusing query id={q['id']} '{name}'")
            return q["id"]
    result = api("/admin/plugins/explorer/queries", "POST",
                 {"query": {"name": name, "sql": QUERIES[key]["sql"]}})
    qid = (result.get("query") or result)["id"]
    print(f"  Created query id={qid} '{name}'")
    return qid


def run_query(qid):
    result  = api(f"/admin/plugins/explorer/queries/{qid}/run", "POST", {"limit": 200})
    payload = result.get("result", result)
    columns = payload.get("columns", [])
    rows    = payload.get("rows", [])
    return [dict(zip(columns, row)) for row in rows]


os.makedirs("data", exist_ok=True)

for key in QUERIES:
    print(f"[{key}]")
    qid  = find_or_create_query(key)
    rows = run_query(qid)
    out  = f"data/{key}.json"
    with open(out, "w") as f:
        json.dump(rows, f, indent=2, default=str)
    print(f"  Wrote {len(rows)} rows → {out}")

with open("data/meta.json", "w") as f:
    json.dump({
        "updated_at":    datetime.now(timezone.utc).isoformat(),
        "discourse_url": DISCOURSE_URL,
    }, f, indent=2)

print("Done.")