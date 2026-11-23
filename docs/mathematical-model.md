# Mathematical model and engineering decisions

The system ranks heroes using population evidence, personal history, and information visible during a draft. All win rates named v below use the 0–100 scale. Probabilities p and P use the 0–1 scale. Scores use ranking points. Coefficients are explicit design choices and have yet to be calibrated across players.

## Mathematical foundations

The implementation uses exponential and logarithmic functions, weighted averages, statistical shrinkage, set similarity, and bounded scoring terms. The derivative and limit calculations below explain the behavior of these functions and the consequences of their parameter choices. The backend evaluates the scoring formulas directly.

The stages follow the flow from evidence to output, with each mathematical topic attached to the decision it supports.

## 1. Statistical shrinkage — establish a population baseline

The selected role and skill bracket determine candidate eligibility. Population samples need at least 200 games. Exact role data also requires a role share of at least 10%. Historical data retains its provenance and receives lower influence. Provider-reported positions define the personal role sample. Unknown positions are handled separately.

For the next-game ranking, evidence quality q starts at 1 for exact role data, 0.75 for the dated Dotabuff role sample, or 0.5 for an all-role aggregate. Staleness multiplies q by 0.75 and unverified patch coverage by 0.5.

$$
A=\mathrm{round}_2(50+(v-50)n/(n+500)),\quad p=(50+(A-50)q)/100,\quad M=100(p-0.5)
$$

The factor n/(n+500) limits how strongly a small sample can move the baseline. At n=500, the population deviation from 50% is halved before the quality adjustment.

## 2. Exponential decay and weighted averages — estimate personal performance

For matches within 90 days on the selected hero and position, age a is measured in days and outcome y is 0 or 1.

$$
w_i=2^{-a_i/30},\quad G=\sum_i w_i,\quad W=\sum_i w_i y_i,\quad P=\frac{W+40p}{G+40}
$$

Equivalently, for G greater than zero,

$$
P=\frac{G}{G+40}\frac{W}{G}+\frac{40}{G+40}p.
$$

This is a convex combination of recent personal performance and the population baseline. Forty is the prior weight. With no matching games P equals p. With growing evidence the personal rate receives more weight. With fractional recency weights this is a weighted shrinkage estimate.

Games with unknown position yield a separate estimate P₀ and can contribute a readiness penalty.

$$
U=0.35\min(0,100(P_0-p)).
$$

### Derivatives and partial derivatives — sensitivity to age and prior weight

Differentiation explains how these functions behave. These derivatives analyze the implemented scoring functions.

$$
\frac{dw}{da}=-\frac{\ln 2}{30}w,\qquad \frac{\partial P}{\partial p}=\frac{40}{G+40}.
$$

Each extra day removes the same fraction of a game's remaining weight. At G=40, a one-percentage-point change in the baseline shifts P by half a percentage point. Generalizing the prior weight to λ and keeping the observed rate r fixed gives

$$
P_\lambda=\frac{Gr+\lambda p}{G+\lambda},\qquad \frac{\partial P_\lambda}{\partial\lambda}=\frac{G(p-r)}{(G+\lambda)^2}.
$$

Increasing the prior weight pulls the estimate toward the population rate. Its effect diminishes as λ grows. The application currently fixes λ at 40.

### Limits — behavior as the evidence grows

Holding the observed personal rate r and baseline p fixed gives

$$
\lim_{G\to\infty}\frac{Gr+40p}{G+40}=r,\qquad
\lim_{G\to 0^+}\frac{Gr+40p}{G+40}=p.
$$

The same estimator moves continuously from population evidence toward personal evidence as the weighted sample grows. For the population adjustment,

$$
\lim_{n\to\infty}\frac{n}{n+500}=1.
$$

With a large sample, the sample-size adjustment approaches the observed population rate. The separate quality factor still controls how strongly that rate influences the baseline. At fixed outcome rate, rounding to two decimals introduces small steps in the implemented population adjustment.

## 3. Logarithmic diminishing returns — convert experience into readiness

