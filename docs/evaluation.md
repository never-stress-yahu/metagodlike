# Reproducible evaluation

Run the following from the backend directory. All inputs are committed. No database, account, or network is required.

    python research/evaluate.py

## Personal estimates

The frozen sample contains **20 distinct public player histories**. The original four accounts were selected by convenience. The additional accounts were drawn from distinct ranked All Pick matches in four average-rank bands. See the [sampling protocol and sources](../data/research/README.md).

For each account, matches are deduplicated and ordered by time. The first 60% supplies warm-up history, the next 20% selects the prior weight, and the final 20% is held out. Each prediction uses only preceding games on the same hero within 90 days, weighted with a 30-day half-life. Outcomes already observed during validation and test may update later predictions. Matches without earlier appearances on the same hero in that window are excluded. Roles are pooled because reliable position labels are unavailable.

The selected prior weight is **40**, chosen from 10, 20, 40 and 80 using **3,096 validation predictions**. The comparison gives each player equal weight by averaging their mean squared probability errors (Brier scores). Lower is better. The production default is 40. All priors here use 50% because historical role-and-patch baselines are unavailable.

| Prior weight | Validation Brier |
| --- | ---: |
| 10 | 0.250857 |
| 20 | 0.249697 |
| 40 | 0.249466 |
| 80 | 0.249569 |

| Player | Test predictions | Neutral | Personal | Selected weight |
| --- | ---: | ---: | ---: | ---: |
| player-1 | 165 | 0.2500 | 0.3586 | 0.2491 |
| player-2 | 98 | 0.2500 | 0.3314 | 0.2505 |
| player-3 | 173 | 0.2500 | 0.3543 | 0.2483 |
| player-4 | 177 | 0.2500 | 0.3393 | 0.2475 |
| player-5 | 65 | 0.2500 | 0.2497 | 0.2462 |
| player-6 | 151 | 0.2500 | 0.2841 | 0.2487 |
| player-7 | 103 | 0.2500 | 0.3547 | 0.2511 |
| player-8 | 145 | 0.2500 | 0.3338 | 0.2512 |
| player-9 | 95 | 0.2500 | 0.3988 | 0.2516 |
| player-10 | 143 | 0.2500 | 0.2552 | 0.2281 |
| player-11 | 167 | 0.2500 | 0.2616 | 0.2424 |
| player-12 | 174 | 0.2500 | 0.3815 | 0.2502 |
| player-13 | 171 | 0.2500 | 0.3073 | 0.2514 |
| player-14 | 186 | 0.2500 | 0.2761 | 0.2510 |
| player-15 | 182 | 0.2500 | 0.3276 | 0.2520 |
| player-16 | 176 | 0.2500 | 0.3122 | 0.2495 |
| player-17 | 140 | 0.2500 | 0.3115 | 0.2472 |
| player-18 | 197 | 0.2500 | 0.2510 | 0.2491 |
| player-19 | 174 | 0.2500 | 0.3246 | 0.2508 |
| player-20 | 198 | 0.2500 | 0.2766 | 0.2468 |

Across **3,080 held-out predictions**, mean per-player Brier is **0.248137** with weight 40, **0.314492** for the unsmoothed personal rate, and **0.250000** for a constant 50% estimate. The selected weight beats the neutral estimate for **11 of 20** players.

The expanded sample is exploratory. It favors active accounts with public match histories, some players can share matches, and the first four accounts' final segments were reported in the earlier experiment. The rank bands describe seed matches. The evaluation pools each account's public history and measures a component of the recommendation score using a neutral prior.

## Draft ranking ablation

Every variant ranks the same candidates that passed corrected-model evidence checks. Population uses meta alone. Personal adds experience, personal results and complexity. Full adds population-adjusted matchups and risk. Raw uses the previous 50% matchup baseline. All cases retain pre-match player history, while population statistics were collected later.

| Match | Candidates scored / eligible | Population top pick | Personal top pick | Full top pick | Previous model |
| --- | ---: | --- | --- | --- | --- |
| 9094461999 | 26 / 29 | Troll Warlord | Troll Warlord | Troll Warlord | Clinkz |
| 9094375739 | 15 / 29 | Sven | Sven | Wraith King | Wraith King |
| 9093259247 | 18 / 25 | Spectre | Clinkz | Spectre | Clinkz |

These comparisons measure ranking changes and evidence coverage. Winners of unplayed alternatives are unobserved, so they cannot measure counterfactual win-rate improvement.

## External review still needed

For a user study, prepare the same draft views with model labels hidden and output order randomized. Ask experienced players to rate role fit, counterpick reasoning, missing information, and usefulness before revealing the method. Record disagreements and failures as well as positive feedback. No human-review results have been collected.

Full validation scores, per-player counts, rankings and SHA-256 input hashes (UTF-8 with LF line endings) are in [results.json](../data/research/results.json). Source URLs and collection time are stored with the inputs. Public identifiers make these records pseudonymized, not anonymous.
