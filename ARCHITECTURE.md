# Arthur v1.8 · Technical architecture

## Authority and update flow

One Python Runtime owns the shared world. Its lock serializes mutations. A 20 Hz loop integrates measured elapsed time, caps suspension gaps at 250 ms and publishes detached snapshots. Rendering, polling and model latency do not determine movement speed.

Local rules handle needs, travel, finite gathering, storage and construction. Optional model calls provide contextual conversation, short reflections and constrained intentions. Local life continues when a key is absent, the service is slow, output is invalid or the request budget is exhausted.

| Module | Responsibility |
| --- | --- |
| `server.py` | Runtime, HTTP routes, permissions, actions, persistence and public/private snapshots |
| `mind.py` | Persona, values, memory retrieval, preferences, inspirations, facts and goals |
| `conversation.py` | Async jobs, message identities, retries, request limits and restart recovery |
| `ai_client.py` | Responses API, strict schema, output validation and connection status |
| `building.py` | Paid construction phases, finite resources, deposits and task selection |
| `world.py` | Terrain, landmarks, collision cells and the reserved house plot |
| `locomotion.py` | Continuous routes, rounded turns, acceleration and braking |
| `app.js`, `index.html`, `styles.css` | Conversation, outlook, controls, owner access, map and camera |
| `motion.js` | Interpolation, restart/sequence protection and 30 FPS pacing |
| `character.js`, `arthur_sprites.png` | Arthur’s appearance, planted feet, idle motion and creatures |
| `landscape.js` | Cached scenery, atmosphere, depth sorting and construction art |
| `settings.py`, `setup_ai.py` | Local configuration, hidden key entry and owner-code setup |
| `import_save.py` | Source-preserving SQLite backup into a clean folder |

## Durable state

SQLite stores world JSON in `kv`, alongside the public `journal` and legacy `memories` tables. State migrates to schema version 18 while retaining older unknown fields. Saves occur every 1.25 seconds, on accepted owner actions and on orderly shutdown.

`state.mind` stores identity, personality, evidence-backed preferences, up to 240 episodic memories, 64 diary entries, 24 inspirations and 32 private user facts. Retrieval weighs relevance, importance and recency. Migrated visits and world memories are labeled as prior experiences. Relevant memory retrieval and a recent conversation window of 20 messages provide selective continuity, not unlimited recall.

`state.house` records status, style, ordered paid/completed phases, current work, stockpile and spent materials. `state.resources` records node supply and harvesting cooldowns. Chat history retains 200 entries; up to 80 receipts support idempotent replay. Rolling-hour attempt timestamps survive restarts.

## Conversation lifecycle

1. An authorized `POST /api/chat` supplies a message and a stable `request_id`. Messages are limited to 2,000 characters.
2. A duplicate returns its original receipt. An explicit retry of a failed job preserves the user turn and starts a new attempt.
3. The user message becomes private evidence. A worker receives a deep copy of relevant context, never the live state.
4. A model call returns HTTP 202 immediately. The page reads completion or failure in normal snapshots. Local replies and exact stop/resume commands complete immediately.
5. The client rejects incomplete output, refusals, invalid JSON, unknown actions, out-of-range fields and invented evidence IDs. It uses the fixed OpenAI endpoint without following redirects.
6. Runtime applies bounded character expressions and separately validates the action. A command revision prevents late proposals overriding newer instructions. The displayed reply includes an action outcome.

The model has no filesystem, shell, database or arbitrary network tools. It cannot write positions or inventory. Allowed intentions are `none`, `go_to`, `start_house`, `pause_house`, `resume_house`, `design_house`, `stop` and `resume`. Destinations and styles are allowlisted. Only one action is executed per response.

Background reflection uses public context. It cannot override an explicit global pause, resume a paused project or interrupt a pending owner destination. Exploratory model suggestions do not replace an active house plan. The model may discuss ideas beyond the available mechanics, but only supported actions can execute.

## Construction loop

`choose_next()` derives a task from needs, current phase, stored stock and carried supplies. Runtime travels with its normal mover or performs a valid action in place. It does not invent another journey just to gather at the same patch.

`harvest()` requires stationary proximity, available stock and an expired cooldown. `deposit()` transfers existing supplies only when standing at the plot. `step_work()` requires Arthur physically at the plot, stationary, unpaused and sufficiently supplied. Each phase charges once and advances through an ordered payment/completion ledger.

Only committed events feed the journal and memory. A proposed model action is not recorded as a completed event. The renderer reads derived `state.construction` progress. The work point stays outside the blocked footprint, preserving collision-safe navigation before and after completion.

## Public viewing and private conversation

Loopback mode grants local owner access. Shared mode requires an owner code of at least 24 characters, checked with constant-time comparison. It travels in `X-Arthur-Owner`, never in a URL. Browser mutations are checked for same origin.

Spectator snapshots contain empty chat history, spectator status and `mind: null`. Request receipts and API attempt records are excluded from every browser snapshot. Chat reflections never become public speech or journal entries. Autonomous reflection excludes user messages, facts and expressions derived from private evidence.

The page clears private content and interpolation buffers on lock. Authentication revisions reject delayed previously authorized snapshots. This is one owner permission level, not multiple accounts. Host administrators and anyone with the owner code share owner access. The development HTTP server does not provide transport encryption.

## Extension points

For additional building types, add persistent project schemas, recipes and validators, then expose derived render projections. Keep material consumption and completed events inside the simulation rather than model-generated code.

For deeper long-term continuity, add summaries or semantic retrieval with explicit provenance and deletion controls. Preserve the distinction between an observed event, a user statement and an imagined idea.

For internet hosting, run the Python process on persistent storage, terminate HTTPS at a suitable proxy and add per-user authentication and request throttling. This project does not provision those services automatically.
