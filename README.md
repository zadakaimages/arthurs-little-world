# Arthur’s Little World · v1.8

**A place of his own.** Arthur now has a saved personality, memories, preferences, inspirations and a house he can build through his own actions. His conversation can use an AI model to talk about his experiences and suggest things he wants to do.

This is a persistent simulated character. These systems create continuity and a sense of personality; they do not establish consciousness or human feelings.

## Cloud deployment

This repository includes the Railway deployment package. Use the existing
`Arthur's Little World` project and `arthur-world` service, with `main` from
`zadakaimages/arthurs-little-world` as the source. See [RAILWAY_DEPLOY.md](RAILWAY_DEPLOY.md).

The cloud entrypoint requires a private owner access code, stores the world in
`/data/arthur.sqlite3`, and runs independently of browser visitors. Keep the
existing persistent volume mounted at `/data`, one replica, and sleeping disabled.
The `/healthz` endpoint checks that the simulation thread is alive and ticking.
The website is public to watch; private conversations and controls require owner access.

Deployment regression checks use temporary saves and make no model API calls:

```bash
python -m unittest discover -s tests -v
```

## Start here

Run Arthur on a computer with **Python 3.10 or newer**. Your phone opens the game in a browser and does not need Python or Terminal. There are no Python packages to install and no JavaScript build step.

1. Extract the ZIP and open Terminal or PowerShell in the `arthur_world_v18` folder.
2. Import your previous save first if you want to keep your existing Arthur; see the next section.
3. For open-ended AI conversation, run setup, enter your own OpenAI API key when prompted, and start the server:

```bash
python3 setup_ai.py
python3 server.py
```

On Windows, use `python` instead of `python3` if that is your installed command. Setup asks for a model ID; press Enter for the default, `gpt-6.1-terra`, or enter a compatible model your API account can access.

Open **http://127.0.0.1:8765** on the host computer. Keep the computer awake and the server running. Press Ctrl+C to stop and save it. Do not open `index.html` directly; it needs the server.

You can also start with only `python3 server.py`. Without an API key, the world, memories, building, creatures and simple local conversation all work. The page labels those replies **Local reply**. Open-ended conversation becomes available after you configure a working model connection and restart the server.

The project contains no API key. No live model connection was available during development, so the integration was checked with controlled provider responses. The page distinguishes **configured but unverified**, a successful connection, and a failed request. A key being present or a reply being pending does not count as verification.

## Keep your existing Arthur

Stop the old server and keep its folder as a backup. From the new, freshly extracted folder, run:

```bash
python3 import_save.py "/full/path/to/old/arthur.sqlite3"
python3 server.py
```

On Windows, the source path might be `"C:\Users\YourName\Downloads\old_arthur\arthur.sqlite3"`.

The importer copies a consistent SQLite save, including committed write-ahead-log data. It preserves the source and refuses to overwrite a save already in the new folder. If you already started a fresh world there, extract another clean copy before importing.

Migration retains companions, nicknames, evolved forms, experience, inventory, coins, plans, journal and memories. Arthur’s new memory system imports saved visit history, earlier user chat and up to 80 recent legacy world memories. A position inside a new obstacle is moved to the nearest clear position connected to the shelter. Legacy decorations that intersect the new house footprint remain saved but are hidden beneath that plot.

The world saves about every 1.25 seconds, after owner actions and during normal shutdown. Stopping the host stops simulation time. Closing the browser does not stop the host.

## What gives Arthur continuity

Arthur has a stable starting personality: curious, gentle, cautious enough to look after himself, and interested in making useful things. His values, preferences, important memories and goals persist in the save.

- **Experiences have consequences.** Visiting a place can increase his interest in it and suggest a house feature. Finishing a construction stage strengthens his interest in making things. Fatigue can give him a reason to dislike rushing.
- **Preferences have reasons.** His outlook panel shows what he likes or avoids and the experiences behind those tendencies. Autonomous destination choices consider his public place preferences.
- **He remembers you.** Relevant conversation, a name you give him and preferences you share can appear in future conversation context. Memory is bounded; he will not retain every sentence forever.
- **He has inspirations.** A meadow can suggest flowers near the door; a hill can inspire a sturdy foundation. Model-generated preferences and inspirations must cite saved evidence before they are applied.
- **He has a continuing project.** His house goal follows actual construction progress. Generated descriptions cannot create supplies or declare an unfinished building complete.

The model receives his persona, relevant memories, recent conversation, needs, inventory, companions and actual house state. It returns a reply and, optionally, a constrained action proposal. The server checks that proposal before executing it. Short reflections are character expressions, not a display of the model’s private reasoning.

### Things to say

Try these after connecting AI conversation:

- “What have you been thinking about today?”
- “What kind of home would you like to build, and why?”
- “My name is E. I like quiet gardens.”
- “What do you remember about the places you’ve visited?”
- “What have you discovered that you dislike?”
- “Let’s choose the stone cottage design.”
- “Pause the house project.”
- “Go to the forest.”

The action interface accepts one executable intention per model response, so a request with several actions may need a follow-up. Local conversation supports direct controls and questions about saved state but cannot interpret every open-ended message.

“Stop” and “continue” use immediate local controls. **Pause Arthur** remains available while a model reply is pending. A delayed reply cannot overwrite a newer instruction. A separate action note explains whether a proposed action was accepted, unavailable or superseded.

## Building a home

Arthur begins with an aspiration to build a home. After eight seconds of orientation, local behavior starts the project automatically unless Arthur or the project is paused. The old cottage is his **shelter**; his new house has its own nearby plot and destination button.

He must gather at actual resource patches, travel with supplies, deposit them at the plot and stand there to work. Patches have finite supplies, a harvesting cooldown and gradual regrowth. His backpack holds 24 items; the house has separate storage.

