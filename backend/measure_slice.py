"""GNN v2 — measure decode quality of a checkpoint (django-free, runs on server).

Reports: related-skill slice AUC (the capability v1 failed: 0.512) + global
label AUC of the PURE GNN decode, against the v4 labels.

    python measure_slice.py --checkpoint checkpoints/exp_v2 --data data/processed/v4_relabel
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch


def main(ckpt: Path, data_dir: Path) -> None:
    from ml_service.inference.checkpoint import load_checkpoint
    from ml_service.models.gnn import prepare_data_for_gnn
    from ml_service.training.trainer import _strip_label_edges
    from sklearn.metrics import roc_auc_score

    model, data, cvs, jobs, meta = load_checkpoint(ckpt)
    model.eval()
    clean = prepare_data_for_gnn(_strip_label_edges(data))
    with torch.no_grad():
        z = model.encode(clean)

    cv_idx = {cv.cv_id: i for i, cv in enumerate(cvs)}
    job_idx = {j.job_id: i for i, j in enumerate(jobs)}

    labels = json.loads((data_dir / "labels.json").read_text())
    cv_db = {c["idx"]: c["cv_id"] for c in json.loads((data_dir / "cvs.json").read_text())}
    job_db = {j["idx"]: j["job_id"] for j in json.loads((data_dir / "jobs.json").read_text())}

    def auc_for(flt) -> tuple[float, int]:
        ci, ji, y = [], [], []
        for l in labels:
            if not flt(l):
                continue
            c, j = cv_db[l["cv_idx"]], job_db[l["job_idx"]]
            if c in cv_idx and j in job_idx:
                ci.append(cv_idx[c]); ji.append(job_idx[j]); y.append(l["label"])
        with torch.no_grad():
            s = model.decode(z, torch.tensor(ci), torch.tensor(ji)).numpy()
        return roc_auc_score(np.array(y), s), len(y)

    sl, n1 = auc_for(lambda l: l["bucket"] == "related_skill_positive")
    gl, n2 = auc_for(lambda l: True)
    print(f"RESULT slice_auc={sl:.4f} (n={n1}) global_auc={gl:.4f} (n={n2})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--data", default="data/processed/v4_relabel")
    a = ap.parse_args()
    main(Path(a.checkpoint), Path(a.data))
