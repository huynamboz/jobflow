"""Save and load trained model + graph data for inference."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

import torch
from torch_geometric.data import HeteroData

from ml_service.graph.schema import CVData, EducationLevel, JobData, SeniorityLevel
from ml_service.models.gnn import HeteroGraphSAGE, prepare_data_for_gnn

logger = logging.getLogger(__name__)


def save_checkpoint(
    path: Path | str,
    model: HeteroGraphSAGE,
    data: HeteroData,
    cvs: list[CVData],
    jobs: list[JobData],
    metadata: dict | None = None,
) -> None:
    """Save model weights, graph data, and CV/job lists to a directory."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)

    torch.save(model.state_dict(), path / "model.pt")
    torch.save(data, path / "graph.pt")

    # Serialize CVs and Jobs as JSON (frozen dataclasses)
    cv_dicts = [_cv_to_dict(cv) for cv in cvs]
    job_dicts = [_job_to_dict(job) for job in jobs]

    with open(path / "cvs.json", "w", encoding="utf-8") as f:
        json.dump(cv_dicts, f, ensure_ascii=False)
    with open(path / "jobs.json", "w", encoding="utf-8") as f:
        json.dump(job_dicts, f, ensure_ascii=False)

    meta = metadata or {}
    meta["num_cvs"] = len(cvs)
    meta["num_jobs"] = len(jobs)
    # Save node_dims so load_checkpoint can reconstruct the right projection layers
    # when embedding dim changes (e.g. MiniLM 384 → BGE-base 768).
    meta["node_dims"] = {
        ntype: int(layer.in_features)
        for ntype, layer in model.projections.items()
    }
    with open(path / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    logger.info("Checkpoint saved to %s (model + graph + %d CVs + %d jobs)", path, len(cvs), len(jobs))


def load_checkpoint(
    path: Path | str,
    hidden_channels: int = 128,
    num_layers: int = 2,
) -> tuple[HeteroGraphSAGE, HeteroData, list[CVData], list[JobData], dict]:
    """Load model, graph, CVs, jobs from a checkpoint directory."""
    path = Path(path)

    data: HeteroData = torch.load(path / "graph.pt", weights_only=False)

    # Strip label edges + add reverse edges to match training-time metadata
    from ml_service.training.trainer import _strip_label_edges

    data_clean = _strip_label_edges(data)
    data_prepared = prepare_data_for_gnn(data_clean)
    metadata = data_prepared.metadata()

    # Read saved config if available
    meta = {}
    meta_path = path / "metadata.json"
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        train_cfg = meta.get("train_config", {})
        hidden_channels = train_cfg.get("hidden_channels", hidden_channels)
        num_layers = train_cfg.get("num_layers", num_layers)
        dropout = train_cfg.get("dropout", 0.0)
    else:
        dropout = 0.0

    node_dims = meta.get("node_dims") or None  # None → GNN uses its built-in default
    # GNN v2/E4: reconstruct the class the checkpoint was trained with.
    _mtype = (meta.get("train_config") or {}).get("model_type", "graphsage")
    if _mtype == "gat":
        from ml_service.models.gnn import HeteroGAT
        model = HeteroGAT(metadata=metadata, hidden_channels=hidden_channels,
                          num_layers=num_layers, dropout=dropout, node_dims=node_dims)
    else:
        model = HeteroGraphSAGE(
            metadata=metadata,
            hidden_channels=hidden_channels,
            num_layers=num_layers,
            dropout=dropout,
            node_dims=node_dims,
        )
    # GNN v2: strict=False — train-only modules (e.g. role_head) may be absent
    # in older checkpoints (they're never used at inference) or present-but-
    # unused. Log any mismatch so silent drift is visible.
    _missing, _unexpected = model.load_state_dict(
        torch.load(path / "model.pt", weights_only=True), strict=False)
    if _missing or _unexpected:
        logger.info("checkpoint load: missing=%s unexpected=%s", _missing, _unexpected)
    model.eval()

    with open(path / "cvs.json", encoding="utf-8") as f:
        cv_dicts = json.load(f)
    cvs = [_dict_to_cv(d) for d in cv_dicts]

    with open(path / "jobs.json", encoding="utf-8") as f:
        job_dicts = json.load(f)
    jobs = [_dict_to_job(d) for d in job_dicts]

    logger.info("Checkpoint loaded from %s (%d CVs, %d jobs)", path, len(cvs), len(jobs))
    return model, data, cvs, jobs, meta


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _cv_to_dict(cv: CVData) -> dict:
    return {
        "cv_id": cv.cv_id,
        "seniority": int(cv.seniority),
        "experience_years": cv.experience_years,
        "education": int(cv.education),
        "skills": list(cv.skills),
        "skill_proficiencies": list(cv.skill_proficiencies),
        "text": cv.text,
    }


def _dict_to_cv(d: dict) -> CVData:
    return CVData(
        cv_id=d["cv_id"],
        seniority=SeniorityLevel(d["seniority"]),
        experience_years=d["experience_years"],
        education=EducationLevel(d["education"]),
        skills=tuple(d["skills"]),
        skill_proficiencies=tuple(d["skill_proficiencies"]),
        text=d["text"],
    )


def _job_to_dict(job: JobData) -> dict:
    return {
        "job_id": job.job_id,
        "seniority": int(job.seniority),
        "skills": list(job.skills),
        "skill_importances": list(job.skill_importances),
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "text": job.text,
        "experience_min": job.experience_min,
        "experience_max": job.experience_max,
        "role_category": job.role_category,
    }


def _dict_to_job(d: dict) -> JobData:
    return JobData(
        job_id=d["job_id"],
        seniority=SeniorityLevel(d["seniority"]),
        skills=tuple(d["skills"]),
        skill_importances=tuple(d["skill_importances"]),
        salary_min=d["salary_min"],
        salary_max=d["salary_max"],
        text=d["text"],
        experience_min=float(d.get("experience_min") or 0.0),
        experience_max=float(d["experience_max"]) if d.get("experience_max") else None,
        role_category=d.get("role_category") or "",
    )
