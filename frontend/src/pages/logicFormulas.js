// Shared notation keeps the two translations on the same formulas.
export const logicFormulas = {
    overview: [
        [
            String.raw`\mathrm{Matches} = W + L`,
            String.raw`\mathrm{WR} = 100 \cdot \frac{W}{W+L}\,\%`,
            String.raw`\mathrm{KDA}_{\mathrm{recent}} = \frac{\sum_i K_i + \sum_i A_i}{\max(1, \sum_i D_i)}`,
            String.raw`\bar{x} = \frac{1}{n}\sum_{i=1}^{n} x_i, \qquad x \in \{\mathrm{GPM}, \mathrm{XPM}\}`,
        ],
        [
            String.raw`\mathrm{WR}_g = 100 \cdot \frac{W_g}{n_g}\,\%`,
        ],
        [
            String.raw`\overline{\mathrm{LH}} = \frac{1}{n}\sum_{i=1}^{n} \mathrm{LH}_i`,
            String.raw`\mathrm{LH/min} = 60 \cdot \frac{\sum_i \mathrm{LH}_i}{\sum_i t_i}`,
        ],
        [
            String.raw`p = \frac{W}{n}, \qquad z = 1.96`,
            String.raw`\mathrm{Wilson} = 100 \cdot \frac{p + \frac{z^2}{2n} - z\sqrt{\frac{p(1-p)+\frac{z^2}{4n}}{n}}}{1 + \frac{z^2}{n}}`,
        ],
    ],
    meta: [
        null,
        null,
        null,
        [
            String.raw`s_r = \frac{n_r}{\sum_k n_k}, \qquad s_r \ge 0.10`,
        ],
    ],
    recommendations: [
        [
            String.raw`A = \operatorname{round}_2\!\left(50 + (\mathrm{WR}-50)\cdot \frac{n}{n+500}\right)`,
            String.raw`p = \frac{50 + (A-50)q}{100}`,
            String.raw`M = 100(p-0.5)`,
        ],
        [
            String.raw`w_i = 2^{-a_i/30}`,
            String.raw`G = \sum_i w_i, \qquad W = \sum_{i:\,\mathrm{win}} w_i`,
            String.raw`P = \frac{W+40p}{G+40}`,
            String.raw`U = 0.35 \cdot \min\!\bigl(0, 100(P_0-p)\bigr)`,
        ],
        [
            String.raw`V = \min\!\left(1,\frac{\ln(1+g)}{\ln(101)}\right)`,
            String.raw`F = 0.7V + 0.3\min\!\left(1,\frac{r}{10}\right)`,
            String.raw`C = 0.75(c-1)^2(1-V)`,
            String.raw`B = 0.75 \cdot \frac{G}{G_{\mathrm{role}}+20}`,
        ],
        [
            String.raw`\begin{aligned} R_{\mathrm{next}} &= M+100(P-p)+U \\ &\quad +1.5F+B-C \end{aligned}`,
        ],
        [
            String.raw`J_a = \frac{|T \cap T_a|}{|T \cup T_a|}, \qquad v_a = \ln(1+g_a)`,
            String.raw`S = \frac{\sum_a v_a J_a}{\sum_a v_a}`,
            String.raw`B_{\mathrm{learn}} = \min(1, 0.25 k_{\mathrm{new}})`,
            String.raw`R_{\mathrm{learn}} = M+1.5S+B_{\mathrm{learn}}-C`,
        ],
    ],
    match: [
        [
            String.raw`\mathrm{KDA} = \frac{K+A}{\max(1,D)}`,
            String.raw`\bar{x} = \operatorname{round}_2\!\left(\frac{1}{n}\sum_{i=1}^{n} x_i\right)`,
            String.raw`\Delta x = \operatorname{round}_2(x_{\mathrm{match}}) - \bar{x}`,
        ],
    ],
    draft: [
        null,
        null,
        [
            String.raw`E_e = \operatorname{round}_2\!\left(100 \cdot \frac{w_e - n_e/2}{n_e+50}\right)`,
            String.raw`M_{\mathrm{pairs}} = 2 \cdot \frac{\sum_e E_e}{N}`,
            String.raw`R_{\mathrm{risk}} = \min(0, E_1, E_2, \ldots)`,
        ],
        [
            String.raw`M_{\mathrm{meta}} = 2(\mathrm{WR}-50)\cdot \frac{n}{n+500}\cdot q`,
            String.raw`P_{\mathrm{draft}} = \operatorname{clip}_{[-3,\,3]}\!\left(60 \cdot \frac{w-g/2}{g+40}\right)`,
            String.raw`F_{\mathrm{draft}} = 2\min\!\left(1,\frac{\ln(1+g)}{\ln(101)}\right)`,
            String.raw`\begin{aligned} R_{\mathrm{draft}} &= M_{\mathrm{meta}} + M_{\mathrm{pairs}} + R_{\mathrm{risk}} \\ &\quad + P_{\mathrm{draft}} + F_{\mathrm{draft}} - C \end{aligned}`,
        ],
    ],
    items: [
        [
            String.raw`\mathrm{Gold}_{\mathrm{start}} = \sum_i p_i q_i`,
        ],
        null,
        [
            String.raw`\mathrm{Gold}_{\mathrm{mid/late}} = \sum_i p_i`,
        ],
    ],
    benchmarks: [
        [
            String.raw`t = 60m, \qquad m \in \{10,35,50\}`,
        ],
        [
            String.raw`\widehat{\mathrm{NW}}(t) = \operatorname{round}\!\left(\operatorname{median}_i \mathrm{NW}_i(t)\right)`,
            String.raw`\widehat{\mathrm{LH}}(t) = \operatorname{round}\!\left(\operatorname{median}_i \mathrm{LH}_i(t)\right)`,
        ],
    ],
};
