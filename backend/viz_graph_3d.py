"""Visualize ALL HeteroGraphSAGE node embeddings in interactive 3D.

Loads checkpoints/latest, encodes every node (cv / job / skill / seniority) to its
256-dim GNN embedding, reduces to 3D (PCA -> t-SNE), and writes a self-contained
HTML using Plotly.js (CDN) — rotate / zoom / hover / toggle traces in the browser.

    python viz_graph_3d.py            # default checkpoints/latest -> /tmp/jobflow_graph_3d.html
    python viz_graph_3d.py --method pca   # faster, deterministic
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import torch

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("viz")


def main(ckpt: str, out: Path, method: str, max_jobs: int) -> None:
    from ml_service.inference.checkpoint import load_checkpoint
    from ml_service.models.gnn import prepare_data_for_gnn
    from ml_service.training.trainer import _strip_label_edges

    log.info("Loading checkpoint %s ...", ckpt)
    model, data, cvs, jobs, meta = load_checkpoint(ckpt)
    model.eval()

    # capture structural edges from the RAW hetero graph (before prepare flattens it)
    raw_edges = {}
    for et in [("cv", "has_skill", "skill"), ("job", "requires_skill", "skill")]:
        if et in data.edge_types:
            raw_edges[et] = data[et].edge_index.cpu().numpy()

    enc = prepare_data_for_gnn(_strip_label_edges(data))
    with torch.no_grad():
        z_dict = model.encode(enc)  # {ntype: (N, 256)}

    # --- collect embeddings + metadata per node ---
    embs, ntypes, roles, labels = [], [], [], []

    def role_of(obj):
        return (getattr(obj, "role_category", None) or "other").lower()

    z_cv = z_dict["cv"].cpu().numpy()
    for i, cv in enumerate(cvs):
        embs.append(z_cv[i]); ntypes.append("cv"); roles.append(role_of(cv))
        labels.append(f"CV#{getattr(cv,'cv_id',i)} · {role_of(cv)} · sen={int(getattr(cv,'seniority',0))}")

    z_job = z_dict["job"].cpu().numpy()
    job_idx = list(range(len(jobs)))
    if max_jobs and len(jobs) > max_jobs:
        rng = np.random.RandomState(42)
        job_idx = sorted(rng.choice(len(jobs), size=max_jobs, replace=False).tolist())
        log.info("Sampling %d / %d jobs for readability", max_jobs, len(jobs))
    for i in job_idx:
        job = jobs[i]
        embs.append(z_job[i]); ntypes.append("job"); roles.append(role_of(job))
        title = (getattr(job, "text", "") or "")[:50].replace("\n", " ")
        labels.append(f"JOB#{getattr(job,'job_id',i)} · {role_of(job)} · {title}")

    if "skill" in z_dict:
        z_sk = z_dict["skill"].cpu().numpy()
        for i in range(z_sk.shape[0]):
            embs.append(z_sk[i]); ntypes.append("skill"); roles.append("skill")
            labels.append(f"SKILL #{i}")

    if "seniority" in z_dict:
        z_sen = z_dict["seniority"].cpu().numpy()
        names = ["INTERN", "JUNIOR", "MID", "SENIOR", "LEAD", "MANAGER"]
        for i in range(z_sen.shape[0]):
            embs.append(z_sen[i]); ntypes.append("seniority"); roles.append("seniority")
            labels.append(f"SENIORITY {names[i] if i < len(names) else i}")

    X = np.asarray(embs, dtype=np.float32)
    log.info("Encoded %d nodes (cv=%d job=%d skill+sen=%d), dim=%d",
             X.shape[0], len(cvs), len(job_idx), X.shape[0]-len(cvs)-len(job_idx), X.shape[1])

    # --- reduce to 3D ---
    from sklearn.preprocessing import StandardScaler
    Xs = StandardScaler().fit_transform(X)
    if method == "tsne":
        from sklearn.decomposition import PCA
        from sklearn.manifold import TSNE
        Xs = PCA(n_components=min(30, Xs.shape[1]), random_state=42).fit_transform(Xs)
        log.info("Running t-SNE on %d nodes (this takes ~1-2 min)...", Xs.shape[0])
        X3 = TSNE(n_components=3, init="pca", perplexity=30, random_state=42).fit_transform(Xs)
    else:
        from sklearn.decomposition import PCA
        X3 = PCA(n_components=3, random_state=42).fit_transform(Xs)
    log.info("Reduced to 3D via %s", method)

    # --- build edge traces (faint lines): cv/job -> skill ---
    n_cv = len(cvs)
    job_row = {orig: n_cv + pos for pos, orig in enumerate(job_idx)}   # sampled jobs only
    skill_base = n_cv + len(job_idx)
    n_skill = z_dict["skill"].shape[0] if "skill" in z_dict else 0

    def edge_trace(et, src_rows_fn, color, name, cap=6000):
        ei = raw_edges.get(et)
        if ei is None:
            return None
        pairs = []
        for k in range(ei.shape[1]):
            sr = src_rows_fn(int(ei[0, k]))
            dr = skill_base + int(ei[1, k])
            if sr is not None and 0 <= int(ei[1, k]) < n_skill:
                pairs.append((sr, dr))
        if not pairs:
            return None
        if len(pairs) > cap:
            rng = np.random.RandomState(7)
            pairs = [pairs[i] for i in rng.choice(len(pairs), size=cap, replace=False)]
        xs, ys, zs = [], [], []
        for sr, dr in pairs:
            xs += [float(X3[sr, 0]), float(X3[dr, 0]), None]
            ys += [float(X3[sr, 1]), float(X3[dr, 1]), None]
            zs += [float(X3[sr, 2]), float(X3[dr, 2]), None]
        log.info("Edge %s: %d segments (capped %d)", name, len(pairs), cap)
        return {"type": "scatter3d", "mode": "lines", "name": name,
                "x": xs, "y": ys, "z": zs, "hoverinfo": "skip",
                "line": {"color": color, "width": 1}, "opacity": 0.12,
                "visible": "legendonly"}

    edge_traces = []
    t = edge_trace(("cv", "has_skill", "skill"), lambda i: i if i < n_cv else None,
                   "#38bdf8", "edges: cv→skill")
    if t: edge_traces.append(t)
    t = edge_trace(("job", "requires_skill", "skill"), lambda i: job_row.get(i),
                   "#fb923c", "edges: job→skill")
    if t: edge_traces.append(t)

    # --- group into Plotly traces: cv/job by role, skill+seniority as own groups ---
    groups: dict[str, dict] = {}
    for j in range(X3.shape[0]):
        nt = ntypes[j]
        key = "skill" if nt == "skill" else "seniority" if nt == "seniority" else f"{nt}:{roles[j]}"
        g = groups.setdefault(key, {"x": [], "y": [], "z": [], "text": [], "ntype": nt})
        g["x"].append(float(X3[j, 0])); g["y"].append(float(X3[j, 1])); g["z"].append(float(X3[j, 2]))
        g["text"].append(labels[j])

    # color by role (shared cv/job palette so same role lines up), shapes by type
    role_color = {
        "frontend": "#2563eb", "backend": "#16a34a", "fullstack": "#9333ea",
        "qa": "#db2777", "devops": "#ea580c", "data_ml": "#0891b2",
        "mobile": "#ca8a04", "ba": "#65a30d", "data_eng": "#0d9488",
        "design": "#e11d48", "other": "#9ca3af",
        "skill": "#94a3b8", "seniority": "#111827",
    }
    sym = {"cv": "circle", "job": "diamond", "skill": "cross", "seniority": "square"}
    size = {"cv": 5, "job": 3, "skill": 2, "seniority": 10}

    traces = []
    for key in sorted(groups):
        g = groups[key]
        nt = g["ntype"]
        role = key.split(":")[1] if ":" in key else key
        traces.append({
            "type": "scatter3d", "mode": "markers", "name": key,
            "x": g["x"], "y": g["y"], "z": g["z"], "text": g["text"],
            "hoverinfo": "text",
            "marker": {"size": size[nt], "symbol": sym[nt],
                        "color": role_color.get(role, "#9ca3af"),
                        "opacity": 0.85 if nt in ("cv", "seniority") else 0.6,
                        "line": {"width": 0}},
        })

    traces = edge_traces + traces  # edges render behind nodes, off by default
    title = (f"JobFlow HeteroGraphSAGE — {X3.shape[0]} nodes in 3D ({method.upper()}) · "
             f"cv●={len(cvs)} job◆={len(job_idx)} · AUC={meta.get('test_metrics',{}).get('auc_roc',0):.3f}")
    html = _HTML.replace("__DATA__", json.dumps(traces)).replace("__TITLE__", title)
    out.write_text(html)
    log.info("Wrote %s  (open in browser)", out)


_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>JobFlow Graph 3D</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>body{margin:0;font-family:Inter,system-ui,sans-serif;background:#0b1020;color:#e5e7eb}
#h{padding:10px 16px;font-size:13px;border-bottom:1px solid #1f2937}
#p{width:100vw;height:calc(100vh - 44px)}</style></head>
<body><div id="h">__TITLE__ &nbsp;—&nbsp; <b>kéo</b> để xoay · <b>cuộn</b> để zoom · <b>click legend</b> để ẩn/hiện nhóm · hover xem chi tiết</div>
<div id="p"></div>
<script>
var data = __DATA__;
var layout = {paper_bgcolor:'#0b1020', font:{color:'#e5e7eb'}, showlegend:true,
  legend:{itemsizing:'constant', font:{size:10}},
  margin:{l:0,r:0,t:0,b:0},
  scene:{xaxis:{backgroundcolor:'#0b1020',gridcolor:'#1f2937',color:'#6b7280'},
         yaxis:{backgroundcolor:'#0b1020',gridcolor:'#1f2937',color:'#6b7280'},
         zaxis:{backgroundcolor:'#0b1020',gridcolor:'#1f2937',color:'#6b7280'}}};
Plotly.newPlot('p', data, layout, {responsive:true});
</script></body></html>"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default="checkpoints/latest")
    ap.add_argument("--out", default="/tmp/jobflow_graph_3d.html")
    ap.add_argument("--method", choices=["tsne", "pca"], default="tsne")
    ap.add_argument("--max-jobs", type=int, default=2500, help="subsample jobs for readability (0=all)")
    a = ap.parse_args()
    main(a.ckpt, Path(a.out), a.method, a.max_jobs)
