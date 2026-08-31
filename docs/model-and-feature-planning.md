# MLB Model & Feature Planning

> Compiled by the **research-team** (lead synthesis of Researcher → Strategist → Critic).
> Scope: a +EV MLB betting system targeting three markets — **game outcomes (moneyline)**,
> **run totals (over/under)**, and **run-line spreads (±1.5)**. The system optimizes for
> **calibration and Closing Line Value (CLV)** — CLV is the gate metric; ROI is noise under
> ~2000 bets. Recency via EWMA (numerator/denominator weighted separately); calibration fit on
> a held-out *later* chronological slice.
> Date: 2026-06-30.

---

## 0. How this document was produced

Three Sonnet teammates ran a structured exchange:

1. **Researcher** — gathered candidate features and modeling approaches across 10 areas and sent
   findings to both Strategist and Critic.
2. **Strategist** — critically evaluated each feature/approach for *market-beating* value (not just
   predictive value), pruned redundancy, and sent the analysis to the Critic.
3. **Critic** — stress-tested both documents, flagged unsupported claims and architectural/operational
   gaps, and sent itemized critiques back to both.

This file is the lead's synthesis of that exchange. Sections marked **[OPEN]** are unresolved questions
that must be answered empirically before the corresponding feature/approach is trusted.

---

## 1. Guiding principle: predict the *market*, not just reality

The single most important framing from the exchange:

> The bar is the **closing line**, not the true outcome. A feature that genuinely predicts run scoring
> but is already fully priced into the market produces **zero CLV**. Value comes only from information
> that is *mispriced* — slow to be incorporated, hard to compute, or systematically misjudged by the market.

This reframes every feature decision below into one question: *does this give us something the closing
line does not already have?*

---

## 2. Architectural decisions (highest leverage, decided)

| # | Decision | Rationale | Status |
|---|----------|-----------|--------|
| A1 | **Market odds (Pinnacle no-vig prob) are NOT a model input.** They live only in the edge/CLV layer. | Using market prob as a feature creates a circular dependency: the model collapses toward the market and produces near-zero CLV *by construction*, and makes CLV measurement meaningless. | **Decided — reject unconditionally** (Strategist raised, Critic adjudicated) |
| A2 | **One unified run-distribution model serves all three markets.** Negative-Binomial (NB) run distribution is the primary; moneyline, totals, and run-line are all derived from the same per-team run distributions. | Over-dispersion in MLB run scoring breaks Poisson; a shared distribution keeps the three markets internally consistent and avoids three uncoordinated models. | **Decided** |
| A3 | **NB convolution must be done by Monte Carlo simulation, not analytically.** | The sum of two NB distributions is *not* NB in general; an analytical shortcut miscalibrates totals and run-line, which depend on the full joint/aggregate distribution. | **Decided** (Critic) |
| A4 | **GBT (gradient boosting) is an ensemble/regularization component, not the primary.** Bradley-Terry rejected as primary. | GBT alone loses the shared run-structure that ties the three markets together; Bradley-Terry discards the run distribution entirely. | **Decided** |
| A5 | **Calibration (isotonic/Platt) fit on a held-out *later* chronological slice**, never training data; strict point-in-time features. | Fitting calibration on training data made ECE worse historically; chronological 3-way split prevents leakage. | **Decided (pre-existing)** |
| A6 | **NB over-dispersion parameter α must vary by pitcher/matchup profile**, not be fixed. | A fixed α miscalibrates high- and low-variance games — exactly where totals and run-line edges live. | **Decided** (Critic) |

---

## 3. Feature catalog with verdicts

Legend: **KEEP** = retain in the candidate stack · **CUT** = redundant or already priced ·
**CONDITIONAL** = keep only if it earns CLV empirically · **[OPEN]** = unresolved question.

### 3.1 Starting pitcher quality
| Feature | Verdict | Reasoning |
|---|---|---|
| SIERA | **KEEP (primary)** | Best single ERA estimator; early-season **SIERA-vs-ERA** gap is a real mispricing window (market anchors on ERA). |
| Stuff+ / pitch-level stuff models | **KEEP** | Strongest edge for **newly-promoted / low-sample arms** where rate stats are noisy and the market is slow. |
| CSW% | **KEEP (one of)** | Stable, fast-stabilizing skill signal. Pick one of CSW%/SwStr% — they overlap. |
| FIP, xFIP | **CUT (redundant)** | Collinear with SIERA; SIERA dominates. Keep at most one as a sanity cross-check, not a model input. |
| SwStr% | **CONDITIONAL** | Redundant with CSW%; keep only the one that tests better. |

