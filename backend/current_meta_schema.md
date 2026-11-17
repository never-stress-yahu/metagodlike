# Verified current-meta snapshot contract

Set `CURRENT_META_FILE` to the absolute path of your collector's JSON output. The file must match the bracket selected by the request. Fields below describe a schema, not a usable dataset; there is deliberately no synthetic live-meta file shipped.

```json
{
  "source": "collector and reproducible cohort source URL/name",
  "rank_bracket": "ARCHON",
  "position_data_exact": true,
  "patch": "current minor patch number from Valve",
  "patch_coverage_verified": true,
  "window_start": "ISO 8601 UTC timestamp",
  "window_end": "ISO 8601 UTC timestamp",
  "collected_at": "ISO 8601 UTC timestamp",
  "heroes": {
    "10": {
      "positions": {
        "1": {"matches": 1000, "wins": 550}
      }
    }
  }
}
```

Example counts are illustrative. Replace every timestamp and patch field with real evidence. Include the full five-position counts per hero when calculating role share; omitted positions must genuinely have zero games, not uncollected samples. Counts must be positive integers with wins between zero and matches; omit zero-count positions. The validator recomputes win rate from counts.

The collector must verify every underlying game belongs to the intended rank cohort, patch and window, deduplicate matches, distinguish role labels from lane/wealth guesses, and retain audit provenance outside the aggregate. The validator checks metadata consistency; it cannot independently prove a collector's boolean assertions. Do not mark position_data_exact or patch_coverage_verified true merely because a provider reports an aggregate or an inferred lane. A dedicated provider/collector integration with adequate target-rank role labels is still required.

High-MMR role audits with provider-inferred roles are research references. A verified Archon or Legend snapshot needs matches from the requested rank cohort.
