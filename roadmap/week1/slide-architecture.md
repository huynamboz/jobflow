> ⚠️ **ARTIFACT LỊCH SỬ (Week 1)** — số liệu trong file này là snapshot thời điểm tuần 1
> (386-dim, hidden 128, all-MiniLM tiếng Anh, chưa có domain term). KHÔNG dùng cho slide
> hiện tại — dùng [roadmap/slide.md](../slide.md) (đã đồng bộ production GNN v2, 2026-06-11).

# Kiến trúc hệ thống JobFlow-GNN — Sơ đồ cho Slide

---

## Slide 1: Tổng quan hệ thống (End-to-End Pipeline)

```
┌──────────────────────────────────────────────────────────────────────┐
│                        JobFlow-GNN System                           │
│                                                                      │
│  ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌───────────────┐   │
│  │  Crawl  │───▶│ Extract  │───▶│  Build   │───▶│    Train      │   │
│  │  Jobs   │    │  Skills  │    │  Graph   │    │    GNN        │   │
│  └─────────┘    └──────────┘    └──────────┘    └───────┬───────┘   │
│                                                         │           │
│                                                         ▼           │
│  ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌───────────────┐   │
│  │  Input  │───▶│ Extract  │───▶│  Score   │───▶│   Output      │   │
│  │  JD     │    │  Skills  │    │  CVs     │    │   Top K CVs   │   │
│  └─────────┘    └──────────┘    └──────────┘    └───────────────┘   │
│                                                                      │
│  ─── Training Flow (offline) ───────────────────────────── trên ──  │
│  ─── Inference Flow (online) ───────────────────────────── dưới ──  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Slide 2: Training Flow (5 bước)

```
Bước 1                Bước 2                Bước 3
┌──────────┐         ┌──────────┐         ┌──────────────────┐
│  Indeed   │         │  Skill   │         │   Heterogeneous  │
│  Crawl    │────────▶│  Extract │────────▶│   Graph (PyG)    │
│  315 JDs  │         │  + Label │         │                  │
└──────────┘         └──────────┘         │  CV ──► Skill    │
                                           │  Job ──► Skill   │
                                           │  CV ──► Seniority│
                                           │  Job ──► Seniority
                                           └────────┬─────────┘
                                                    │
                                                    ▼
                          Bước 5               Bước 4
                     ┌──────────────┐    ┌──────────────────┐
                     │  Checkpoint  │◀───│  HeteroGraphSAGE │
                     │  Save        │    │  + BPR Loss      │
                     │  model.pt    │    │  + Early Stopping │
                     └──────────────┘    └──────────────────┘
```

---

## Slide 3: Inference Flow (4 bước)

```
Bước 1                Bước 2               Bước 3              Bước 4
┌──────────┐         ┌──────────┐         ┌──────────┐        ┌──────────────┐
│  JD Text │         │  Extract │         │  Hybrid  │        │  Top K CVs   │
│  (mới)   │────────▶│  Skills  │────────▶│  Score   │───────▶│  + Score     │
│          │         │  + Sen.  │         │          │        │  + Eligible  │
└──────────┘         └──────────┘         │ α×GNN    │        │  + Skills    │
                                           │ β×Skill  │        └──────────────┘
                                           │ γ×Senior │
                                           └────┬─────┘
                                                │
                                       ┌────────┴────────┐
                                       │  CV Embeddings  │
                                       │  (precomputed)  │
                                       └─────────────────┘
```

---

## Slide 4: Graph Schema

```
                        ┌─────────────┐
                        │  Seniority  │
                        │ (6 levels)  │
                        └──────┬──────┘
                               │
              has_seniority ───┘└─── requires_seniority
                               │
              ┌────────────────┘└────────────────┐
              │                                  │
        ┌─────┴──────┐                    ┌──────┴─────┐
        │     CV     │                    │    Job     │
        │ (200 nodes)│                    │(311 nodes) │
        │            │                    │            │
        │ embedding  │                    │ embedding  │
        │ exp_years  │    match /         │ salary_min │
        │ edu_level  │    no_match        │ salary_max │
        └─────┬──────┘◄──────────────────►└──────┬─────┘
              │                                  │
     has_skill│                                  │requires_skill
      (w=1–5) │                                  │ (w=1–5)
              │          ┌────────────┐          │
              └─────────►│   Skill    │◄─────────┘
                         │ (85 nodes) │
                         │            │
                         │ embedding  │
                         │ category   │
                         └────────────┘