Let g be the larger of recorded and recent games on the hero, r the recent all-role game count, c the complexity category (1, 2, or 3), and G_role the weighted game count across heroes on the chosen role.

$$
V=\min(1,\ln(1+g)/\ln(101)),\quad F=0.7V+0.3\min(1,r/10)
$$

$$
C=0.75(c-1)^2(1-V),\quad B=0.75G/(G_{\mathrm{role}}+20).
$$

Logarithmic growth gives early experience more influence per game. Before saturation at g=100,

$$
\frac{dV}{dg}=\frac{1}{(1+g)\ln(101)}.
$$

Complexity is quadratic in c−1. At zero experience, the penalties for Simple, Moderate, and Complex are 0, 0.75, and 3 points. Experience gradually removes that penalty. Unknown complexity contributes zero penalty.

The next-game ranking is

$$
R_{\mathrm{next}}=M+100(P-p)+U+1.5F+B-C.
$$

A hero must have a nonnegative score and pass the Practice First filter. Complex heroes with fewer than five games require practice. Heroes with fewer than 20 games and at least three recent losses with zero wins on the selected or unknown role also require practice. Up to five qualifying heroes are returned.

## 4. Set similarity — find useful heroes to learn

Reference heroes are up to five frequently played, role-compatible heroes with at least 20 games each. T and T_a are hero tag sets after removing the broad Carry and Support labels.

$$
J_a=\frac{|T\cap T_a|}{|T\cup T_a|},\qquad S=\frac{\sum_a\ln(1+g_a)J_a}{\sum_a\ln(1+g_a)}
$$

$$
R_{\mathrm{learn}}=M+1.5S+\min(1,0.25k_{\mathrm{new}})-C.
$$

Jaccard similarity measures skill overlap. The capability catalog identifies useful additions such as initiation or ally saves. With no usable reference pool S is zero. Candidates need fewer than 20 games, adjusted population rate A ≥ 50, nonnegative score, and a new or transferable capability.

## 5. Reconstruct the decision before scoring a draft

Captains Mode processes picks and bans in order. Ranked All Pick reveals opponents only after simultaneous phases finish, following the 2–2–1 structure. A complete, consistent ten-pick log is required. Picked and banned heroes are removed according to that visibility model.

Player experience includes only games preceding the reviewed match. Population and matchup statistics retain their actual collection scope. A retrospective ranking can use later aggregate statistics, as the demo does. Such a replay illustrates a decision using those statistics and does not establish what a historical live system would have predicted.

## 6. Shrinkage and a minimum penalty — score matchup risk

The candidate baseline p_h and opponent baseline p_e are aggregate win proportions computed from their complete matchup tables from the same OpenDota endpoint. Each underlying match contributes one row per opponent, so the summed table counts are repeated observations and are used only to estimate a proportion.

$$
b_e=\frac{p_h(1-p_e)}{p_h(1-p_e)+(1-p_h)p_e}.
$$

This is an independent hero-strength expectation on the odds scale. Equal baselines yield 50%. A 58% candidate facing a 50% opponent has an expected rate of 58%, making a 53% observed pair rate an unfavorable residual. Both baselines must be available. The endpoint has no rank, position or patch filter. Adjustment reduces general-strength confounding but cannot establish causal counterpick effects or control team composition and player selection.

For enemy e, w_e is the candidate's wins and n_e is the pair's sample size. A pair needs at least 20 games. Coverage must include strictly more than half of the N visible enemies.

$$
E_e=\mathrm{round}_2\left(100\frac{w_e-n_e b_e}{n_e+50}\right),\quad M_{\mathrm{pairs}}=\frac{2}{N}\sum_e E_e,\quad R_{\mathrm{risk}}=\min(0,E_1,\ldots).
$$

With an expected rate of 50%, thirty-six wins in 60 games yields an edge of 5.45 points. Missing pairs contribute zero to the numerator while N still counts every visible enemy. Both matchup terms are zero when no enemies are visible.

