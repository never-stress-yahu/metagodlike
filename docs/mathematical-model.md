# Mathematical model and engineering decisions

The system ranks heroes using population evidence, personal history, and information visible during a draft. All win rates named v below use the 0–100 scale. Probabilities p and P use the 0–1 scale. Scores use ranking points. Coefficients are explicit design choices and have yet to be calibrated across players.

## 1. Establish which evidence is usable

The selected role and skill bracket determine candidate eligibility. Population samples need at least 200 games. Exact role data also requires a role share of at least 10%. Historical data retains its provenance and receives lower influence. Provider-reported positions define the personal role sample. Unknown positions are handled separately.

For the next-game ranking, evidence quality q starts at 1 for exact role data, 0.75 for the dated Dotabuff role sample, or 0.5 for an all-role aggregate. Staleness multiplies q by 0.75 and unverified patch coverage by 0.5.

$$
A=operatorname{round}_2left(50+(v-50)rac{n}{n+500}ight),qquad
p=rac{50+(A-50)q}{100},qquad M=100(p-0.5)
$$

The factor n/(n+500) limits how strongly a small sample can move the baseline. At n=500, the population deviation from 50% is halved before the quality adjustment.

## 2. Estimate personal performance with recency and shrinkage

For matches within 90 days on the selected hero and position, age a is measured in days and outcome y is 0 or 1.

$$
w_i=2^{-a_i/30},quad
G=sum_i w_i,quad W=sum_i w_i y_i,quad
P=rac{W+40p}{G+40}
$$

Equivalently, for G greater than zero,

$$
P=rac{G}{G+40}rac{W}{G}+rac{40}{G+40}p.
$$

This is a convex combination of recent personal performance and the population baseline. Forty is the prior weight. With no matching games P equals p. With growing evidence the personal rate receives more weight. With fractional recency weights this is a weighted shrinkage estimate.

Games with unknown position yield a separate estimate P₀ and can contribute a readiness penalty.

$$
U=0.35min(0,100(P_0-p)).
$$

### Sensitivity of these choices

Differentiation explains how these functions behave. These derivatives analyze the implemented scoring functions.

$$
rac{dw}{da}=-rac{ln 2}{30}w,qquad
rac{partial P}{partial p}=rac{40}{G+40}.
$$

Each extra day removes the same fraction of a game's remaining weight. At G=40, a one-percentage-point change in the baseline shifts P by half a percentage point. Generalizing the prior weight to λ and keeping the observed rate r fixed gives

$$
P_lambda=rac{Gr+lambda p}{G+lambda},qquad
rac{partial P_lambda}{partiallambda}
=rac{G(p-r)}{(G+lambda)^2}.
$$

Increasing the prior weight pulls the estimate toward the population rate. Its effect diminishes as λ grows. The application currently fixes λ at 40.

## 3. Convert experience into readiness

Let g be the larger of recorded and recent games on the hero, r the recent all-role game count, c the complexity category (1, 2, or 3), and G_role the weighted game count across heroes on the chosen role.

$$
V=minleft(1,rac{ln(1+g)}{ln(101)}ight),qquad
F=0.7V+0.3min(1,r/10)
$$

$$
C=0.75(c-1)^2(1-V),qquad
B=0.75rac{G}{G_{mathrm{role}}+20}.
$$

Logarithmic growth gives early experience more influence per game. Before saturation at g=100,

$$
rac{dV}{dg}=rac{1}{(1+g)ln(101)}.
$$

Complexity is quadratic in c−1. At zero experience, the penalties for Simple, Moderate, and Complex are 0, 0.75, and 3 points. Experience gradually removes that penalty. Unknown complexity contributes zero penalty.

The next-game ranking is

$$
R_{mathrm{next}}=M+100(P-p)+U+1.5F+B-C.
$$

A hero must have a nonnegative score and pass the Practice First filter. Complex heroes with fewer than five games require practice. Heroes with fewer than 20 games and at least three recent losses with zero wins on the selected or unknown role also require practice. Up to five qualifying heroes are returned.

## 4. Find useful heroes to learn

Reference heroes are up to five frequently played, role-compatible heroes with at least 20 games each. T and T_a are hero tag sets after removing the broad Carry and Support labels.

$$
J_a=rac{|Tcap T_a|}{|Tcup T_a|},qquad
S=rac{sum_a ln(1+g_a)J_a}{sum_aln(1+g_a)}
$$

