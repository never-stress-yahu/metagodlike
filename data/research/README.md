# Frozen evidence

These files support the offline evaluation and saved browser demo.

- personal-history.json contains four public OpenDota histories, collection time and source URLs. Each record retains only match ID, hero ID, time and outcome.
- drafts.json contains three real draft states, earlier player experience, eligible candidates, population data, and complete matchup tables used for baseline calculation. Role labels are provider estimates.
- results.json records validation selection, held-out scores, input hashes and ranking comparisons.
- assets.json maps the demo's Valve hero-image URLs to cached paths and SHA-256 hashes.

Population and matchup statistics were collected after the historical matches. These inputs support retrospective comparisons and are unsuitable for claims about historical live prediction accuracy. The histories are a convenience sample, with overlapping matches possible between players. They do not represent an independent sample of all players or skill brackets.

The frozen results can be regenerated from the backend directory with Python 3.12 and the command shown in the [evaluation](../../docs/evaluation.md). The experiment itself uses the standard library. Input hashes use UTF-8 text with LF line endings.

For a new collection, install the backend requirements and run research/collect_evidence.py with the path to a synced SQLite database and a destination directory. This collector queries public APIs and writes a new snapshot. Preserve the committed snapshot when comparing versions.

Data comes from OpenDota. Hero imagery is supplied by Valve's Steam CDN and is cached solely for reliable demonstration. Source URLs are preserved in assets.json. Public identifiers mean the records are pseudonymized and can be linked back to public match data.