4 Node Types  ×  6 Edge Types  =  Heterogeneous Graph
```

---

## Slide 5: Mô hình GNN (HeteroGraphSAGE)

```
┌─────────────────────────────────────────────────────────────────┐
│                      HeteroGraphSAGE                            │
│                                                                  │
│  Layer 1: Per-type Projection                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  CV (386)  ──► Linear ──► (128)                           │ │
│  │  Job (386) ──► Linear ──► (128)                           │ │
│  │  Skill (385) ► Linear ──► (128)                           │ │
│  │  Seniority (6) Linear ──► (128)                           │ │
│  └────────────────────────────────────────────────────────────┘ │
│                          │                                       │
│                          ▼                                       │
│  Layer 2: GraphSAGE × 2 layers (message passing)               │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                                                            │ │
│  │  Mỗi node nhận thông tin từ neighbors qua edges           │ │
│  │  CV ◄──► Skill ◄──► Job  (2-hop: CV thấy Job qua Skill)  │ │
│  │  Aggregation: mean                                         │ │
│  │                                                            │ │
│  │  Output: z_cv (128-dim), z_job (128-dim)                  │ │
│  └────────────────────────────────────────────────────────────┘ │
│                          │                                       │
│                          ▼                                       │
│  Layer 3: MLPDecoder                                            │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  concat(z_cv, z_job) → (256) → ReLU → (128) → (1)       │ │
│  │  Output: matching score                                    │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## Slide 6: Hybrid Scoring

```
                    JD (mới) × CV (từ pool)
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
        ┌───────────┐  ┌───────────┐  ┌───────────┐
        │   GNN     │  │   Skill   │  │ Seniority │
        │  Score    │  │  Overlap  │  │   Match   │
        │           │  │ (Jaccard) │  │           │
        │  α = 0.8  │  │  β = 0.15 │  │  γ = 0.05 │
        └─────┬─────┘  └─────┬─────┘  └─────┬─────┘
              │               │               │
              └───────────────┼───────────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │  Final Score    │
                     │  = α×GNN       │
                     │  + β×Skill     │
                     │  + γ×Seniority │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │  score >= 0.65  │
                     │  → ELIGIBLE     │
                     │  score <  0.65  │
                     │  → NOT ELIGIBLE │
                     └─────────────────┘
```

---

## Slide 7: Kết quả Benchmark

```
┌──────────────────────────────────────────────────────────────┐
│  GNN vs Baselines (311 Real JDs + 200 Synthetic CVs)        │
│                                                              │
│  Recall@5                          Recall@10                 │
│  ┌────────────────────┐            ┌────────────────────┐   │
│  │ Cosine   ██ 2.7%   │            │ Cosine   ██ 4.1%   │   │
│  │ Jaccard  ████ 5.4% │            │ Jaccard  █████ 8.1%│   │
│  │ BM25     ██ 2.7%   │            │ BM25     ██ 2.7%   │   │
│  │ GNN      █████ 6.8%│ ◄ +25%    │ GNN      ████████   │   │
│  └────────────────────┘            │          12.2%      │   │
│                                    └────────────────────┘   │
│                                                   ◄ +50%    │
│  NDCG@5                            NDCG@10                  │
│  ┌────────────────────┐            ┌────────────────────┐   │
│  │ Cosine   ████ 49%  │            │ Cosine   ████ 38%  │   │
│  │ Jaccard  ████████85%│            │ Jaccard  ██████ 69%│   │
│  │ BM25     ███ 32%   │            │ BM25     ██ 20%    │   │
│  │ GNN      ██████████ │ ◄ +17%    │ GNN      █████████ │   │
│  │          100%       │            │          93%       │   │
│  └────────────────────┘            └────────────────────┘   │
│                                                   ◄ +35%    │
└──────────────────────────────────────────────────────────────┘
```

---

## Slide 8: Demo Output

```
┌──────────────────────────────────────────────────────────────┐
│  Input: "Senior Python developer with Django and AWS"        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  #1  CV 16  — 0.7332 ✅ ELIGIBLE                            │
│      Seniority: SENIOR (match ✓)                             │
│      Matched:   python, aws, ci_cd                           │
│      Missing:   django, docker, postgresql, redis             │
│                                                              │
│  #2  CV 69  — 0.7262 ✅ ELIGIBLE                            │
│      Seniority: SENIOR (match ✓)                             │
│      Matched:   python, ci_cd, docker                        │
│      Missing:   django, aws, postgresql, redis                │
│                                                              │
│  #3  CV 35  — 0.7250 ✅ ELIGIBLE                            │
│      Seniority: SENIOR (match ✓)                             │
│      Matched:   aws, ci_cd, docker                           │
│      Missing:   django, python, postgresql, redis             │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## Slide 9: Tech Stack

```
┌────────────────────────────────────────────────────────┐
│                      Tech Stack                        │
│                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │   Python      │  │   PyTorch    │  │  PyTorch    │ │
│  │   3.11        │  │   Geometric  │  │  (GPU/MPS)  │ │
│  └──────────────┘  └──────────────┘  └─────────────┘ │
│                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │  Sentence    │  │  JobSpy      │  │  Pydantic   │ │
│  │  Transformers│  │  (Crawler)   │  │  Settings   │ │
│  └──────────────┘  └──────────────┘  └─────────────┘ │
│                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │  all-MiniLM  │  │  GraphSAGE   │  │  BPR Loss   │ │
│  │  L6-v2       │  │  (GNN)       │  │  (Ranking)  │ │
│  │  dim=384     │  │  128-dim     │  │             │ │
│  └──────────────┘  └──────────────┘  └─────────────┘ │
└────────────────────────────────────────────────────────┘
```
