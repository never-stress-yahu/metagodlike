# Development record

This record summarizes decisions visible in the project's development conversation and implementation. The repository was imported after substantial local development, so its first commit contains earlier work. The examples below describe that process without assigning invented dates or individual code authorship.

## Contributions and tools

Arnur Kaldybekov directed the project and its Dota-specific requirements, reviewed recommendations, and identified concrete failures involving hero positions, complexity, draft visibility and item reconstruction. The project's recorded team roles assign him backend, logic and frontend responsibilities. Abdolla Margulan supplied the frontend work used as the starting point for integration.

Codex substantially assisted with backend and frontend implementation, debugging, tests, documentation, mathematical explanations, evaluation scripts and publication. Code ownership labels describe areas of responsibility. They do not establish that every implementation detail was written independently. A more detailed account of independently implemented components should be confirmed by the contributors before being asserted.

## Flexible positions

**Problem.** Restricting a hero to one familiar position excluded plausible candidates such as mid Necrophos.

**Decision.** Separate curated role policy from measured role evidence. A dated rank-specific role sample can permit a measured secondary role. All-position data carries an explicit label.

**Trade-off.** Role policies still need maintenance. A hero's observed role share in one rank or time window cannot automatically establish viability everywhere.

**Verification.** The backend test for the dated Dotabuff sample checks that observed flexible roles open without asserting verified patch coverage. Tests also keep unsupported fringe roles from entering through all-position aggregates.

## Visibility during the draft

**Problem.** A final lineup contains information that was unavailable when the player selected a hero.

**Decision.** Reconstruct Captains Mode in event order and Ranked All Pick in simultaneous 2–2–1 phases. Candidates and opponents are determined at the recorded decision point.

**Trade-off.** Incomplete logs allow a lineup view but prevent reliable phase analysis.

**Verification.** Tests check that simultaneous-phase opponents remain hidden and that unavailable heroes are excluded.

## Learning difficulty

**Problem.** Treating an unfamiliar Meepo like an unfamiliar Outworld Devourer ignored different learning demands.

**Decision.** Apply a complexity penalty that decreases with recorded experience, plus a practice filter for unready candidates.

**Trade-off.** The categories are coarse. Game count measures exposure rather than mastery, and the penalty weights require broader evaluation.

**Verification.** Tests compare OD and Meepo learning costs and verify that experience reduces the penalty.

## Inventory reconstruction

**Problem.** Purchase logs displayed finished items alongside their consumed ingredients.

**Decision.** Replay purchases and consume recipe components recursively before showing a stage inventory. Later-game examples use completed inventories from long games.

**Trade-off.** Purchase reconstruction does not track sales. Final inventories from games longer than 50 minutes are not exact minute-50 observations.

**Verification.** Tests cover recipe consumption and the completed six-slot requirement.

## Correcting the counterpick baseline

**Problem.** Comparing every pair with 50% could award a positive matchup score even when a strong hero performed below its ordinary expectation.

**Decision.** Estimate both heroes' overall strength from the same matchup source, derive an expected pair probability on the odds scale, and score the sample-adjusted residual. Preserve the old formulation for labeled ablations.

**Trade-off.** The source mixes conditions and the adjustment remains observational. Teammate synergy and higher-order composition effects remain outside this score.

**Verification.** A regression case with 53% observed wins and 58% expected wins receives a negative edge. Three frozen real drafts compare ranking changes on identical candidate sets.

## Testing the personal prior

**Problem.** The first experiment covered one player and depended on a local database.

**Decision.** Commit public inputs with collection metadata and hashes. Select the prior weight on a validation period and report held-out results separately for four players.

**Finding.** The selected weight improves the average relative to a neutral prediction, while one player performs worse. Keep the production default pending wider validation.

**Follow-up.** The expanded sample adds 16 public accounts across four seed-match rank bands. A new validation run selected the production prior weight of 40. The report shows the final scores for each player and records how the accounts were sampled.

[Read the reproducible evaluation](evaluation.md)

## What has yet to be established

Human usefulness ratings, prospective recommendation outcomes, broader rank coverage and reliable teammate-synergy scoring remain open work. The repository currently demonstrates a functioning, tested system and an exploratory evaluation of specific components.
