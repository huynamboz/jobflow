"""Skill-to-Skill relationship graph.

Builds relates_to edges between skills that co-occur frequently in the same
CV or JD. This gives GNN the ability to infer: if CV has "Flask" and JD
requires "Django", GNN knows Flask relates_to Django (both Python web frameworks)
→ partial match even though skill overlap = 0.

Also builds job_cluster edges (Job → Job with similar skill profiles).
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict

from ml_benchmark.graph.schema import CVData, JobData

# Minimum co-occurrence count to create an edge
_MIN_COOCCURRENCE = 3
# Maximum edges per skill (keep graph sparse)
_MAX_EDGES_PER_SKILL = 10


def build_skill_cooccurrence(
    cvs: list[CVData],
    jobs: list[JobData],
) -> dict[tuple[str, str], float]:
    """Compute skill co-occurrence from CVs and JDs.

    Returns dict of (skill_a, skill_b) → PMI score (Pointwise Mutual Information).
    Higher PMI = stronger relationship.
    """
    # Count individual skill frequency and pair co-occurrence
    skill_freq: Counter[str] = Counter()
    pair_freq: Counter[tuple[str, str]] = Counter()
    total_docs = 0

    for cv in cvs:
        skills = sorted(set(cv.skills))
        skill_freq.update(skills)
        for i, a in enumerate(skills):
            for b in skills[i + 1:]:
                pair_freq[(a, b)] += 1
                pair_freq[(b, a)] += 1
        total_docs += 1

    for job in jobs:
        skills = sorted(set(job.skills))
        skill_freq.update(skills)
        for i, a in enumerate(skills):
            for b in skills[i + 1:]:
                pair_freq[(a, b)] += 1
                pair_freq[(b, a)] += 1
        total_docs += 1

    if total_docs == 0:
        return {}

    # Compute PMI: log(P(a,b) / (P(a) * P(b)))
    edges: dict[tuple[str, str], float] = {}
    for (a, b), count in pair_freq.items():
        if count < _MIN_COOCCURRENCE:
            continue
        if a >= b:  # deduplicate (keep a < b)
            continue
        p_ab = count / total_docs
        p_a = skill_freq[a] / total_docs
        p_b = skill_freq[b] / total_docs
        if p_a == 0 or p_b == 0:
            continue
        pmi = math.log(p_ab / (p_a * p_b))
        if pmi > 0:  # only keep positive associations
            edges[(a, b)] = pmi

    return edges


def build_skill_edges(
    cvs: list[CVData],
    jobs: list[JobData],
    skill_to_idx: dict[str, int],
) -> tuple[list[list[int]], list[float]]:
    """Build Skill → Skill edge_index and edge_attr for the graph.

    Returns:
        edge_index: [[src_indices], [dst_indices]]
        edge_attr: PMI weights (normalized to 0-1)
    """
    cooccurrence = build_skill_cooccurrence(cvs, jobs)

    if not cooccurrence:
        return [[], []], []

    # Normalize PMI to 0-1
    max_pmi = max(cooccurrence.values())
    min_pmi = min(cooccurrence.values())
    pmi_range = max_pmi - min_pmi if max_pmi > min_pmi else 1.0

    # Limit edges per skill
    edges_by_skill: defaultdict[str, list[tuple[str, float]]] = defaultdict(list)
    for (a, b), pmi in cooccurrence.items():
        norm_pmi = (pmi - min_pmi) / pmi_range
        edges_by_skill[a].append((b, norm_pmi))
        edges_by_skill[b].append((a, norm_pmi))

    src, dst, attr = [], [], []
    added: set[tuple[str, str]] = set()

    for skill, neighbors in edges_by_skill.items():
        # Keep top-K by PMI
        neighbors.sort(key=lambda x: -x[1])
        for neighbor, weight in neighbors[:_MAX_EDGES_PER_SKILL]:
            if skill not in skill_to_idx or neighbor not in skill_to_idx:
                continue
            pair = (min(skill, neighbor), max(skill, neighbor))
            if pair in added:
                continue
            added.add(pair)
            s_idx = skill_to_idx[skill]
            d_idx = skill_to_idx[neighbor]
            # Bidirectional
            src.extend([s_idx, d_idx])
            dst.extend([d_idx, s_idx])
            attr.extend([weight, weight])

    return [src, dst], attr


def build_semantic_skill_edges(
    skill_names: list[str],
    skill_embeddings: "np.ndarray",
    skill_to_idx: dict[str, int],
    existing_edges: set[tuple[str, str]],
    threshold: float = 0.70,
    max_new_per_skill: int = 5,
) -> tuple[list[list[int]], list[float]]:
    """Build skill-skill edges from embedding cosine similarity.

    Supplements PMI edges for skill pairs that rarely co-occur in the training
    data but are semantically close (e.g. nodejs ↔ express, fastapi ↔ flask).
    Only adds edges not already covered by existing_edges.
    """
    import numpy as np

    n = len(skill_names)
    norms = np.linalg.norm(skill_embeddings, axis=1, keepdims=True)
    norms = np.where(norms < 1e-8, 1.0, norms)
    emb_norm = skill_embeddings / norms
    sim_matrix = (emb_norm @ emb_norm.T).astype(float)  # (S, S)

    src, dst, attr = [], [], []
    added: set[tuple[str, str]] = set()

    for i, skill_a in enumerate(skill_names):
        sims = sorted(
            ((j, float(sim_matrix[i, j])) for j in range(n) if j != i),
            key=lambda x: -x[1],
        )
        count = 0
        for j, sim in sims:
            if count >= max_new_per_skill:
                break
            if sim < threshold:
                break
            skill_b = skill_names[j]
            pair = (min(skill_a, skill_b), max(skill_a, skill_b))
            if pair in existing_edges or pair in added:
                continue
            added.add(pair)
            src.extend([skill_to_idx[skill_a], skill_to_idx[skill_b]])
            dst.extend([skill_to_idx[skill_b], skill_to_idx[skill_a]])
            attr.extend([sim, sim])
            count += 1

    return [src, dst], attr


def build_job_similarity_edges(
    jobs: list[JobData],
    top_k: int = 5,
    min_overlap: float = 0.3,
) -> tuple[list[list[int]], list[float]]:
    """Build Job → Job edges based on skill set similarity.

    Jobs with similar skill requirements are connected → GNN can propagate
    information between similar roles.
    """
    n = len(jobs)
    src, dst, attr = [], [], []

    for i in range(n):
        skills_i = set(jobs[i].skills)
        if not skills_i:
            continue
        similarities: list[tuple[int, float]] = []
        for j in range(n):
            if i == j:
                continue
            skills_j = set(jobs[j].skills)
            if not skills_j:
                continue
            union = skills_i | skills_j
            overlap = len(skills_i & skills_j) / len(union) if union else 0.0
            if overlap >= min_overlap:
                similarities.append((j, overlap))

        # Keep top-K most similar
        similarities.sort(key=lambda x: -x[1])
        for j, sim in similarities[:top_k]:
            src.append(i)
            dst.append(j)
            attr.append(sim)

    return [src, dst], attr


def build_cv_similarity_edges(
    cvs: list[CVData],
    top_k: int = 5,
    min_overlap: float = 0.3,
) -> tuple[list[list[int]], list[float]]:
    """Build CV → CV edges based on skill set similarity.

    CVs with similar skill profiles are connected → if CV_A matches Job_X,
    GNN propagates signal to CV_B (similar to CV_A).
    """
    n = len(cvs)
    src, dst, attr = [], [], []

    for i in range(n):
        skills_i = set(cvs[i].skills)
        if not skills_i:
            continue
        similarities: list[tuple[int, float]] = []
        for j in range(i + 1, n):
            skills_j = set(cvs[j].skills)
            if not skills_j:
                continue
            union = skills_i | skills_j
            overlap = len(skills_i & skills_j) / len(union) if union else 0.0
            if overlap >= min_overlap:
                similarities.append((j, overlap))

        similarities.sort(key=lambda x: -x[1])
        for j, sim in similarities[:top_k]:
            # Bidirectional
            src.extend([i, j])
            dst.extend([j, i])
            attr.extend([sim, sim])

    return [src, dst], attr