$$
R_{mathrm{learn}}=M+1.5S+min(1,0.25k_{mathrm{new}})-C.
$$

Jaccard similarity measures skill overlap. The capability catalog identifies useful additions such as initiation or ally saves. With no usable reference pool S is zero. Candidates need fewer than 20 games, adjusted population rate A ≥ 50, nonnegative score, and a new or transferable capability.

## 5. Reconstruct the decision before scoring a draft

Captains Mode processes picks and bans in order. Ranked All Pick reveals opponents only after simultaneous phases finish, following the 2–2–1 structure. A complete, consistent ten-pick log is required. Picked and banned heroes are removed according to that visibility model.

Player experience includes only games preceding the reviewed match. Population and matchup statistics retain their actual collection scope. A retrospective ranking can use later aggregate statistics, as the demo does. Such a replay illustrates a decision using those statistics and does not establish what a historical live system would have predicted.

## 6. Score revealed matchups and the worst opponent

For enemy e, w_e is the candidate's wins and n_e is the pair's sample size. A pair needs at least 20 games. Coverage must include strictly more than half of the N visible enemies.

$$
E_e=operatorname{round}_2left(100rac{w_e-n_e/2}{n_e+50}ight),qquad
M_{mathrm{pairs}}=rac{2}{N}sum_e E_e,qquad
R_{mathrm{risk}}=min(0,E_1,ldots).
$$

Thirty-six wins in 60 games yields an edge of 5.45 points. Missing pairs contribute zero to the numerator while N still counts every visible enemy. Both matchup terms are zero when no enemies are visible.

The minimum term makes a single bad matchup matter even when the average is favorable. This is an explicit risk penalty. Pairwise observations cannot fully capture interactions between all ten heroes or isolate causal counterpick effects.

## 7. Combine the draft score

Here g and w count the player's pre-match games and wins on this hero across roles. The draft quality factor q_d is 1 for verified meta and 0.6 for historical meta.

$$
M_{mathrm{meta}}=2(v-50)rac{n}{n+500}q_d
$$

$$
P_{mathrm{draft}}=operatorname{clip}_{[-3,3]}
left(60rac{w-g/2}{g+40}ight),qquad
F_{mathrm{draft}}=2minleft(1,rac{ln(1+g)}{ln(101)}ight)
$$

$$
R_{mathrm{draft}}=M_{mathrm{meta}}+M_{mathrm{pairs}}+
R_{mathrm{risk}}+P_{mathrm{draft}}+F_{mathrm{draft}}-C.
$$

C uses the same complexity function with pre-match g. Scores are rounded to two decimals, then sorted by score, population sample size, and hero ID. Up to three heroes are returned. Negative totals remain eligible and indicate that penalties exceeded bonuses. The score orders candidates and has no calibrated mapping to win probability.

[Explore the real-match example](https://never-stress-yahu.github.io/metagodlike/) and inspect each contribution.

## 8. Evaluate what can be measured

The included chronological experiment evaluates recency-weighted personal estimates against observed outcomes using

$$
mathrm{Brier}=rac{1}{m}sum_{j=1}^{m}(P_j-y_j)^2.
$$

It uses only earlier matches when computing each personal prediction. On one 1,000-game snapshot, 874 matches had earlier experience on the selected hero within 90 days. Raw personal rate scored 0.3130, a constant 50% scored 0.2500, and smoothing toward 50% scored 0.2489.

The snapshot lacks role labels and historical population baselines. This experiment pools roles and uses a fixed neutral prior. The small improvement over that neutral baseline needs evaluation across more players. It does not evaluate the complete next-game or draft ranking. Outcomes for unpicked alternatives are unobserved.

The constants 30, 40, 50, 500 and ranking weights are engineering choices. Evaluating alternative settings should use separate chronological tuning and test periods to avoid selecting coefficients on the final evaluation sample.

## Implementation references

- [Next-game and learning scoring](../backend/main.py)
- [Draft ranking and score breakdown](../backend/draft_recommendations.py)
- [Complexity and role context](../backend/recommendation_context.py)
- [Chronological smoothing experiment](../backend/evaluate_smoothing.py)
- [Formulas displayed in the bilingual Logic tab](../frontend/src/pages/logicFormulas.js)
