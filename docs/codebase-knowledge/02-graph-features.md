# Graph Schema, Node Features & Data Layer

## Đồ thị heterogeneous (PyG HeteroData)

**4 loại node**: CV · Job · Skill · Seniority (6 mức)

**Edge types** (schema.py:18-34, builder.py):

| Edge | Hướng | Cách dựng | Trọng số |
|---|---|---|---|
| `has_skill` | CV→Skill | từ CVSkill | proficiency 1-5 |
| `requires_skill` | Job→Skill | từ JobSkill | importance 1-5 |
| `has_seniority` / `requires_seniority` | CV/Job→Seniority | 1 cạnh/node | — |
| `relates_to` | Skill↔Skill | **PMI co-occurrence** (≥3 docs, top-10/skill) + **semantic** (cosine ≥ 0.70, +5/skill, không trùng PMI) | PMI/sim |
| `similar_to` | Job↔Job | Jaccard skill ≥ 0.3, top-5/job | sim |
| `similar_profile` | CV↔CV | Jaccard ≥ 0.3, top-5/CV, 2 chiều | sim |
| `match` / `no_match` | CV→Job | **nhãn LLM** (chỉ train; bị strip khi message-passing) | — |

`prepare_data_for_gnn` = ToUndirected (thêm reverse edges).

## Node features

| Node | Dim | Công thức |
|---|---|---|
| CV | **386** | sentence_embed(text)[384] + exp_years_norm + edu_norm |
| Job | **397** | sentence_embed(text)[384] + minmax(salary_min) + minmax(salary_max) + **role_onehot[11]** |
| Skill | **385** | embed(name)[384] + category(1) |
| Seniority | 6×6 | identity one-hot |

`ROLE_CATEGORIES` (builder.py:32): `other, frontend, backend, fullstack, qa, devops, data_ml, mobile, ba, data_eng, design`.

⚠️ Lưu ý quan trọng: **role nằm trong job features (one-hot) nhưng KHÔNG nằm trong CV features** — CV chỉ có role ngầm qua text embedding. Job role one-hot + nhãn thiếu cross-domain → GNN khó học domain matching tường minh.

## Dataclasses (schema.py)

- `CVData(cv_id, seniority 0-5, experience_years, education 0-4, skills, skill_proficiencies 1-5, text)`
- `JobData(job_id, seniority, skills, skill_importances 1-5, salary_min/max, text, experience_min/max, role_category)`
- Enums: `SeniorityLevel` INTERN(0)..MANAGER(5) · `EducationLevel` NONE(0)..PHD(4) · `SkillCategory` TECHNICAL/SOFT/TOOL/DOMAIN

## Role inference (`ml_service/inference/role_classifier.py`)

- `infer_role(skills, text)`: **title regex** (200 ký tự đầu) → **skill set** (≥2 skill trùng bộ role) → fullstack nếu có cả FE+BE → "other".
- `role_match_penalty(cv_role, job_role)`: 1.0 cùng/tương thích · 0.7 kề · 0.45 lệch hẳn — nhân vào score Stage-1.
- ⚠️ Taxonomy của role_classifier (frontend/backend/fullstack/devops/**data/ml**/mobile/security/erp/other) **không trùng 100%** với `ROLE_CATEGORIES` của Job (data_ml/data_eng/qa/ba/design) — nguồn lệch tiềm ẩn khi so `infer_role(cv) == job.role_category`.

## Skill layer (`ml_service/data/`)

- `SkillNormalizer` (skill_normalization.py): skill-alias.json — **145 canonical skills**, alias lowercase → canonical, catalog name→category.
- `skill_graph.py`: build_skill_cooccurrence (PMI), build_semantic_skill_edges, build_job/cv_similarity_edges.
- `skill_taxonomy.py`: SKILL_SYNONYMS, SKILL_CLUSTERS (8 cụm role), cluster coverage 40%.
- `labeler.py`: PairLabeler — rule synthetic (chỉ dùng path in-app, không phải production).

## Embedding (`ml_service/embedding/`)

- Provider factory; mặc định `EnglishProvider` = **all-MiniLM-L6-v2, 384-dim, normalized**. Có `BgeSmallProvider` (bge-small-en-v1.5, 384) thay thế drop-in. node_dims lưu trong checkpoint metadata để đổi provider an toàn.

## Job DB → JobData (live path, feature 018)

`build_jobdata_from_db` (matching_service.py:262): Job.id, seniority clamp [0,5], skills = JobSkill→`skill.canonical_name`, importance, salary, text = "title. description", experience_min/max, **role_category = Job.role_category** (lowercase, default "other"). Lọc `is_active=True` + ≥1 skill.

**Nguồn `Job.role_category`**: LLM JD extraction (`apps/jobs/services/llm_jd_extractor.py`, 11 giá trị) — extraction fail → "other". ⚠️ Job thiếu nhãn role → domain_fit trung tính 0.5; nhóm "Data Analyst" hiện chưa được label role → 2 ca lệch trong eval 20-CV.

## Cập nhật GNN v2 (024 — 2026-06-11)

- **Embedding provider production = `multilingual`** (paraphrase-multilingual-MiniLM-L12-v2,
  384-dim, normalize) — thay all-MiniLM-L6-v2 tiếng-Anh. Đây là thay đổi ăn điểm nhất lịch sử
  model (slice related-skill 0.512→0.73). Đổi provider = đổi node features = PHẢI retrain.
- **CV node 386 → 397-dim**: thêm role one-hot 11 (suy bằng `infer_role` canonical 023) — đối
  xứng với job node. Checkpoint cũ không load được vào builder mới → luôn giữ backup.
- **Pretrain tự giám sát** (`run_pretrain.py`): link-prediction trên has_skill/requires_skill
  (drop 30%, dot-product, BCE, 120 epoch, link-acc ~0.80) → warm-start BPR qua env `PRETRAIN_PATH`.
- Trainer env gates: `AUX_ROLE_WEIGHT` (default 0 — 0.3 phá BPR, xem doc 12), `SKILL_REL_WEIGHT`
  (default 0), `GNN_MODEL` (graphsage|gat|rgcn — HeteroGAT thêm ở 024, không dùng production).