| Stage | Materials consumed | On-site work |
| --- | --- | --- |
| Foundation | 2 wood, 6 stone | 9 seconds |
| Timber frame | 8 wood, 2 stone | 12 seconds |
| Roof | 6 wood, 2 flowers | 10 seconds |
| Finishing touches | 2 wood, 2 stone, 4 flowers | 8 seconds |
| **Total** | **18 wood, 10 stone, 6 flowers** | **39 seconds, plus gathering and journeys** |

The art changes from a marked plot to foundations, framing, a partial roof and a finished house. Materials are charged once per stage. Paid work, storage and progress survive restarts. Low energy and hunger can interrupt the project.

Choose **Woodland cabin**, **Stone cottage** or **Meadow cottage** before the first stage consumes materials. These are appearance choices with the same recipe in this prototype.

**Pause project** stops construction while Arthur can continue exploring. **Pause Arthur** stops his travel and work; wildlife and the clock continue. **Continue building** explicitly resumes the project and Arthur. **Store materials** works when he is standing at the plot with supplies; he also deposits automatically while pursuing the project. After completion, he can recharge at his own home and return to exploring and smaller crafting projects.

## Chat and watch from your phone

On the host computer, run:

```bash
python3 setup_ai.py --share
python3 server.py
```

This enables local-network access and prints a private owner access code. Existing API configuration is retained if you press Enter at the key prompt. To configure sharing without API prompts, use `python3 setup_ai.py --share --skip-ai`.

Connect your phone to the same network and open `http://YOUR-COMPUTERS-LOCAL-IP:8765`, replacing the placeholder with the computer’s real local IP address. The host firewall must allow the server on that private network. The host’s loopback address, `127.0.0.1`, will not work from the phone.

Open **Owner access** and enter the code printed by setup. You can then chat, direct Arthur, buy resources and manage the house. The browser keeps the code in the current tab’s session storage. **Lock controls** clears private panels and removes that saved code.

Other viewers can watch the shared world, creatures, house and public journal. They cannot control Arthur or read owner conversations, private memories or personal reflections without the owner code. The API key stays on the host and never appears in the browser.

| Server mode | Owner controls |
| --- | --- |
| Default loopback host, `127.0.0.1` | Available on the host computer |
| Shared host, `0.0.0.0`, without a valid owner code | Spectator view |
| Shared host with the valid owner code | Private conversation and owner controls |

This server is for a trusted local network or development. It does not publish a website or configure encrypted public hosting. Internet deployment needs HTTPS, persistent storage and suitable authentication around the server. Anyone with the owner code shares the same owner conversation; separate user accounts are not implemented.

## Model connection and settings

Setup writes a private `arthur.env` file. Do not include it when sharing the project. Your save also contains private conversation. The static server serves neither settings, Python source nor database files.

Model requests send relevant saved context and your messages to OpenAI. API usage is charged to your API account. This is not automatically connected to your ChatGPT conversation or subscription. The client uses `store: false`; that setting does not promise zero provider retention.

| Setting | Default | Meaning |
| --- | --- | --- |
| `OPENAI_API_KEY` | Unset | Key used only by the host |
| `ARTHUR_MODEL` | `gpt-6.1-terra` | Compatible Responses API model |
| `ARTHUR_AI_AUTONOMY` | `1` | Occasional model reflections; `0` retains model chat and local autonomy |
| `ARTHUR_THINK_INTERVAL` | `180` | Seconds between model reflections, after an initial delay |
| `ARTHUR_MAX_AI_CALLS_PER_HOUR` | `40` | Combined rolling-hour limit for chat and reflections |
| `ARTHUR_HOST` | `127.0.0.1` | Listen locally or on the network |
| `ARTHUR_PORT` | `8765` | HTTP port |
| `ARTHUR_DB` | Game folder’s `arthur.sqlite3` | Save path |
| `ARTHUR_OWNER_TOKEN` | Unset | Private access code for shared mode |

Restart after changing settings. Environment variables override `arthur.env`. The request limit survives restarts and counts failed attempts too. It is a **request limit, not a dollar budget**. Each call caps output at 2,400 tokens. Usage cost depends on the model and input/output sizes. Local control commands do not use model calls.

If a request fails, the world continues and conversation shows a retry option. Retries reuse the message identity to avoid duplicate turns or repeated actions. A reply interrupted by a server restart is marked retryable. If a key still fails, check the displayed error, model access and API-account configuration on the host.

Official implementation references: [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create), [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses), and [default model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-terra).

## Architecture and verification

See `ARCHITECTURE.md` for state flow and extension points. Movement retains the 20 Hz server simulation, continuous coordinates, collision-aware routes and distance-driven feet. The browser targets 30 FPS and interpolates shared snapshots.

Run the automated checks from this folder:

```bash
python3 -m unittest discover -s tests -v
```

Optional JavaScript checks require Node.js 18 or newer; Node is not required to play:

```bash
node --test tests/test_client.mjs tests/test_gait.mjs
```

The release passed **76 Python tests and 14 JavaScript tests** covering actual autonomous construction, material conservation, persistence, movement, model validation, retry/idempotency, privacy, owner access and command priority. A separate native Canvas/DOM-shim check exercised the interface, async chat, construction controls, locking and mobile-sized canvas rendering. Construction stages were rendered and visually inspected.

No live API call, full browser CSS/layout check or physical iPhone performance test was performed. **30 FPS is a target**; performance depends on the device and browser. This is a layered 2D prototype with one house plot, three predefined house appearances, bounded conversation actions and original rule-driven creatures. Additional rooms, arbitrary furniture, separate visitor accounts and public deployment are future extensions.