### 3.2 Bullpen
| Feature | Verdict | Reasoning |
|---|---|---|
| **Arm-level bullpen fatigue** (pitches/appearances over trailing days, back-to-backs, unavailability) | **KEEP (primary alpha)** | Computationally expensive, updates intraday, and the market is demonstrably slow on it — a top candidate alpha source. |
| Aggregate bullpen ERA/FIP | **CUT/CONDITIONAL** | Largely priced; value is in the *fatigue/availability* dimension, not season-level quality. |

### 3.3 Times-Through-Order (TTO) penalty
| Feature | Verdict | Reasoning |
|---|---|---|
| TTO penalty + projected starter length / opener usage | **KEEP** | Interacts with bullpen exposure; matters for totals and run-line. Must use *projected* (point-in-time) usage, not realized. |

### 3.4 Batting / offense
| Feature | Verdict | Reasoning |
|---|---|---|
| wRC+ (park/league adjusted) | **KEEP (primary)** | Best single offense summary. |
| xwOBA | **KEEP** | Adds the "deserved vs actual" mispricing angle on top of wRC+. |
| Platoon / vs-handedness splits | **KEEP** | Real, exploitable lineup-construction signal; shrink small samples. |
| wOBA, ISO, raw K%/BB% (as standalone offense inputs) | **CUT (redundant)** | Collinear with wRC+/xwOBA. Keep K%/BB% only where they feed the pitching/matchup side. |

