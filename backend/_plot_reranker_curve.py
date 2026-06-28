"""Sandbox-only: reproduce the reranker training loop with per-epoch logging
and plot a learning curve. Writes NOTHING to any checkpoint — only a PNG.
"""
from __future__ import annotations
import logging
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn

logging.basicConfig(level=logging.WARNING)

from ml_service.data.skill_normalization import SkillNormalizer
from ml_service.embedding import get_provider
from ml_service.inference import InferenceEngine
from ml_service.reranker.ranker import _RerankerMLP, _DIM_NAMES
from train_reranker import load_labels, build_index_pairs, DEFAULT_SKILL_ALIAS

CKPT = Path("checkpoints/sandbox_a14_reranker")
DATA = Path("data/processed/v4_relabel")
EPOCHS = 300

print("loading engine ...")
normalizer = SkillNormalizer(str(DEFAULT_SKILL_ALIAS))
provider = get_provider()
engine = InferenceEngine.from_checkpoint(CKPT, normalizer, provider, job_pool_dir="/nonexistent")
cv_id_to_idx  = {cv.cv_id:   i for i, cv  in enumerate(engine.cv_pool)}
job_id_to_idx = {job.job_id: i for i, job in enumerate(engine.job_pool)}
cvs, jobs = engine.cv_pool, engine.job_pool

tr, va = load_labels(DATA)
tr_cv, tr_job, tr_lbl, tr_dim = build_index_pairs(tr, cv_id_to_idx, job_id_to_idx)
va_cv, va_job, va_lbl, _      = build_index_pairs(va, cv_id_to_idx, job_id_to_idx)
print(f"train {len(tr_lbl)} · val {len(va_lbl)}")

def compute_scores(ci_list, ji_list):
    tc, gc = {}, {}
    g, s = [], []
    for ci, ji in zip(ci_list, ji_list):
        if ci not in tc:
            tc[ci] = provider.encode([cvs[ci].text])[0]
            gc[ci] = engine._get_cv_gnn_embedding(cvs[ci])
        g.append(engine._gnn_score_fast(cvs[ci], jobs[ji], ji, tc[ci], gc[ci]))
        s.append(engine._score_pair_fast(cvs[ci], jobs[ji], ji, tc[ci], gc[ci])[0])
    return g, s

print("scoring train ...");  tr_g, tr_s = compute_scores(tr_cv, tr_job)
print("scoring val ...");    va_g, va_s = compute_scores(va_cv, va_job)

fe = engine.reranker._fe
Xtr = fe.extract_batch(cvs, jobs, tr_cv, tr_job, gnn_scores=tr_g, stage1_scores=tr_s).astype(np.float32)
Xva = fe.extract_batch(cvs, jobs, va_cv, va_job, gnn_scores=va_g, stage1_scores=va_s).astype(np.float32)
ytr = np.array(tr_lbl, dtype=np.int64); yva = np.array(va_lbl, dtype=np.int64)

Xtr_t = torch.from_numpy(Xtr); Xva_t = torch.from_numpy(Xva)
ytr_t = torch.from_numpy(ytr)
counts = np.bincount(ytr, minlength=3).clip(1)
w = torch.tensor(len(ytr)/(3.0*counts), dtype=torch.float32)
main_loss_fn = nn.CrossEntropyLoss(weight=w)

# aux tensors (same as production)
aux_t = [torch.from_numpy(np.array([d.get(dn,-1) for d in tr_dim], dtype=np.int64)) for dn in _DIM_NAMES]
AUX_W = 0.3

torch.manual_seed(0)
model = _RerankerMLP(Xtr.shape[1], num_classes=3)
opt = torch.optim.Adam(model.parameters(), lr=1e-3)