The minimum term makes a single bad matchup matter even when the average is favorable. This is an explicit risk penalty. Pairwise observations cannot fully capture interactions between all ten heroes or isolate causal counterpick effects.

## 7. Additive scoring and clipping — combine the draft score

Here g and w count the player's pre-match games and wins on this hero across roles. The draft quality factor q_d is 1 for verified meta and 0.6 for historical meta.

$$
M_{\mathrm{meta}}=2(v-50)\frac{n}{n+500}q_d
$$

$$
P_{\mathrm{draft}}=\mathrm{clip}_{[-3,3]}\left(60\frac{w-g/2}{g+40}\right),\quad F_{\mathrm{draft}}=2\min(1,\ln(1+g)/\ln(101))
$$

$$
R_{\mathrm{draft}}=M_{\mathrm{meta}}+M_{\mathrm{pairs}}+R_{\mathrm{risk}}+P_{\mathrm{draft}}+F_{\mathrm{draft}}-C.
$$

Clipping is a piecewise function. Below −3 the personal contribution stays at −3, between −3 and 3 it follows the calculated value, and above 3 it stays at 3. The experience cap and worst-matchup penalty likewise introduce boundaries where the slope changes. The logarithmic derivative in stage 3 applies before the experience cap is reached.

C uses the same complexity function with pre-match g. Scores are rounded to two decimals, then sorted by score, population sample size, and hero ID. Up to three heroes are returned. Negative totals remain eligible and indicate that penalties exceeded bonuses. The score orders candidates and has no calibrated mapping to win probability.

### How matchups changed the top pick

In saved match 9094375739, Sven scores 4.52 points from population performance and 8.96 points with the player's history included. Wraith King scores 3.44 and 4.98 points under the same two variants. The full model then includes matchups against the two visible opponents.

Against Anti-Mage, Wraith King won 17 of 25 games. The baseline from both heroes' population rates gives an expected win rate of about 50.86%. Substituting into the matchup formula gives

$$
E_{\mathrm{AntiMage}}\approx 100\frac{17-25(0.5086)}{25+50}\approx 5.71.
$$

Windranger adds an edge of 0.60. With two visible opponents, twice the average edge contributes 6.31 ranking points. Both edges are positive, so the worst-matchup penalty is zero. The full score is 11.29 points, placing Wraith King first. The saved example shows how opponent information changes the ordering. The result of playing a different hero in that match is unknown.

[Compare the scoring variants in the browser demo](https://never-stress-yahu.github.io/metagodlike/).

## 8. Mean squared error — evaluate observed outcomes

The included chronological experiment evaluates recency-weighted personal estimates against observed outcomes using

$$
\mathrm{Brier}=\frac{1}{m}\sum_{j=1}^{m}(P_j-y_j)^2.
$$

The frozen experiment uses 20 public histories with chronological 60/20/20 warm-up, validation, and test periods. The 3,096 validation predictions select a prior weight of 40 from 10, 20, 40, and 80. The selected value matches the production default. Across 3,080 held-out predictions, mean per-player Brier is 0.248137 with smoothing, 0.250000 for the constant 50% estimate, and 0.314492 for the raw personal win rate. Each player contributes equally to the mean.

The experiment pools roles and fixes the prior at 50% because historical role-and-patch baselines are unavailable. It evaluates smoothing. A separate comparison records how the full draft score changes rankings across three real drafts. Results for heroes not selected in a match remain unobserved. [Full protocol, results and reproduction command](evaluation.md)

The constants 30, 40, 50, 500 and ranking weights are engineering choices. Evaluating alternative settings should use separate chronological tuning and test periods to avoid selecting coefficients on the final evaluation sample.

## Implementation references

- [Next-game and learning scoring](../backend/main.py)
- [Draft ranking and score breakdown](../backend/draft_recommendations.py)
- [Complexity and role context](../backend/recommendation_context.py)
- [Chronological smoothing experiment](../backend/evaluate_smoothing.py)
- [Formulas displayed in the bilingual Logic tab](../frontend/src/pages/logicFormulas.js)
