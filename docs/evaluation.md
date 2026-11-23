# Reproducible evaluation

Run the following from the backend directory. All inputs are committed. No database, account, or network is required.

    python research/evaluate.py

## Personal estimates

Four convenience-sampled public player histories are deduplicated and ordered by match time. The first 60% supplies warm-up history, the next 20% selects the prior weight, and the final 20% is held out. Each prediction uses only preceding games on the hero within 90 days. Outcomes already observed during validation and test may update later predictions. Roles are pooled because reliable position labels are unavailable.

The selected prior weight is **20**, chosen from 10, 20, 40 and 80 by mean per-player validation Brier. The production default remains 40 pending broader evidence. All priors here are neutral 50% because historical role-and-patch baselines are unavailable.

| Player | Test predictions | Neutral | Personal | Fixed 40 | Selected weight |
| --- | ---: | ---: | ---: | ---: | ---: |
| player-1 | 165 | 0.2500 | 0.3586 | 0.2491 | 0.2489 |
| player-2 | 98 | 0.2500 | 0.3314 | 0.2505 | 0.2518 |
| player-3 | 173 | 0.2500 | 0.3543 | 0.2483 | 0.2478 |
| player-4 | 177 | 0.2500 | 0.3393 | 0.2475 | 0.2467 |

Mean per-player held-out Brier is **0.2488** with the selected weight, **0.3459** for personal rate, and **0.2500** for neutral prediction.

Four players provide exploratory evidence only. These results evaluate a smoothing component. They do not establish the effectiveness of the full recommendation score or generalize to all ranks.

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
