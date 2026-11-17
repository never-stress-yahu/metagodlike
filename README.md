<div align="center">

<img src="frontend/public/favicon.svg" width="76" height="76" alt="metagodlike icon" />

# metagodlike

**Explainable Dota 2 hero recommendations based on player history, role, rank, and draft matchups.**

![React](https://img.shields.io/badge/React-19-263445?logo=react&logoColor=61dafb)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-263445?logo=fastapi&logoColor=6bd3bb)
![SQLite](https://img.shields.io/badge/SQLite-local%20storage-263445?logo=sqlite&logoColor=9dd2ef)

[One-minute tour](#a-one-minute-tour) · [Screenshots](#screenshots) · [What you can do](#what-you-can-do) · [Quick start](#quick-start) · [How it works](#how-it-works) · [Configuration](#configuration) · [Publish to GitHub (RU)](docs/publish.md)

</div>

---

metagodlike helps Dota 2 players choose a hero for their role, decide which heroes to practice, and review the picks they could have made in a past match. Its recommendation engine turns public match statistics and each player's history into rankings with a visible score breakdown.

## A one-minute tour

**1. Filter the candidates.** Start with the player's role and skill bracket. Check that each hero has enough qualifying matches and label whether the data covers the current patch or comes from a historical source.

**2. Score the hero for the player.** Combine the hero's meta performance with the player's recent results on that role, how familiar they are with the hero, and how difficult the hero is to learn. Recent games carry more weight, and a small personal sample is pulled toward the meta baseline. For example, **4 weighted wins in 5 weighted games** and a **52% meta baseline** give a personal estimate of **55.1%** after adding the weight of 40 baseline games. That estimate contributes to the ranking. A separate **Worth learning** ranking looks for heroes that add useful skills to the player's pool.

**3. Score the pick for a specific draft.** Given a complete pick log, reconstruct which enemy heroes were visible at the player's turn. Remove unavailable heroes and rank up to three alternatives using meta, the player's experience before that match, and both favorable and unfavorable matchups. The interface shows how each factor contributed.

The **Logic** page documents the formulas in English and Russian. [General recommendation scoring](backend/main.py) · [Draft scoring](backend/draft_recommendations.py)

## Team

- **Abdolla Margulan** — Frontend
- **Kaldybekov Arnur** — Backend, scoring logic, and frontend

## Screenshots

| Overview | Recommendations |
| :---: | :---: |
| ![Overview with a win-rate chart and the most-played heroes](docs/screenshots/overview.jpg) | ![Hero recommendations with role and rank filters](docs/screenshots/recommendations.jpg) |
| **Match review** | **Logic** |
| ![Match lineups and the start of the draft order](docs/screenshots/match-details.jpg) | ![Logic with a table of contents and typeset formulas](docs/screenshots/logic.jpg) |

The Overview screenshot uses a demo display name. Recommendations shown in screenshots reflect the data available at capture time.

## What you can do

### Track your form by role

**Overview** shows total matches and win rate, recent KDA and GPM, a win-rate chart, and your most-played heroes. Each point on the chart is the win rate for its own group of up to 20 games. The chart uses up to 1,000 available matches.

**Recent Farming by Role** looks at the last 20 games and reports match count, last hits per match, and last hits per minute separately for Carry, Mid, and Offlane. Last hits per minute uses total last hits divided by total time for each role. Matches with missing position or farming data are excluded. In **Heroes**, you can search your pool and sort by games played or win rate.

### Review a match against your own baseline

Open any of the 20 recent matches to see the result, duration, both lineups, and your position when it is available. The comparison table shows your kills, deaths, assists, KDA, GPM, and XPM alongside your average from the other recent matches. Each metric shows how many games contributed to its baseline.

### Choose heroes for your next games or for practice

Select one of the five positions and use your own medal or an available rank override. The app checks the role and size of the available meta sample before ranking heroes. The two lists answer different questions.

| List | What goes into it |
| --- | --- |
| **Recommended for next games** | Meta win rate, your recent results on the hero in that position, familiarity, and hero complexity. Recent results use a 90-day window and give newer matches more weight. |
| **Worth learning** | Heroes with fewer than 20 recorded games that pass the meta checks and bring a useful skill, such as initiation or ally saves, or build on a skill from your current pool. |

Each list can show up to five heroes. **Why this hero** opens the reasons, and the card shows the meta win rate, sample size, and your games on that hero. The page labels the scope of the data so you can tell position-specific rates from all-position aggregates.

### Revisit what you knew at pick time

When a public draft log is complete, **Match Details** shows which enemy heroes had been revealed before your pick. In Ranked All Pick, opponents from the same simultaneous phase stay hidden until the phase ends. In Captains Mode, picks follow the recorded order and the page marks which team had last pick.

The app can show **up to three alternatives** for your position. It filters out unavailable heroes, measures their matchups against revealed opponents, and combines those matchups with meta and your experience before the match. The breakdown includes the worst matchup so you can see when a strong counter to one enemy comes with a weakness against another. The score expresses ranking preference in points.

### Inspect builds from start to late game

Open **Items** from a hero card to see the build examples available for that hero and role.

| Stage | What is shown |
| --- | --- |
| **Start** | Observed starting purchases up to 600 gold, arranged as inventory and backpack slots |
| **Mid · 35 min** | An inventory reconstructed from purchases, with components removed when they go into an upgrade |
| **Late · 50+ min** | A completed six-slot inventory from the end of a match lasting at least 50 minutes |

You can inspect individual prices and the total item cost for each available build. Net worth and last-hit targets at **10, 35, and 50 minutes** use the median of the available observations, with the sample size and role coverage shown alongside.

### Read the formulas

The **Logic** tab walks through the inputs, filters, equations, and outputs for each part of the app. It is available in English and Russian, with formulas typeset from LaTeX.

## Quick start

Use **Python 3.12** and **Node.js 24 with npm**. Run the following from the repository root in two terminals.

**Terminal 1 · FastAPI**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

<details>
<summary>macOS and Linux</summary>

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

</details>

**Terminal 2 · React app**

```sh
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

Open [metagodlike](http://127.0.0.1:5173/). In **Overview**, enter your Steam32 or Steam64 ID and select **Sync player**. Enable **Expose Public Match Data** in Dota 2 so the provider can read your matches. The app stores one active player per instance. Syncing another account replaces the active profile.

### Try the recommendation engine offline

With the backend environment installed, run this from `backend/`:

```sh
python demo_recommendations.py
```

The script prints two synthetic recommendation scenarios, **Carry** (`scenarios["1"]`) and **Soft Support** (`scenarios["4"]`). Compare `recommended_for_next_games` and `worth_learning` in each scenario, then look at a hero's `score_breakdown`. The script uses fictional match and patch data and runs without a Steam account or API credentials. [Demo source](backend/demo_recommendations.py)

### Troubleshooting

| What you see | What to check |
| --- | --- |
| The frontend cannot reach the API | Run Uvicorn from `backend/` and check the [local API docs](http://127.0.0.1:8000/docs). The default Vite proxy expects port 8000. |
| The sync has no match history | Check the Steam32 or Steam64 ID and enable **Expose Public Match Data** in Dota 2. |
| **Worth learning** is empty | The list can be empty when the selected role and rank lack usable meta or no eligible low-experience hero meets the score and capability checks. |

## How it works

```mermaid
flowchart LR
    Player["Steam account"] --> UI["React / Vite"]
    UI -->|"/api"| API["FastAPI"]
    API -->|Fetch public match data| Providers["OpenDota / optional STRATZ"]
    API <-->|Active player snapshot| SQLite[("SQLite")]
    Meta["Rank and position data"] --> API
    API -->|Stats, rankings, breakdowns| UI
```

OpenDota supplies the default public match data. FastAPI normalizes the Steam ID and deduplicates imported matches before saving the active-player snapshot in SQLite. From that snapshot the API builds the overview, role summaries, and personal match comparisons. Recommendation and item endpoints add the relevant hero, matchup, or purchase data before returning results to the React app.

### What depends on the source data

- **Current-patch meta.** Verified recommendations need a recent snapshot for the requested rank and position. Historical results can appear with a source label when verified data is unavailable. The snapshot format and freshness checks are documented in the [meta schema](backend/current_meta_schema.md).
- **Positions and drafts.** Position labels can be provider estimates. A match can have visible lineups while draft coaching is unavailable because the pick log is incomplete.
- **Items and benchmarks.** An example or benchmark can be missing when the provider has too few purchase logs, inventories, or timeline readings. The app labels when the sample includes other positions.

## Configuration

The default local setup works with public OpenDota data. Set optional backend variables in the shell that runs Uvicorn.

| Variable | Where | Purpose |
| --- | --- | --- |
| `OPENDOTA_API_KEY` | Backend | Optional key for OpenDota API requests |
| `STRATZ_TOKEN` | Backend | Optional STRATZ token for provider fallback and position data |
| `CURRENT_META_FILE` | Backend | Path to a verified rank and role snapshot. See the [snapshot schema](backend/current_meta_schema.md) |
| `DATABASE_URL` | Backend | SQLite database location. Defaults to `sqlite:///./dota_helper.db` |
| `FRONTEND_ORIGINS` | Backend | Comma-separated origins to allow for CORS. Defaults to the local Vite URLs |
| `VITE_API_BASE_URL` | Frontend | Alternate API base URL. Defaults to `/api` |

For a deployment with a reverse proxy, serve the Vite build with a fallback to `index.html` for frontend routes and proxy `/api` to FastAPI while stripping the prefix. The default app is designed for one active player per instance.

## Repository map

| Path | Contents |
| --- | --- |
| [`frontend/`](frontend/) | React views, styling, assets, and the bilingual Logic page |
| [`backend/`](backend/) | FastAPI, scoring, role policy, and SQLite persistence |
| [`backend/current_meta_schema.md`](backend/current_meta_schema.md) | Input format and checks for verified meta snapshots |
| [`docs/screenshots/`](docs/screenshots/) | Screenshots of the running UI |
| [`.github/workflows/ci.yml`](.github/workflows/ci.yml) | Frontend lint and build, plus backend tests |

## Verification

Run `npm run lint` and `npm run build` from `frontend/`. With the backend environment active, run `python -m pytest -q` from `backend/`. Backend tests use mocked providers and temporary SQLite databases. GitHub Actions runs these same checks on pushes and pull requests.

With both servers running, open the interactive [FastAPI docs](http://127.0.0.1:8000/docs).