### 3.5 Lineups, injuries, rest
| Feature | Verdict | Reasoning |
|---|---|---|
| **Injury-information speed** (who's out, before the market fully adjusts) | **KEEP (primary alpha)** | Edge is in *latency* — acting on confirmed scratches/IL before lines move. |
| Projected lineups (point-in-time) | **KEEP** | Required input; **[OPEN]** leakage risk (see §5). |
| Rest / day-after-night / getaway / B2B / travel | **CONDITIONAL** | Plausibly priced; keep behind a CLV test. |

### 3.6 Park & environment
| Feature | Verdict | Reasoning |
|---|---|---|
| Park factors (run, HR), altitude, roof state | **KEEP** | Stable, necessary as model context. Mostly priced *on its own*, so value is in **interactions** (weather × park). |

### 3.7 Weather
| Feature | Verdict | Reasoning |
|---|---|---|
| **Computed wind vector × park orientation** | **KEEP (primary alpha)** | The *computed interaction* (does wind blow out to the actual fences of *this* park?) is harder for the market than raw wind speed — a genuine edge candidate for totals/run-line. |
| Temperature, humidity | **KEEP** | Cheap, real effect on carry/run environment. |
| Raw wind speed (uncomputed) | **CUT** | Mostly priced; the orientation interaction is where the alpha is. |
| **Backtests must use pre-game *forecasts*, not observed actuals** | **RULE** | Using realized weather is leakage that inflates backtest CLV. (Critic) |

### 3.8 Umpire
| Feature | Verdict | Reasoning |
|---|---|---|
| Umpire run-environment / strike-zone tendency | **CONDITIONAL — challenged** | Researcher claimed it as alpha; Critic flagged it as *questionable* because UmpScorecards data is public and likely priced. Must earn its place via a feature-group CLV test. |

### 3.9 Defense / framing / baserunning
| Feature | Verdict | Reasoning |
|---|---|---|
| OAA/DRS, catcher framing | **CONDITIONAL** | Second-order; keep behind a CLV test, shrink heavily. |

### 3.10 Market / odds-derived
| Feature | Verdict | Reasoning |
|---|---|---|
| Pinnacle no-vig fair prob | **EDGE LAYER ONLY** | The CLV anchor and edge benchmark — *never* a model input (see A1). |
| Line movement / steam / open-vs-current gap | **CONDITIONAL — [OPEN], see §11** | Strategist: bet **filters only**, never model inputs. Researcher (revised): valid *candidate* inputs distinct from current fair prob (capture smart-money flow), gated by FDR feature selection. Critic adjudication: defensible **as an input only if** it survives a pre-specified, rigorous chronological-holdout FDR test — unlike current fair prob, it is not categorically circular. **Decision required before build.** |

---

## 4. Recommended stack per market

All three markets are derived from the **same NB run-distribution model** (A2), via Monte Carlo
convolution of the two teams' run distributions (A3).

- **Game outcome (moneyline):** P(home runs > away runs) from the simulated joint distribution.
  Core drivers: starter (SIERA/Stuff+), bullpen fatigue, offense (wRC+/xwOBA/platoon), park, weather.
- **Run totals (over/under):** distribution of *total* runs from the simulation. Most sensitive to
  **weather×park**, **bullpen fatigue/TTO**, and the **matchup-varying α** (A6).
- **Run-line (±1.5):** tail/margin probabilities from the same simulated margin distribution — no
  separate model. Benefits most from getting the *variance* (α) right, since run-line lives in the tails.

---

## 5. Data integrity & leakage rules (must pass before any CLV number is trusted)

1. **[OPEN — critical] Lineup/injury timestamp leakage.** Historical databases often record lineup and
   injury data at *game completion*, not at *public availability time*. If backtests use post-hoc
   timestamps, CLV is fictitious. **Validate availability timestamps before trusting any backtest.**
2. **Weather = forecast, not actual** in all backtests (§3.7).
3. **2023 pitch-clock regime break.** The rule change altered pace, bullpen usage, and run environment.
   Pre-2023 data must be handled carefully or excluded from baseline calibration.
4. Strict point-in-time EWMA features (row *t* excludes observations at *t*); shrink small samples
   (Bayesian / effective-sample-size).

---

## 6. Modeling & validation discipline

- **NB convolution → Monte Carlo** (A3); **matchup-varying α** (A6).
- **Multiple-comparisons correction** is mandatory in feature selection — currently absent. Without it,
  "alpha" from feature search is likely overfit.
- **GBT inclusion criterion must be pre-specified** before running the test (no post-hoc justification).
- **Alpha must be earned empirically** via **feature-group CLV tests**, not asserted. The six claimed
  primary alpha sources (bullpen fatigue, injury latency, wind×orientation, umpire env, early-season
  SIERA-vs-ERA, Stuff+ for promoted arms) are *hypotheses* until each clears a CLV test.

---

## 7. Operational layer (raised by Critic; currently unspecified — needs decisions)

| Item | Status / recommendation |
|---|---|
| **Kelly fraction** | **25% fractional Kelly — DECIDED**, fixed in build spec. |
| **De-vig method** | **DECIDED — one method per market type, locked across all backtests + production:** power/multiplicative for moneylines (additive understates favorite fair prob at extreme prices); additive acceptable for near-even totals (e.g. -115/-115). |
| **Book limits / execution realities** | **[OPEN]** — target books and expected limit ranges must be in the build spec *before* sizing math is finalized. |
| **CLV tracking spec** | **Closing line locked at T-5 min Pinnacle**; track CLV on **all evaluated games**, not just placed bets. **[OPEN]** — name the historical Pinnacle data source. |

---

## 8. Points of disagreement / adjudications

- **Market prob as feature:** Researcher implied usefulness as CLV anchor → Strategist rejected as input
  → Critic adjudicated **rejected as input, edge-layer only**. *Resolved.*
- **Umpire run-environment as alpha:** Researcher (alpha) vs Critic (likely priced via public
  UmpScorecards). *Unresolved → CLV test required.*
- **Document quality:** Critic judged the Strategist's pruned analysis the stronger of the two inputs,
  primarily for catching the market-prob circularity and the redundancy structure.

---

## 9. Open questions to resolve next (prioritized)

1. **Validate lineup/injury availability timestamps** (gates all backtest credibility). — §5.1
2. **Specify NB→runs Monte Carlo convolution** and the **α(matchup) model**. — A3, A6
3. **Stand up feature-group CLV tests** to empirically confirm/deny the six claimed alpha sources. — §6
4. **Decide de-vig method and Kelly fraction**; build the CLV-tracking spec (timestamp + data source + all-games). — §7
5. **Define the 2023 regime-break handling** for training/calibration windows. — §5.3
6. Add **multiple-comparisons correction** and a **pre-specified GBT inclusion criterion** to the modeling pipeline. — §6

---

## 10. Final consolidated build spec (post round-2)

After the Critic's critique, the Researcher accepted all corrections and the Strategist produced the
finalized spec below. This supersedes the earlier per-market sketch in §4 where they differ.

### 10.1 EWMA half-lives (point-in-time, num/denom weighted separately)
| Signal | Half-life |
|---|---|
| Bullpen fatigue | 5–7 games |
| Bullpen skill | 10–14 games |
| Team offense | 15–20 games |
| Starters | 20–30 games |

Pre-2023 data is excluded or given near-zero EWMA weight (pitch-clock regime break).

### 10.2 Moneyline stack
SIERA (xFIP for small-N) + Stuff+ (promoted arms) · team xwOBA vs starter handedness ·
bullpen usage-weighted xFIP + high-leverage arm fatigue · confirmed-lineup delta vs projected ·
park run factor + home flag · TTO penalty (expected IP → bullpen exposure) · injury flag (starter + top-4).

### 10.3 Totals stack
SIERA both sides + CSW% · team xwOBA platoon-adjusted (both) · park run factor (3-yr) + roof ·
computed wind head/tail × park orientation + temp <55°F · bullpen xFIP + fatigue (both) ·
TTO penalty · umpire EWMA run-environment (v1 collapsed; disaggregated retained for v2) ·
team defense OAA (both) · GB% × turf interaction · velo trend (fatigue/injury proxy).

### 10.4 Run-line
Derived directly from the NB joint run distribution — P(win by 2+). **No separate model.**

### 10.5 Features cut from v1 model input
FIP standalone · SwStr% (kept in pipeline, not a model input) · K%/BB%/K-BB% standalone ·
HR/9 standalone · raw pitch-shape metrics · wRC+ standalone · team K%/BB% standalone · park SO factor ·
raw park dimensions · temp >85°F flag · humidity · umpire home bias · umpire disaggregated K%/BB% (v1) ·
travel miles/time-zone · getaway day · days-since-off-day · team baserunning · **market odds as any model input.**

### 10.6 Other locked decisions
- NB convolution via **Monte Carlo**; **matchup-varying α** — `log(α)` as a function of starter K%, GB%, and opposing-lineup contact quality (not a global constant).
- **Independence** of home/away run distributions to be **tested first** (residual correlation after conditioning on all pre-game features); **Gaussian copula** with empirically-fitted rank correlation as fallback if material.
- **GBT** added only if it clears a **pre-specified Brier-score threshold**; regularization grid fixed before testing.
- All candidate features must clear **Benjamini-Hochberg FDR-corrected** selection at **FDR 0.10** against a chronological hold-out. Research "signal strength" labels are prioritization guides only, not guaranteed inclusion.
- **Pre-2023 data:** excluded from primary training / EWMA + fatigue calibration; permitted only as **Bayesian shrinkage priors** for stable career metrics (wOBA, SIERA, xwOBA).
- 25% fractional Kelly · de-vig per §7 · CLV on all evaluated games, closing line at **T-5 min Pinnacle** · backtest weather via **Open-Meteo historical forecast archive**.

---

## 11. Decision needed from you (the one unresolved item)

**Line-movement / steam / open-vs-current-gap as a model INPUT (not just a bet filter).**
- **Strategist:** filters only — never a model input.
- **Researcher (revised) + Critic:** defensible as an input *if and only if* it clears a pre-specified,
  rigorous FDR test on a chronological hold-out; it is distinct from current fair probability (which is
  rejected unconditionally) because it encodes information *flow*, not the price itself.
- **Lead recommendation:** allow it into the candidate pool **gated behind the pre-specified CLV/FDR test**,
  with an explicit correlation check against current fair prob; default to **filter-only** if it fails.
  Your call before build.

---

### Appendix: contributor summary
- **Researcher** — 10-section feature catalog + data-source cost table + feature-priority matrix.
- **Strategist** — redundancy pruning, market-prob circularity catch, unified-NB recommendation, six alpha hypotheses.
- **Critic** — convolution/α/regime-break/leakage/operational gaps, empirical-alpha discipline, adjudications.
