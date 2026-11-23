# Frozen evidence

These files support the offline evaluation and saved browser demo.

- personal-history.json contains 20 public OpenDota histories, collection times and source URLs. Each match record retains only match ID, hero ID, time and outcome.
- drafts.json contains three real draft states, earlier player experience, eligible candidates, population data, and complete matchup tables used for baseline calculation. Role labels are provider estimates.
- results.json records validation selection, held-out scores, input hashes and ranking comparisons.
- assets.json maps the demo's Valve hero-image URLs to cached paths and SHA-256 hashes.

Population and matchup statistics were collected after the historical matches. These inputs support retrospective comparisons and are unsuitable for claims about historical live prediction accuracy. The histories are a convenience sample, with overlapping matches possible between players. They do not represent an independent sample of all players or skill brackets.

The frozen results can be regenerated from the backend directory with Python 3.12 and the command shown in the [evaluation](../../docs/evaluation.md). The experiment itself uses the standard library. Input hashes use UTF-8 text with LF line endings.

## Player sampling

Players 1–4 retain the histories from the original convenience sample. The expansion adds four distinct accounts from each of four ranked All Pick seed-match bands, based on average match rank: Herald–Guardian, Crusader–Archon, Legend–Ancient, and Divine–Immortal. The collector reads OpenDota's public match listing, considers the newest returned seeds first within each page, and takes at most one account per seed. Among unexamined accounts in that match it takes the first by ascending account ID with at least 300 usable matches in its latest public history of up to 1,000 records. Selection uses history length and public availability; it does not use win rate or evaluation results.

The added histories are mixed-mode and pooled across positions. Seed-match rank describes where an account was found and may differ from the player's rank or the ranks in their earlier matches. This selection favors active accounts with public data.

For a fresh expansion, install the backend requirements and run `python research/expand_histories.py ORIGINAL_HISTORY OUTPUT_HISTORY` from `backend/`, using the four-account snapshot from `v1.0.0` as the original input. Public match listings and player histories change over time. Use the committed snapshot to reproduce the reported numbers. The original collector in `research/collect_evidence.py` takes a synced SQLite database and a destination directory and collects the initial accounts and draft cases.

Data comes from OpenDota. Hero imagery is supplied by Valve's Steam CDN and is cached solely for reliable demonstration. Source URLs are preserved in assets.json. Public identifiers mean the records are pseudonymized and can be linked back to public match data.
