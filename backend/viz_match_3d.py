"""Highlight ONE CV + its real top-10 job matches in interactive 3D.

Runs the REAL matching pipeline (stage1 hybrid → reranker → Platt) against the
frozen checkpoint job pool (so every matched job aligns with a graph node), then
draws all jobs faintly, the chosen CV as a big star, and its top-10 matches as
big markers connected by lines labelled with the calibrated P(match).

    python viz_match_3d.py                  # auto-pick a backend CV
    python viz_match_3d.py --cv-index 12    # specific CV
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

import django
import numpy as np
import torch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("viz_match")


def build_engine():
    from django.conf import settings
    from ml_service.embedding import get_provider
    from ml_service.data.skill_normalization import SkillNormalizer
    from ml_service.inference.engine import InferenceEngine
    normalizer = SkillNormalizer(settings.ML_SKILL_ALIAS_PATH)
    provider = get_provider()
    # job_pool_dir → nonexistent path forces the FROZEN checkpoint pool (6251 jobs
    # that ARE graph nodes), so every matched job has a 3D position.
    return InferenceEngine.from_checkpoint(
        "checkpoints/latest", normalizer, provider, job_pool_dir="/tmp/__no_pool__")


def role_of(obj):
    return (getattr(obj, "role_category", None) or "other").lower()


def main(cv_index: int, out: Path, top_k: int, ctx_jobs: int) -> None:
    eng = build_engine()
    cvs, jobs, z = eng._cvs, eng._jobs, eng._z_dict
    log.info("Engine ready: %d cvs, %d jobs (frozen pool)", len(cvs), len(jobs))

    if cv_index < 0:
        cv_index = next((i for i, c in enumerate(cvs) if role_of(c) == "backend"), 0)
    cv = cvs[cv_index]
    log.info("Chosen CV#%s role=%s seniority=%s", getattr(cv, "cv_id", cv_index),
             role_of(cv), int(getattr(cv, "seniority", 0)))

    results = eng.match_cv(cv, top_k=top_k)
    id2idx = {j.job_id: i for i, j in enumerate(jobs)}
    top = []  # (job_idx, P, result)
    for r in results:
        ji = id2idx.get(r.job_id)
        if ji is not None:
            top.append((ji, r.score, r))
    log.info("Top-%d matches: %s", len(top), [f"{r.score:.2f}" for _, _, r in top])

    # Job positions MUST come from the engine's actual pool embeddings (aligned
    # with self._jobs / id2idx), NOT z["job"] — the live pool ≠ graph job order.
    z_job = eng._job_embeddings.detach().cpu().numpy()
    _, cv_gnn = eng.encode_cv(cv)
    cv_vec = cv_gnn.detach().cpu().numpy().reshape(-1)

    # skill nodes (for CV→skill→job paths): only skills SHARED between the CV and
    # at least one top job — the literal "why this job" bridge.
    z_skill = z["skill"].detach().cpu().numpy() if "skill" in z else None
    skill_names = sorted(eng._normalizer.skill_catalog.keys()) if z_skill is not None else []
    name2sk = {n: i for i, n in enumerate(skill_names)}
    cv_skills = set(getattr(cv, "skills", []) or [])
    shared_by_job = {}   # ji -> [skill_name, ...] present as skill nodes
    shared_names = set()
    for ji, _, _ in top:
        js = set(getattr(jobs[ji], "skills", []) or [])
        sh = [s for s in (cv_skills & js) if s in name2sk]
        shared_by_job[ji] = sh
        shared_names.update(sh)

    # context job sample (always include the top-k)
    rng = np.random.RandomState(42)
    top_set = {ji for ji, _, _ in top}
    pool = [i for i in range(len(jobs)) if i not in top_set]
    ctx = sorted(rng.choice(pool, size=min(ctx_jobs, len(pool)), replace=False).tolist())

    rows, kind = [], []
    # context jobs
    for ji in ctx:
        rows.append(z_job[ji]); kind.append(("ctx", ji, None))
    # top jobs
    for rank, (ji, P, r) in enumerate(top, 1):
        rows.append(z_job[ji]); kind.append(("top", ji, (rank, P, r)))
    # shared skill nodes
    for s in sorted(shared_names):
        rows.append(z_skill[name2sk[s]]); kind.append(("skill", name2sk[s], s))
    # the chosen CV (last) — use the engine's inductive encode for consistency
    rows.append(cv_vec); kind.append(("cv", cv_index, None))

    X = np.asarray(rows, dtype=np.float32)
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA
    from sklearn.manifold import TSNE
    Xs = StandardScaler().fit_transform(X)
    Xs = PCA(n_components=min(30, Xs.shape[1]), random_state=42).fit_transform(Xs)
    log.info("t-SNE on %d points...", Xs.shape[0])
    X3 = TSNE(n_components=3, init="pca", perplexity=min(30, max(5, Xs.shape[0] // 4)),
              random_state=42).fit_transform(Xs)

    cv_row = len(rows) - 1
    cvp = X3[cv_row]

    # --- traces ---
    traces = []
    # context jobs (faint grey)
    cx = [(X3[i, 0], X3[i, 1], X3[i, 2]) for i, k in enumerate(kind) if k[0] == "ctx"]
    ctitle = [f"job#{jobs[k[1]].job_id} · {role_of(jobs[k[1]])}" for k in kind if k[0] == "ctx"]
    traces.append({"type": "scatter3d", "mode": "markers", "name": f"jobs (context, {len(cx)})",
                   "x": [p[0] for p in cx], "y": [p[1] for p in cx], "z": [p[2] for p in cx],
                   "text": ctitle, "hoverinfo": "text",
                   "marker": {"size": 2.5, "color": "#475569", "opacity": 0.35}})

    # connector lines CV -> each top job
    lx, ly, lz = [], [], []
    for i, k in enumerate(kind):
        if k[0] == "top":
            lx += [float(cvp[0]), float(X3[i, 0]), None]
            ly += [float(cvp[1]), float(X3[i, 1]), None]
            lz += [float(cvp[2]), float(X3[i, 2]), None]
    traces.append({"type": "scatter3d", "mode": "lines", "name": "match links (direct)",
                   "x": lx, "y": ly, "z": lz, "hoverinfo": "skip", "visible": "legendonly",
                   "line": {"color": "#fbbf24", "width": 3}, "opacity": 0.55})

    # row lookups for CV→skill→job paths
    top_row = {k[1]: i for i, k in enumerate(kind) if k[0] == "top"}
    skill_row = {k[2]: i for i, k in enumerate(kind) if k[0] == "skill"}

    # CV → skill → job paths (the literal "why": shared skills bridge them)
    px, py, pz = [], [], []
    for ji, shs in shared_by_job.items():
        jr = top_row.get(ji)
        for s in shs:
            sr = skill_row.get(s)
            if jr is None or sr is None:
                continue
            # CV -> skill
            px += [float(cvp[0]), float(X3[sr, 0]), None]
            py += [float(cvp[1]), float(X3[sr, 1]), None]
            pz += [float(cvp[2]), float(X3[sr, 2]), None]
            # skill -> job
            px += [float(X3[sr, 0]), float(X3[jr, 0]), None]
            py += [float(X3[sr, 1]), float(X3[jr, 1]), None]
            pz += [float(X3[sr, 2]), float(X3[jr, 2]), None]
    traces.append({"type": "scatter3d", "mode": "lines",
                   "name": f"CV→skill→job paths ({len(shared_names)} skills)",
                   "x": px, "y": py, "z": pz, "hoverinfo": "skip",
                   "line": {"color": "#34d399", "width": 1.5}, "opacity": 0.4})

    # shared skill nodes (cross markers, labelled)
    sx = [float(X3[i, 0]) for i, k in enumerate(kind) if k[0] == "skill"]
    sy = [float(X3[i, 1]) for i, k in enumerate(kind) if k[0] == "skill"]
    sz = [float(X3[i, 2]) for i, k in enumerate(kind) if k[0] == "skill"]
    slbl = [k[2] for k in kind if k[0] == "skill"]
    traces.append({"type": "scatter3d", "mode": "markers+text", "name": f"shared skills ({len(slbl)})",
                   "x": sx, "y": sy, "z": sz, "text": slbl, "hoverinfo": "text",
                   "textfont": {"size": 8, "color": "#a7f3d0"}, "textposition": "middle right",
                   "marker": {"size": 4, "color": "#10b981", "symbol": "cross",
                               "line": {"color": "#064e3b", "width": 1}}})

    # top jobs (big, colored by RANK — P saturates near 1.0 so rank shows order)
    tx, ty, tz, ttxt, tcol, tlbl = [], [], [], [], [], []
    for i, k in enumerate(kind):
        if k[0] == "top":
            rank, P, r = k[2]
            tx.append(float(X3[i, 0])); ty.append(float(X3[i, 1])); tz.append(float(X3[i, 2]))
            tcol.append(rank)
            tlbl.append(f"#{rank}")
            elig = "✓ eligible" if r.eligible else "✗ below 0.50"
            ms = ", ".join(r.matched_skills[:6])
            ttxt.append(f"#{rank}  P={P:.0%}  [{r.match_level}] {elig}<br>"
                        f"{r.title[:60]}<br>role={role_of(jobs[k[1]])} · matched: {ms}")
    traces.append({"type": "scatter3d", "mode": "markers+text", "name": f"top-{len(top)} matches",
                   "x": tx, "y": ty, "z": tz, "text": ttxt, "hoverinfo": "text",
                   "texttemplate": "%{customdata}", "customdata": tlbl, "textposition": "bottom center",
                   "textfont": {"size": 9, "color": "#fde68a"},
                   "marker": {"size": 9, "color": tcol, "colorscale": "Viridis",
                               "cmin": 1, "cmax": len(top), "showscale": True,
                               "colorbar": {"title": "rank", "x": 1.02},
                               "line": {"color": "#000", "width": 1}}})

    # the chosen CV (big green star)
    traces.append({"type": "scatter3d", "mode": "markers+text", "name": "★ chosen CV",
                   "x": [float(cvp[0])], "y": [float(cvp[1])], "z": [float(cvp[2])],
                   "text": [f"★ CV#{getattr(cv,'cv_id',cv_index)} · {role_of(cv)} · sen={int(getattr(cv,'seniority',0))}"],
                   "textposition": "top center", "hoverinfo": "text",
                   "marker": {"size": 16, "color": "#22c55e", "symbol": "diamond",
                               "line": {"color": "#fff", "width": 2}}})

    scores_str = " · ".join(f"#{rk} {P:.0%}" for rk, (_, P, _) in enumerate(top, 1))
    title = (f"Matching 1 CV → top-{len(top)} jobs · CV#{getattr(cv,'cv_id',cv_index)} "
             f"({role_of(cv)}, sen={int(getattr(cv,'seniority',0))}) · {scores_str}")
    html = _HTML.replace("__DATA__", json.dumps(traces, default=float)).replace("__TITLE__", title)
    out.write_text(html)
    log.info("Wrote %s", out)


_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>CV Match 3D</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>body{margin:0;font-family:Inter,system-ui,sans-serif;background:#0b1020;color:#e5e7eb}
#h{padding:10px 16px;font-size:13px;border-bottom:1px solid #1f2937}
#p{width:100vw;height:calc(100vh - 44px)}</style></head>
<body><div id="h">__TITLE__ &nbsp;—&nbsp; ★=CV · điểm to=top job (màu theo P) · đường vàng=liên kết match · hover xem chi tiết</div>
<div id="p"></div><script>
var data = __DATA__;
var layout = {paper_bgcolor:'#0b1020', font:{color:'#e5e7eb'}, showlegend:true,
  legend:{itemsizing:'constant', font:{size:10}}, margin:{l:0,r:0,t:0,b:0},
  scene:{xaxis:{backgroundcolor:'#0b1020',gridcolor:'#1f2937',color:'#6b7280'},
         yaxis:{backgroundcolor:'#0b1020',gridcolor:'#1f2937',color:'#6b7280'},
         zaxis:{backgroundcolor:'#0b1020',gridcolor:'#1f2937',color:'#6b7280'}}};
Plotly.newPlot('p', data, layout, {responsive:true});
</script></body></html>"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cv-index", type=int, default=-1, help="-1 = auto-pick a backend CV")
    ap.add_argument("--out", default="/tmp/jobflow_match_3d.html")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--ctx-jobs", type=int, default=1500, help="grey context jobs")
    a = ap.parse_args()
    main(a.cv_index, Path(a.out), a.top_k, a.ctx_jobs)
