# TokenGotchi

TokenGotchi is a Tamagotchi-style virtual pet that lives on your Claude Code token usage. Every time Claude Code burns tokens on your behalf, your little creature gets fed, gains experience, and evolves. Neglect your coding and it will grow restless — keep shipping and it will thrive.

## Prerequisites

- **Windows.** These instructions are Windows-first; no other platform is verified.
- **Python 3.10 or newer**, with `pip`.
- **Claude Code, already installed and used at least once.** TokenGotchi has no data source of its own — it reads Claude Code's own session files. If you've never run Claude Code, install and use it first, then come back here.

## Install

If you just want to play, grab `TokenGotchi.exe` from the
[Releases](https://github.com/mChewWW/TokenGotchi/releases) page and run it —
no Python needed. To run or modify the source, read on.

Clone the repo and set up a virtual environment:

```bash
git clone https://github.com/mChewWW/TokenGotchi.git
cd TokenGotchi
python -m venv venv
venv\Scripts\activate
```

Then install in editable mode:

```bash
pip install -e ".[dev]"
```

This registers the `tokengotchi` console command used below, and pulls in the test dependencies.

If you'd rather not do an editable install, `pip install -r requirements.txt` will install the same runtime dependencies from a flat file — but it does **not** register the `tokengotchi` command, since that only happens through `pyproject.toml`'s packaging metadata. If you go this route, run the game with `python -m tokengotchi.main` instead (see below).

## Running

```bash
tokengotchi
```

Or, if you installed from `requirements.txt` and skipped the editable install:

```bash
python -m tokengotchi.main
```

## First Launch / What to Expect

On first launch you'll see a one-time privacy notice. Click **Got it!** and your pet appears as an **egg**.

While it's an egg, the screen tells you what to do:

- **`USE CLAUDE CODE TO HATCH`** across the top — the egg is fed by your Claude Code usage, not by anything you click.
- **`HATCHING  x/5`** with a progress bar along the bottom, in place of the usual hunger meter. This is BITS earned toward hatching, and it's the number to watch.

You need **5 BITS** to hatch — roughly 2,500 Claude Code output tokens at the default earn rate, or about one short Claude Code exchange. Just leave the TokenGotchi window open and go use Claude Code normally; the bar fills on its own and the egg hatches into a **baby**.

The **FOOD** button is deliberately greyed out while your pet is an egg — eggs don't eat. It becomes available once your pet hatches.

**If the bar never moves**, this almost always means Claude Code hasn't produced any usage data yet, not that something is broken. Have a Claude Code session with the TokenGotchi window open and progress should start appearing. See Troubleshooting below if it still doesn't.

## Controls

| Control | Key | What it does |
| --- | --- | --- |
| **FOOD** | `F` | Opens the food menu. Spends BITS to refill hunger. Disabled while your pet is an egg, and while it's mid-bite. |
| **SHOP** | `S` | Opens the cosmetics shop — hats, screen skins, and cases. Hover an item to preview it on the real device before you buy. |
| The earn rate, top-right of the screen (`500T=1b >` at the default rate) | `R` | Opens the rates panel: your current earn rate, today's usage, and how your pet's appetite is trending. The number itself shifts as your usage does. |

## How it Works

TokenGotchi reads Claude Code's own session transcripts — the JSONL files Claude Code writes under `~/.claude/projects/**/*.jsonl` after every assistant response. These are read directly from your local filesystem; no network calls are ever made.

`~/.claude/stats-cache.json` (a file Claude Code writes only when a session ends) is **not** the live data source — it's consulted only as a compatibility check to confirm TokenGotchi understands the version of data Claude Code is producing.

TokenGotchi sums the token counts from those session files, converts them into in-game currency (BITS and ECHOES), and feeds that currency into the game engine. Your pet's hunger, stage, and wallet update accordingly. Spend currency in the in-game shop to unlock cosmetics for your creature.

**Privacy note:** TokenGotchi is entirely offline. It only reads local Claude Code session files from your own machine and never transmits any data anywhere.

## Troubleshooting

- **Your pet isn't earning anything / the `HATCHING` bar stays at 0/5:** TokenGotchi hasn't found any Claude Code session data yet. There's no explicit "no data found" message in the UI — a bar frozen at 0 is the only symptom you'll see. Confirm Claude Code is installed and that you've run at least one session while TokenGotchi is running, then relaunch TokenGotchi.
- **Nothing happens after a Claude Code update:** if Claude Code changes its internal session data format ahead of a version TokenGotchi understands, TokenGotchi detects this internally but (like the case above) does not currently show an on-screen error for it. Update TokenGotchi to the latest version; if the problem persists, please file an issue.

## Known Limitations

- No macOS/Linux instructions — only Windows behavior has been verified.
- The pre-built executable is published as a release asset, not committed to this repository.
- No demo/offline mode exists yet for trying TokenGotchi without a Claude Code account.
- No in-app error messaging yet for "no session data found" or "schema version mismatch" — both conditions are detected internally but not surfaced visually; see Troubleshooting above.

## License

MIT — see [LICENSE](LICENSE).
