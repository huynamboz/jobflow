from __future__ import annotations

import numpy as np
import torch
from torch_geometric.data import HeteroData

from ml_service.data.skill_graph import (
    build_cv_similarity_edges,
    build_job_similarity_edges,
    build_semantic_skill_edges,
    build_skill_edges,
)
from ml_service.embedding.base import EmbeddingProvider
from ml_service.graph.schema import (
    CVData,
    JobData,
    LabeledPair,
    SeniorityLevel,
    SkillCategory,
)

def _minmax(arr: np.ndarray) -> np.ndarray:
    """Min-max normalize array to [0, 1]."""
    mn, mx = arr.min(), arr.max()
    if mx - mn < 1e-8:
        return np.full_like(arr, 0.5)
    return (arr - mn) / (mx - mn)


class GraphBuilder:
    def __init__(self, embedding_provider: EmbeddingProvider) -> None:
        self._embed = embedding_provider

    def build(
        self,
        cvs: list[CVData],
        # Note: skill graph (relates_to, similar_to) is built from ALL data passed here.
        # For proper train/test separation, pass only training CVs/jobs.
        jobs: list[JobData],
        skill_catalog: dict[str, SkillCategory],
        pairs: list[LabeledPair],
    ) -> HeteroData:
        data = HeteroData()

        # Build index mappings
        cv_id_to_idx = {cv.cv_id: i for i, cv in enumerate(cvs)}
        job_id_to_idx = {job.job_id: i for i, job in enumerate(jobs)}
        skill_names = sorted(skill_catalog.keys())
        skill_to_idx = {s: i for i, s in enumerate(skill_names)}

        # --- CV nodes: embedding(384) + experience_years_norm + education_norm = 386 ---
        cv_texts = [cv.text for cv in cvs]
        cv_embeddings = self._embed.encode(cv_texts)  # (N, 384)
        exp_years = np.array([cv.experience_years for cv in cvs], dtype=np.float32)
        edu_levels = np.array([float(cv.education) for cv in cvs], dtype=np.float32)
        # Min-max normalize
        exp_norm = _minmax(exp_years)
        edu_norm = _minmax(edu_levels)
        cv_extra = np.stack([exp_norm, edu_norm], axis=1)
        data["cv"].x = torch.from_numpy(np.concatenate([cv_embeddings, cv_extra], axis=1))

        # --- Job nodes: embedding(384) + salary_min_norm + salary_max_norm + role_category_onehot(11) = 397 ---
        _ROLE_CATEGORIES = [
            "other", "frontend", "backend", "fullstack", "qa",
            "devops", "data_ml", "mobile", "ba", "data_eng", "design",
        ]
        _role_to_idx = {r: i for i, r in enumerate(_ROLE_CATEGORIES)}

        job_texts = [job.text for job in jobs]
        job_embeddings = self._embed.encode(job_texts)  # (N, 384)
        sal_min = np.array([float(job.salary_min) for job in jobs], dtype=np.float32)
        sal_max = np.array([float(job.salary_max) for job in jobs], dtype=np.float32)
        role_onehot = np.zeros((len(jobs), len(_ROLE_CATEGORIES)), dtype=np.float32)
        for i, job in enumerate(jobs):
            rc = (job.role_category or "other").lower()
            role_onehot[i, _role_to_idx.get(rc, 0)] = 1.0
        job_extra = np.concatenate(
            [np.stack([_minmax(sal_min), _minmax(sal_max)], axis=1), role_onehot],
            axis=1,
        )
        data["job"].x = torch.from_numpy(np.concatenate([job_embeddings, job_extra], axis=1))

        # --- Skill nodes: embedding(384) + category = 385 ---
        skill_embeddings = self._embed.encode(skill_names)  # (S, 384)
        skill_cats = np.array(
            [[float(skill_catalog[s])] for s in skill_names],
            dtype=np.float32,
        )
        data["skill"].x = torch.from_numpy(np.concatenate([skill_embeddings, skill_cats], axis=1))

        # --- Seniority nodes: identity matrix (6, 6) ---
        data["seniority"].x = torch.eye(len(SeniorityLevel))

        # --- has_skill edges: CV -> Skill (with proficiency weight) ---
        hs_src, hs_dst, hs_attr = [], [], []
        for cv in cvs:
            cv_idx = cv_id_to_idx[cv.cv_id]
            for skill, prof in zip(cv.skills, cv.skill_proficiencies):
                if skill in skill_to_idx:
                    hs_src.append(cv_idx)
                    hs_dst.append(skill_to_idx[skill])
                    hs_attr.append(float(prof))
        data["cv", "has_skill", "skill"].edge_index = torch.tensor(
            [hs_src, hs_dst], dtype=torch.long
        )
        data["cv", "has_skill", "skill"].edge_attr = torch.tensor(hs_attr, dtype=torch.float)

        # --- requires_skill edges: Job -> Skill (with importance weight) ---
        rs_src, rs_dst, rs_attr = [], [], []
        for job in jobs:
            job_idx = job_id_to_idx[job.job_id]
            for skill, imp in zip(job.skills, job.skill_importances):
                if skill in skill_to_idx:
                    rs_src.append(job_idx)
                    rs_dst.append(skill_to_idx[skill])
                    rs_attr.append(float(imp))
        data["job", "requires_skill", "skill"].edge_index = torch.tensor(
            [rs_src, rs_dst], dtype=torch.long
        )
        data["job", "requires_skill", "skill"].edge_attr = torch.tensor(rs_attr, dtype=torch.float)

        # --- has_seniority edges: CV -> Seniority ---
        hsen_src, hsen_dst = [], []
        for cv in cvs:
            hsen_src.append(cv_id_to_idx[cv.cv_id])
            hsen_dst.append(int(cv.seniority))
        data["cv", "has_seniority", "seniority"].edge_index = torch.tensor(
            [hsen_src, hsen_dst], dtype=torch.long
        )

        # --- requires_seniority edges: Job -> Seniority ---
        rsen_src, rsen_dst = [], []
        for job in jobs:
            rsen_src.append(job_id_to_idx[job.job_id])
            rsen_dst.append(int(job.seniority))
        data["job", "requires_seniority", "seniority"].edge_index = torch.tensor(
            [rsen_src, rsen_dst], dtype=torch.long
        )

        # --- skill → skill (relates_to) edges: PMI co-occurrence + semantic similarity ---
        sk_edge_index, sk_edge_attr = build_skill_edges(cvs, jobs, skill_to_idx)

        # Supplement with embedding-based edges for semantically close skills
        # that rarely co-occur (e.g. nodejs ↔ express, fastapi ↔ flask).
        existing_pmi: set[tuple[str, str]] = set()
        for s, d in zip(sk_edge_index[0], sk_edge_index[1]):
            a, b = skill_names[s], skill_names[d]
            existing_pmi.add((min(a, b), max(a, b)))
        sem_edge_index, sem_attr = build_semantic_skill_edges(
            skill_names, skill_embeddings, skill_to_idx, existing_pmi,
            threshold=0.70, max_new_per_skill=5,
        )

        all_src = sk_edge_index[0] + sem_edge_index[0]
        all_dst = sk_edge_index[1] + sem_edge_index[1]
        all_attr = sk_edge_attr + sem_attr

        if all_src:
            data["skill", "relates_to", "skill"].edge_index = torch.tensor(
                [all_src, all_dst], dtype=torch.long
            )
            data["skill", "relates_to", "skill"].edge_attr = torch.tensor(
                all_attr, dtype=torch.float
            )

        # --- job → job (similar_to) edges: skill overlap ---
        job_edge_index, job_edge_attr = build_job_similarity_edges(jobs)
        if job_edge_index[0]:
            data["job", "similar_to", "job"].edge_index = torch.tensor(
                job_edge_index, dtype=torch.long
            )
            data["job", "similar_to", "job"].edge_attr = torch.tensor(
                job_edge_attr, dtype=torch.float
            )

        # --- cv → cv (similar_profile) edges: skill overlap ---
        cv_edge_index, cv_edge_attr = build_cv_similarity_edges(cvs)
        if cv_edge_index[0]:
            data["cv", "similar_profile", "cv"].edge_index = torch.tensor(
                cv_edge_index, dtype=torch.long
            )
            data["cv", "similar_profile", "cv"].edge_attr = torch.tensor(
                cv_edge_attr, dtype=torch.float
            )

        # --- match / no_match label edges: CV -> Job ---
        match_src, match_dst = [], []
        nomatch_src, nomatch_dst = [], []
        for pair in pairs:
            cv_idx = cv_id_to_idx.get(pair.cv_id)
            job_idx = job_id_to_idx.get(pair.job_id)
            if cv_idx is None or job_idx is None:
                continue
            if pair.label == 1:
                match_src.append(cv_idx)
                match_dst.append(job_idx)
            else:
                nomatch_src.append(cv_idx)
                nomatch_dst.append(job_idx)

        data["cv", "match", "job"].edge_index = torch.tensor(
            [match_src, match_dst], dtype=torch.long
        )
        data["cv", "no_match", "job"].edge_index = torch.tensor(
            [nomatch_src, nomatch_dst], dtype=torch.long
        )

        return data
