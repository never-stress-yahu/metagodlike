export const logicStagesEn = [
    {
        id: "sync",
        title: "Sync and position detection",
        nav: "Data and positions",
        input: "Steam Account ID or SteamID64, player profile, match history, and hero catalog.",
        steps: [
            {
                title: "Fetch and clean match data",
                body: "OpenDota is the primary source for profiles and matches. If the OpenDota sync fails and STRATZ is configured, the server tries STRATZ. Matches with invalid IDs or unknown outcomes are discarded. The server deduplicates by match ID and sorts from newest to oldest. It keeps up to 1,000 matches for the chart and up to 20 recent matches for the list and match details. A successful sync saves the active player snapshot in SQLite.",
            },
            {
                title: "Identify the player's position",
                body: "Positions 1–5 are Carry, Mid, Offlane, Soft Support, and Hard Support. For match details and farming stats, the server checks the saved match position first, then OpenDota's position_est. The position stays unknown if both are missing. A provider-reported position may be an estimate.",
            },
        ],
        output: "The active player profile, avatar when available, rank, match history, and recent matches used by Overview, Heroes, Matches, and Recommendations.",
    },
    {
        id: "overview",
        title: "Profile, heroes, and farming",
        nav: "Profile and farming",
        input: "Total wins W and losses L, up to 1,000 matches, stats from the last 20 matches, and hero statistics. K, D, and A are kills, deaths, and assists. LH is last hits, GPM is gold per minute, and XPM is experience per minute.",
        steps: [
            {
                title: "Overview metrics",
                body: "Win Rate and Matches use the available total wins and losses. Recent KDA adds up kills, deaths, and assists across recent matches with all three values present. GPM and XPM are averages of the known recent values, rounded to the nearest integer. In the equations, i indexes eligible matches and n is their count for the metric being averaged.",
            },
            {
                title: "Win Rate chart",
                body: "The chart divides history into separate groups of 20 matches, counting back from the newest match. The oldest group may be smaller. Bars are shown in chronological order, and each bar uses the wins W and match count n for that group g.",
            },
            {
                title: "Recent Farming by Role",
                body: "The server looks at the last 20 matches and groups eligible games by Carry, Mid, and Offlane. A game needs a known position, last hit count, and positive duration t in seconds. Support games are skipped. In each role, i indexes games and n is their count. Longer matches carry more weight in the per-minute calculation through the total duration.",
            },
            {
                title: "Favorite Hero and Best Hero",
                body: "Favorite Hero is chosen by number of games, then wins. Best Hero uses the Wilson lower bound with z = 1.96, which gives less credit to high win rates from small samples. The server considers heroes with at least three matches first. If none qualify, it considers all played heroes. Ties are broken by win rate and then games. For both cards, the final tie-breaker is the lower hero ID. W and n are wins and games on the hero.",
            },
        ],
        output: "Overview metrics, win rate for each match group, farming averages for three core positions, and per-hero statistics.",
    },
    {
        id: "meta",
        title: "Meta data and position eligibility",
        nav: "Meta and roles",
        input: "The selected position, profile rank or rank override, hero catalog, meta source, and current-patch information.",
        steps: [
            {
                title: "Choose the rank and position",
                body: "A manually selected position takes priority. For automatic focus, the server finds the most-played hero in the last 20 matches and looks for their most frequently recorded position. If a position is unavailable, it can use position-specific meta or the hero's catalog position. Divine data can be used for Immortal with a rank fallback label.",
            },
            {
                title: "Verify the patch and sample dates",
                body: "A verified snapshot needs position-specific stats for the requested rank. For a configured meta file, both the snapshot and the verification of the current patch must be no more than 24 hours old. Its match window must start after the patch release, span up to 14 days, and end within the last three days. A source with a known patch mismatch is excluded from general recommendations.",
            },
            {
                title: "Distinguish the data sources",
                body: "Meta sources include a configured snapshot, STRATZ, and OpenDota's all-position aggregate. When verified meta is unavailable, the interface allows historical results. For Crusader, it can use the stored Dotabuff sample collected on November 17, 2026 for seven days after collection. That sample includes positions with at least 200 matches and at least 10% of the hero's picks across the five positions. A hero can qualify for more than one position.",
            },
            {
                title: "Filter heroes before scoring",
                body: "A hero needs at least 200 matches in the meta row and a valid win rate from 0 to 100. For exact role data, the share of games on the selected position must be at least 10%. Outside the Dotabuff sample, eligibility follows the position catalog, with a narrower list for all-position aggregates. Conditional roles require verified current-patch role data without a rank fallback. The interface labels verified and historical sources separately. In the equation, r is the selected position, k indexes all positions, and n is the match count on a position.",
            },
        ],
        output: "Eligible heroes with their meta win rates, sample sizes, and source and patch verification status.",
    },
    {
        id: "recommendations",
        title: "Recommendations for future games",
        nav: "Recommendations",
        input: "Eligible heroes, their meta win rates, player experience, recent position-specific results, hero complexity, and capabilities.",
        steps: [
            {
                title: "Start with the meta",
                body: "WR is the meta win rate on a 0–100 scale and n is the sample size. Smaller samples pull the adjusted rate A closer to 50%. The quality factor q starts at 1 for exact position data, 0.75 for the Dotabuff sample, or 0.5 for an all-position aggregate. It is multiplied by 0.75 for stale data and by 0.5 when current-patch coverage is unverified. The function round₂ rounds to two decimal places.",
            },
            {
                title: "Estimate personal performance on the position",
                body: "The server merges match records and keeps the last 90 days. Each match i is weighted using its age aᵢ in days, so its weight halves every 30 days. G and W are weighted games and wins on this hero and position, using positions reported by the provider. Games with an unknown position are estimated separately as P₀ using the same formula. They can add a readiness penalty U.",
            },
            {
                title: "Account for familiarity and complexity",
                body: "g is the larger of the recorded games and recent games on the hero. r is the number of games on this hero across all positions in the 90-day window. G_role is the total weighted games on the selected position across all heroes. Complexity c is 1 for Simple, 2 for Moderate, and 3 for Complex. Unknown complexity gives a zero penalty.",
            },
            {
                title: "For Next Games",
                body: "The score must be at least zero. The Practice First rule also applies. A Complex hero goes to practice when the player has fewer than five games on them. Any hero can go to practice when the player has fewer than 20 games on them and at least three recent games in the selected or unknown position with zero wins.",
            },
            {
                title: "Worth Learning",
                body: "The reference pool is up to five of the player's most-played heroes compatible with the position, each with at least 20 games. Jaccard similarity J compares hero tags, excluding Carry and Support. For each reference hero a, Tₐ is their tag set and gₐ is their game count. T is the candidate's tag set. Similarity S is zero if there are no comparisons. A curated capability catalog identifies transferable skills and counts useful capabilities k_new missing from the pool, such as ally saves or initiation. A hero qualifies with fewer than 20 games, A ≥ 50, a score of at least zero, and at least one new or transferable capability. The interface labels eligible historical results.",
            },
        ],
        output: "Up to five heroes per list, with reasons, sample sizes, and score contributions. Ties go to the larger meta sample, then the lower hero ID. A list can be shorter if fewer heroes pass the checks. P is a personal performance estimate adjusted for sample size.",
    },
    {
        id: "match",
        title: "Match results and deviations from baseline",
        nav: "Match results",
        input: "A selected match from the last 20 games, other games in the same list, and team lineups from OpenDota.",
        steps: [
            {
                title: "Calculate a personal baseline",
                body: "The selected match is excluded from the baseline. Each metric uses its own mean and sample size, since missing values are skipped separately for kills, deaths, assists, GPM, XPM, and KDA. Both the selected match value x_match and the baseline mean are rounded to two decimal places before computing the deviation.",
            },
            {
                title: "Build team lineups",
                body: "The server finds the player by account_id. Their slot determines whether they played for Radiant or Dire. The server groups heroes into allies and enemies, and displays the position from the saved match or the provider's estimate.",
            },
        ],
        output: "Match results, both lineups, position when available, and each metric's deviation from the recent baseline. If the baseline is missing, no deviation is shown.",
    },
    {
        id: "draft",
        title: "Draft phases and three alternative picks",
        nav: "Draft and counters",
        input: "Ten match participants, game mode, ordered picks_bans log, position, meta data, hero matchup stats, and games played before this match.",
        steps: [
            {
                title: "Reconstruct what was visible at the pick",
                body: "In Captains Mode, the server processes events in log order. A set of picks after bans starts a new phase. At each pick, earlier enemy picks are visible and picked or banned heroes are unavailable. The final pick determines which team had Last Pick. Ranked All Pick uses 2–2–1 picks per team, with opposing picks hidden until the phase ends. Both final heroes belong to the same phase. No enemy heroes are visible in phase one. Heroes in completed phases and all logged bans are excluded from the candidate pool.",
            },
            {
                title: "Check whether a draft can be scored",
                body: "A complete, ordered log with ten picks matching both lineups is required. The lineups can still display when an incomplete or inconsistent log prevents phase analysis. Use a manually selected role, the recorded match position, or the hero's catalog default when the match position is unknown.",
            },
            {
                title: "Score matchups and counterpick risk",
                body: "Each visible enemy e needs at least 20 matchup games and both heroes' population baselines from the same OpenDota matchup endpoint for the pair to count. p_h and p_e are the candidate and enemy aggregate win rates on a 0–1 scale. Their odds define the expected pair rate b_e. E_e measures deviation from this expectation, reducing the influence of general hero strength. Matchup data has no rank, role or patch filter. This is an observational adjustment with unmeasured confounding. wₑ is the candidate's wins and nₑ is the matchup sample size. When OpenDota reports the enemy's wins, the candidate's wins are the matchup games minus those wins. Matchup evidence must cover strictly more than half the revealed enemies. N is the total revealed enemies, including those without enough pair data. With an expected rate of 50%, 36 wins in 60 games gives a +5.45 edge. At a 58% expected rate, 53 wins in 100 games gives a negative edge. With no revealed enemies, matchup and risk contributions are both zero.",
            },
            {
                title: "Calculate the draft score",
                body: "Only available heroes eligible for the selected position with at least 200 meta matches are considered. Verified position data also requires at least a 10% role share. WR is the meta win rate, n is its sample size, and q is 1 for verified meta or 0.6 for historical data. g and w are the player's games and wins on the hero before the match, across all positions. Apply the same complexity penalty C as in general recommendations, using this value of g. The clip function limits the personal contribution to the stated range.",
            },
        ],
        output: "Enemies visible at pick time and up to three alternatives with a score breakdown. The ranking sorts by score rounded to two decimals, then by meta sample size and hero ID. A negative score means penalties outweighed bonuses. Draft picks can still place in the top three because there is no zero-point cutoff.",
    },
    {
        id: "items",
        title: "Items by game stage",
        nav: "Items",
        input: "Selected hero and position, public OpenDota matches with purchase logs or final inventories, and an item catalog with prices and recipes.",
        steps: [
            {
                title: "Starting Items",
                body: "The server requests up to six matches from a 14-day window. Purchases at or before second zero form a starting build if they cost more than 0 and at most 600 gold. Matches on the selected role take priority. Identical builds are grouped, and up to two of the most frequent are shown. If no builds are available, the interface lists up to eight popular individual items. In the formula, price pᵢ and quantity qᵢ are for each item type i.",
            },
            {
                title: "Mid Game · 35 minutes",
                body: "In games that reach 35 minutes, the server replays purchases made strictly before that mark. When an upgrade is purchased, its components are consumed, following nested recipes as needed. For example, an Ultimate Orb used for Eye of Skadi disappears from the build. The server keeps up to six of the most expensive finished items costing at least 450 gold. Boots of Speed, Blink Dagger, and Magic Stick also pass this filter. The reconstruction does not account for item sales.",
            },
            {
                title: "Late Game · final inventory from games lasting 50+ minutes",
                body: "A late-game build uses the six actual active slots at the end of a match that lasted at least 50 minutes, with all slots occupied by eligible finished items. For mid and late, the first suitable match on the chosen role takes priority, with a possible fallback to another role. The search can expand from 14 to 60 days if a build or the relevant net worth benchmark is missing. The cost sums the price pᵢ of the item in each displayed slot i.",
            },
            {
                title: "Lay out the inventory",
                body: "Starting items are ordered as Tango, Circlet, Boots, Branches, other items, and wards. Separate copies of branches and other non-stackable items occupy separate slots. Tango and wards stack. Three backpack slots follow the six active slots.",
            },
        ],
        output: "Starting builds, an example 35-minute inventory, and a six-slot example from the end of a long match. Individual prices and total cost are shown when a specific build is available.",
    },
    {
        id: "benchmarks",
        title: "Net worth and last hits at 10, 35, and 50 minutes",
        nav: "Time benchmarks",
        input: "The hero's time series networth_t and lh_t from matches sampled for the item inventory.",
        steps: [
            {
                title: "Select observations at each minute",
                body: "Matches are deduplicated by ID. For each minute m, a match must reach that minute and have an observation at the exact corresponding second t. Each metric uses games on the selected role if at least three observations are available. Otherwise, the sample includes all positions and is labeled as mixed.",
            },
            {
                title: "Calculate the typical value",
                body: "Net worth and last hits are calculated separately. The benchmark is the median at that minute across the eligible matches i. NW stands for net worth and LH for last hits. With an even number of games, the median is the mean of the two middle values. The result is rounded to the nearest integer. No benchmark is shown with fewer than three observations.",
            },
        ],
        output: "Typical net worth and last hits at each minute, alongside the sample size and position coverage. Each benchmark is the median of the available games on that hero.",
    },
];
