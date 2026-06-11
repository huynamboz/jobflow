# Research — Calibrated Probability Display

## R1. Calibration fit method

**Decision**: sklearn `LogisticRegression(solver="lbfgs", C=1e6, max_iter=1000)`
on `X = scores.reshape(-1, 1)`, `y = (label >= 1)`. Extract `a = coef_[0][0]`,
`b = intercept_[0]` — identical `P = sigmoid(a·s + b)` form, `calibration.json`
schema unchanged (plus new `trained_with` key).

**Rationale**: the existing hand-rolled GD (lr=0.01, 1000 iters) measurably
does not converge — current artifact maps the whole observed score range
[0.25, 0.98] into P ∈ [0.37, 0.54] (span 0.17, useless). LBFGS on 1-D logistic
regression is the canonical Platt-scaling implementation (sklearn's own
`CalibratedClassifierCV(method="sigmoid")` does exactly this). `C=1e6`
effectively disables regularization, matching Platt's original unpenalized MLE.
sklearn is already a project dependency (trainer metrics) — no new deps.

**Alternatives considered**:
- *Isotonic regression*: nonparametric, fits arbitrary monotonic maps — better
  when calibration curve is non-sigmoid, but needs more data per region and
  produces flat (tie-creating) segments; ~1.8k val pairs is comfortable for
  Platt, marginal for isotonic. Sigmoid also guarantees STRICT monotonicity
  (FR-002) which isotonic does not. Rejected for now; revisit if the
  reliability table shows systematic sigmoid misfit.
- *Fixing the hand GD (more iters / better lr)*: reinventing sklearn with more
  failure modes. Rejected.
- *Temperature scaling on reranker logits*: requires reaching into the MLP's
  pre-softmax logits and would NOT include the penalty gates in the calibrated
  signal (FR-005 violation). Rejected.

## R2. Calibration signal

**Decision**: fit on `rank_score = reranker_expected_class_score × penalty_product`
computed for val-split pairs on the **training graph** (same engine context the
reranker was trained in), with penalties computed by the SAME
`_penalty_product` helper serving uses.

**Rationale**: since A3, rank_score is the ordering signal — calibrating any
other signal (current code uses stage-1) yields probabilities inconsistent with
the displayed ORDER. Gates must be inside the calibrated signal because they
multiply the served score; excluding them would systematically overestimate
gated pairs. The training graph (not the live pool) is required because val
pairs reference labeling-era job ids and the reranker's features must be
computed in the same context as training (the established A14 lesson).

**Caveat (documented, accepted)**: the resulting probability is conditional on
the v4 labeled-pair distribution (bucket-selected at the decision boundary).
Framing in docs/UI: "likelihood this pair would be labeled a match by our
ground truth", never a universal probability.

## R3. Version-coupling stamp

**Decision**: `calibration.json` gains `"trained_with": "<sha256(reranker.pt)[:16]>"`.
Engine at boot computes the same hash of the serving `reranker.pt` and WARNs on
mismatch (`_warn_if_calibration_stale`, mirroring `_warn_if_reranker_weights_stale`).

**Rationale**: the calibrator is a function of the reranker's score
distribution — the file hash is the most direct, dependency-free fingerprint of
that distribution's source. Hybrid-weights stamps (the A14 guard's choice) are
already covered by the reranker's own guard; chaining hash(reranker.pt) makes
the coupling transitive: weights→reranker (existing guard) → reranker→calibrator
(new guard).

**Alternatives**: copying `trained_with_weights` again (indirect — misses a
reranker retrain with same weights); timestamp (race-prone, meaningless after
file copies). Rejected.

## R4. Eligible threshold

**Decision**: `ELIGIBLE_MIN_PROB = 0.50` ("more likely a match than not"),
named constant in engine.py with rationale comment. Validated during rollout:
measure eligible-rate over the 4 employees' 400 persisted matches before/after;
if the rate swings drastically (>±25 percentage points), adjust the constant
once and record the final value here.

**Rationale**: with a calibrated probability, 0.5 is the only threshold that
needs no further justification. The old `0.65 × basket-top` was relative —
exactly the semantics this feature removes.

**Measured baseline**: rank_score over 400 persisted matches: min 0.250,
p10 0.386, p50 0.787, p90 0.940, max 0.982.

**Rollout measurement (T017, final)**: eligible-rate 76% (old relative) → 96%
(P≥0.50) — swing +20pp, within the ±25pp gate. KEPT at 0.50: the persisted
rows are the top-100 of 5,803 jobs, so a high eligible share is the honest
reading, and 0.50 retains its clean "more likely than not" semantics.

## R5. Order-invariance verification method

**Decision**: capture the engine-produced ranked `job_id` sequence per employee
(`rematch_employee` output order) BEFORE any change → `order_before.json` in
the spec dir; after implementation re-capture and diff. DB `-match_score`
ordering is NOT usable for this check because reranker saturation creates exact
score ties whose DB sort order is nondeterministic — the engine's own output
sequence is the ground truth (stable sort over deterministic inputs).

## R6. Fallback behavior without a usable calibrator

**Decision**: display raw rank_score + one warning log per engine lifetime
("calibration missing/unfitted — displaying raw rank score"). The remap path is
deleted, not kept as fallback (FR-003/FR-008): a silent fallback to remap would
resurrect the exact silent-degradation class the project spent 024 eliminating.