ytr_bin = (ytr >= 1).astype(int); yva_bin = (yva >= 1).astype(int)
hist_loss, hist_prec, hist_rec, hist_f1 = [], [], [], []
for ep in range(EPOCHS):
    model.train()
    main_logits, aux_logits = model.forward_all(Xtr_t)
    loss = main_loss_fn(main_logits, ytr_t)
    for aux_l, y_aux in zip(aux_logits, aux_t):
        mask = y_aux >= 0
        if mask.sum() > 0:
            dc = torch.bincount(y_aux[mask], minlength=3).float().clamp(min=1)
            dw = mask.sum().float()/(3.0*dc)
            loss = loss + AUX_W * nn.CrossEntropyLoss(weight=dw)(aux_l[mask], y_aux[mask])
    opt.zero_grad(); loss.backward(); opt.step()

    model.eval()
    with torch.no_grad():
        pb = (model(Xva_t).argmax(1).numpy() >= 1).astype(int)   # predicted "match"
    tp = int(((pb == 1) & (yva_bin == 1)).sum())
    fp = int(((pb == 1) & (yva_bin == 0)).sum())
    fn = int(((pb == 0) & (yva_bin == 1)).sum())
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec  = tp / (tp + fn) if (tp + fn) else 0.0
    f1   = 2*prec*rec/(prec+rec) if (prec+rec) else 0.0
    hist_loss.append(float(loss.item())); hist_prec.append(prec); hist_rec.append(rec); hist_f1.append(f1)

bp = int(np.argmax(hist_prec)); BESTP = bp+1
bf = int(np.argmax(hist_f1));   BESTF = bf+1
print(f"best val PRECISION {hist_prec[bp]:.3f} @ep {BESTP} · recall {hist_rec[bp]:.3f} · best F1 {hist_f1[bf]:.3f} @ep {BESTF} · final P {hist_prec[-1]:.3f} R {hist_rec[-1]:.3f} F1 {hist_f1[-1]:.3f}")

# ---- plot precision / recall / F1 theo epoch ----
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
CREAM="#faf7f0"; GREEN="#2f9e57"; BLUE="#2f6fed"; PURP="#7a4fd0"; INK="#1c2430"; MUTED="#6b7686"; AMBER="#c47d12"
ep_x = list(range(1, EPOCHS+1))
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":13})
fig, ax = plt.subplots(figsize=(12,6.4), dpi=170)
fig.patch.set_facecolor(CREAM); ax.set_facecolor("#ffffff")
ax.plot(ep_x, hist_prec, color=BLUE,  lw=2.6, label="Precision")
ax.plot(ep_x, hist_rec,  color=GREEN, lw=2.2, ls=(0,(5,2)), label="Recall")
ax.plot(ep_x, hist_f1,   color=PURP,  lw=2.0, ls=(0,(1,1)), label="F1")
ax.set_xlabel("Epoch", fontsize=13.5, color=INK)
ax.set_ylabel("Precision / Recall / F1 (val, match/không)", fontsize=13.5, fontweight="bold", color=INK)
ax.set_ylim(0.4, 1.0); ax.tick_params(colors=MUTED); ax.grid(True, alpha=0.16, lw=0.8)
ax.scatter([BESTP],[hist_prec[bp]], color=BLUE, zorder=6, s=60, ec="white", lw=1.2)
ax.annotate(f"precision = {hist_prec[bp]:.3f}\n@ epoch {BESTP}", xy=(BESTP,hist_prec[bp]),
            xytext=(BESTP-95,hist_prec[bp]+0.02), fontsize=11.5, color=BLUE, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.45", fc="#eef3ff", ec=BLUE, lw=1.2),
            arrowprops=dict(arrowstyle="->", color=BLUE, lw=1.3))
for s in ("top","right"): ax.spines[s].set_visible(False)
fig.text(0.125, 0.965, "Huấn luyện Reranker — Precision / Recall / F1 theo epoch", fontsize=17, fontweight="bold", color=INK, va="top")
fig.text(0.125, 0.918, "Quyết định nhị phân match/không · validation · dữ liệu v4 (12.084 nhãn) · 300 epoch", fontsize=11.2, color=MUTED, va="top")
ax.legend(loc="lower right", frameon=True, fontsize=12, facecolor="#ffffff", edgecolor="#e3dccd")
fig.tight_layout(rect=[0,0.0,1,0.88])
out = "../Slide jobflow/precision-curve.png"
fig.savefig(out, facecolor=CREAM, bbox_inches="tight")
print("saved →", out, f"| final: P={hist_prec[-1]:.3f} R={hist_rec[-1]:.3f} F1={hist_f1[-1]:.3f}")
