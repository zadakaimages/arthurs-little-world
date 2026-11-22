# Arthur's Little World: Railway deployment

## Reuse the existing resources

- GitHub repository: `zadakaimages/arthurs-little-world`, branch `main`.
- Railway project: `Arthur's Little World`.
- Production service: `arthur-world`.
- Persistent volume: `arthur-world-data`, mounted at `/data`.

Keep the source files at the repository root. Never commit `arthur.env`, `.env`
files, API keys, owner access codes, or SQLite saves. The Dockerfile starts
`python cloud_start.py`; no package installation or frontend build is needed.

## Required service settings

| Setting | Value |
| --- | --- |
| Source | `zadakaimages/arthurs-little-world`, `main` |
| Start command | `python cloud_start.py` |
| Healthcheck | `/healthz`, 60-second startup timeout |
| Replicas | Exactly 1 |
| Sleep application | Disabled |
| Volume mount | `/data` |
| `ARTHUR_DB` | `/data/arthur.sqlite3` |
| `PORT` | `8080` |
| `ARTHUR_OWNER_TOKEN` | Existing random secret, at least 24 characters |

Preserve an existing owner secret. Configure any new secret directly in Railway's
Variables screen. Do not put it in the repository, a URL, or a chat message.
Generate or reuse one Railway HTTPS domain, targeting port 8080.

## Owner access

Anyone can watch the world and its public activity journal. Open **Owner access**
on the website and enter the private code from Railway's `ARTHUR_OWNER_TOKEN`
variable to unlock conversations and controls. The code is stored only in that
browser tab's session storage. **Lock controls** removes it from the tab.

The server requires the code for every owner action and removes private memory,
conversation, and reflection fields from spectator API responses. Source files,
settings, and SQLite databases are not exposed by the web server. Use the HTTPS
domain when entering the code. Everyone holding the same code shares one owner
account; separate users are not implemented.

## Optional model conversation

Without `OPENAI_API_KEY`, the autonomous simulation, construction, creatures,
saved personality, and simple local replies work. To add open-ended model
conversation, set `OPENAI_API_KEY` and an `ARTHUR_MODEL` supported by the API
account in Railway Variables, then redeploy and verify with a real owner chat.
Optional settings are `ARTHUR_AI_AUTONOMY=1`, `ARTHUR_THINK_INTERVAL=180`, and
`ARTHUR_MAX_AI_CALLS_PER_HOUR=30`. The request limit is not a dollar budget.

## Verification and persistence

Wait for Railway deployment status `SUCCESS`, then confirm `/healthz` returns
HTTP 200 and `/api/state` has advancing `seq` and world time across two requests.
Anonymous owner actions must return HTTP 403. `/healthz` returns HTTP 503 if the
simulation thread stops or has not completed a tick for ten seconds.

World state autosaves to SQLite and is saved during a normal shutdown. Restarting
with the same `/data` volume must preserve world time, position, and progress.
Keep exactly one replica because this is one authoritative simulation with a
SQLite save. The world continues with no browser open while Railway runs the
service; it does not advance during host downtime.

The deployment package contains no previous SQLite save. A fresh empty volume
starts a new world. To move an older Arthur, stop the old host and this service,
keep backups of both saves, and transfer a consistent SQLite backup to
`/data/arthur.sqlite3` using authenticated volume tools. Do not put a personal save
in the public GitHub repository. Plan regular backups of the persistent volume.
