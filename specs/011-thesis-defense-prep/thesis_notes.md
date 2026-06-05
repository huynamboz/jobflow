# Thesis Defense Notes — Trả lời các câu hỏi của thầy

**Ngày**: 2026-05-21
**Tác giả**: Trịnh Huy Nam
**Phiên bản**: Draft 1

> Tài liệu này tổng hợp câu trả lời cho 4 ghi chú của thầy, dựa trên evidence thực tế từ các thí nghiệm Phase 1-5 (commit `c865c3f` → Phase 5 commit). Cập nhật cuối: 2026-05-22 (Phase 5 LSTM + BiLSTM 3-seeds hoàn tất).

---

## 1. Vì sao chọn HeteroGraphSAGE? Phù hợp với dữ liệu nào?

### 1.1. Lý do chọn GraphSAGE làm backbone

6 lý do cụ thể (theo thứ tự ưu tiên):

| # | Lý do | Đối thủ thua ở đâu |
|---|---|---|
| 1 | **Inductive learning** — sinh embedding cho node CHƯA THẤY (job mới đăng) mà không cần retrain toàn graph | GCN, LightGCN: transductive → mỗi job mới phải retrain |
| 2 | **Mini-batch sampling** qua `NeighborLoader` — scale được dataset 1.6M+ apps (CareerBuilder12) | GCN, GAT: full-batch yêu cầu adjacency matrix toàn graph, OOM với big data |
| 3 | **`to_hetero` wrapper của PyG** — biến GraphSAGE thành heterogeneous chỉ bằng 1 dòng code | R-GCN, HGT: phải implement layer hetero thủ công, nhiều params |
| 4 | **Industrial-proven** — Pinterest's PinSage (KDD 2018 Best Paper) là production recsys lớn nhất thế giới, build trên GraphSAGE foundation | Các kiến trúc mới (HGT 2020, GAT 2018) chưa có deploy production scale tương đương |
| 5 | **Stable training** — concat(self, mean(neighbors)) ít oversmoothing hơn GCN khi stack 2-3 layers | GCN: oversmoothing rõ rệt từ layer 3+ |
| 6 | **Flexible aggregator** — `mean`, `max`, `LSTM` đều support; ta dùng `mean` đủ | GIN: chỉ sum, dễ over-fit |

### 1.2. Phân loại trong họ GNN

```
GNN (Graph Neural Network)
├── Spectral methods (cũ, ít dùng)
└── Spatial / Message-Passing (hiện đại)
    ├── Homogeneous
    │   ├── GCN (Kipf 2017)
    │   ├── GraphSAGE (Hamilton 2017)  ← backbone của ta
    │   ├── GAT (Veličković 2018)
    │   ├── GIN (Xu 2019)
    │   └── LightGCN (He 2020)         ← baseline ta so sánh
    └── Heterogeneous
        ├── R-GCN (Schlichtkrull 2018)
        ├── HGT (Hu 2020)
        └── wrap-based
            └── HeteroGraphSAGE (PyG to_hetero) ← model ta
```

### 1.3. Đánh giá phù hợp với dữ liệu

| Dataset | Đặc điểm | Kết quả HeteroSAGE | Phù hợp? |
|---|---|---|---|
| **MovieLens-1M** (Phase 2) | Bipartite, ~6K user × 3K movie, không hetero schema | NDCG@20 = 0.0272 (tie LightGCN 0.0258) | ⚠️ Trung bình — kiến trúc generic cho hetero không tận dụng được trên CF thuần |
| **CareerBuilder12** bipartite (Phase 3) | Bipartite, 3K user × 3K job sau k-core, sparse | NDCG@20 = 0.1689 ± 0.006 (thua LightGCN 0.2738) | ❌ Thua — pure bipartite job-rec, kiến trúc nặng overkill |
| **CareerBuilder12** hetero (Phase 4c) | Bipartite + skill node (extracted keyword) + seniority | NDCG@20 = 0.1426 ± 0.015 | ❌ Tệ hơn cả bipartite — skill extract noise > signal |
| **JobFlow** (Phase 4b, data tự crawl) | Nhỏ, có rich schema (skill + seniority curated) | NDCG@20 = 0.0069 ± 0.001 (thắng LightGCN 0.0041) | ✅ **Thắng** — small + curated rich schema là sân chơi của kiến trúc hetero |

### 1.4. Kết luận về tính phù hợp

> **HeteroGraphSAGE phù hợp khi data có:**
> 1. **Schema heterogeneous đúng nghĩa** (nhiều node type với metadata riêng — skill, seniority, location)
> 2. **Metadata được curated chất lượng cao** (không phải extract noise bằng keyword)
> 3. **Đòi hỏi inductive** (node mới xuất hiện liên tục — đặc trưng job-rec production)
>
> **KHÔNG phù hợp khi data thuần collaborative filtering bipartite**. Trong trường hợp này, LightGCN đơn giản hơn nhưng hiệu quả hơn (chứng minh trên CB12).

---

## 2. Các hướng cải tiến mô hình

Dựa trên kết quả Phase 1-5, có 6 hướng cải tiến cụ thể, sắp xếp theo ưu tiên/impact:

### Ưu tiên 1: Skill extraction chất lượng cao (Big impact)

**Vấn đề**: Phase 4c chứng minh keyword-based extract (regex match skill-alias.json) làm hetero variant TỆ hơn bipartite. False positive như "Java" trong "JavaScript", "Design" trong "Designer required" lan noise qua message passing.

**Cải tiến**:
- Dùng **LLM-based NER** (gpt-4o-mini, Qwen2.5) trích xuất skill có context awareness
- Hoặc dùng **fine-tuned BERT cho NER** (model nhẹ hơn, deploy được)
- Validate output bằng existing `skill-alias.json` (catalog 145 skills)

**Effort**: 2-3 ngày code + cost API
**Expected impact**: hetero variant có thể vượt bipartite → vượt LightGCN trên CB12

### Ưu tiên 2: Hybrid scoring (đã có trong production)

**Vấn đề**: Pure GNN score bỏ qua tín hiệu domain-specific (skill match, seniority match).

**Cải tiến**: Code production tại `backend/ml_service/training/trainer.py` đã có:
```
final_score = α × gnn_score + β × skill_overlap + γ × seniority_match
α=0.6, β=0.3, γ=0.1  # tuned cho JobFlow
```
Áp dụng pattern này lên kết quả benchmark CB12 → kỳ vọng tăng NDCG@20.

**Effort**: 4-6 giờ (port logic + tune cho CB12)
**Expected impact**: Tăng 10-30% NDCG trên dataset có metadata

### Ưu tiên 3: Attention mechanism (HGT)

**Vấn đề**: HeteroGraphSAGE dùng mean aggregation — coi mọi neighbor như nhau.

**Cải tiến**: Thay bằng **HGT (Heterogeneous Graph Transformer, Hu 2020)** — meta-relation-aware attention cho phép model học tự động skill nào quan trọng hơn cho job nào.

**Effort**: 1-2 tuần (HGT phức tạp hơn, debug khó hơn)
**Expected impact**: Tăng 10-20% NDCG nếu có data scale (chứng minh paper trên DBLP, ACM)

### Ưu tiên 4: Pre-trained text embeddings

**Vấn đề**: HeteroSAGE hiện tại dùng trainable id embedding ngẫu nhiên cho user/movie/job nodes. Không tận dụng được semantic của job title/description.

**Cải tiến**:
- Thay xavier_init bằng **Sentence-BERT embedding** (`all-MiniLM-L6-v2`, đã có trong sandbox `embedding/`)
- Job text → vector 384 dim → project to hidden=64

**Effort**: 1 ngày code (sandbox đã có embedding provider sẵn)
**Expected impact**: Tăng 5-15% NDCG, đặc biệt cho cold-start jobs

### Ưu tiên 5: Hard negative mining

**Vấn đề**: BPR sampling random negative — đa số negative quá dễ (random unrelated job), không train được phần khó.

**Cải tiến**:
- Sampling negative theo similarity với positive (vd: same seniority, different skills)
- Đã có ý tưởng trong `trainer._sample_bpr_pairs` với `hard_neg_ratio` param

**Effort**: 1-2 ngày + tune ratio
**Expected impact**: Tăng 5-10% NDCG

### Ưu tiên 6: Multi-task learning

**Vấn đề**: Train chỉ task BPR ranking, bỏ qua signal phụ (salary fit, location fit).

**Cải tiến**: Thêm auxiliary loss:
- Skill prediction loss (predict missing skill từ job description)
- Salary regression loss
- Combined loss: `L = BPR + λ1·skill_pred + λ2·salary`

**Effort**: 1-2 tuần
**Expected impact**: 5-15% NDCG, bonus interpretability

### Tóm tắt cải tiến

| # | Cải tiến | Effort | Impact | ROI |
|---|---|---|---|---|
| 1 | LLM-based skill NER | 2-3 ngày | +10-30% | ⭐⭐⭐⭐⭐ |
| 2 | Hybrid scoring (port từ production) | 4-6 giờ | +10-30% | ⭐⭐⭐⭐⭐ |
| 3 | HGT attention | 1-2 tuần | +10-20% | ⭐⭐⭐ |
| 4 | Pre-trained text embeddings | 1 ngày | +5-15% | ⭐⭐⭐⭐ |
| 5 | Hard negative mining | 1-2 ngày | +5-10% | ⭐⭐⭐ |
| 6 | Multi-task learning | 1-2 tuần | +5-15% | ⭐⭐ |

---

## 3. Kịch bản ứng dụng thực tế

### 3.1. Use case — Khuyến nghị việc làm cho ứng viên

**Input**: CV của ứng viên (PDF hoặc text)

**Pipeline**:

```
                ┌──────────────┐
   CV PDF/text ─►│ CV Parser    │  parse text → structured fields
                │ (Phase 1 code│  (skill, seniority, experience_years)
                │  inference/) │
                └──────┬───────┘
                       ▼
                ┌──────────────┐
                │ Embedding    │  text → 386-dim vector (Sentence-BERT)
                │ Provider     │
                └──────┬───────┘
                       ▼
                ┌──────────────┐
                │ HeteroGraph  │  CV node + Job nodes + Skill nodes
                │ Builder      │  + Seniority nodes
                └──────┬───────┘
                       ▼
                ┌──────────────┐
                │ HeteroGraph  │  forward pass: encode CV + all jobs
                │ SAGE Model   │  → CV embedding [hidden], Job embeddings [N, hidden]
                └──────┬───────┘
                       ▼
                ┌──────────────┐
                │ Hybrid Score │  α·GNN + β·skill_overlap + γ·seniority_match
                │ (Reranker)   │
                └──────┬───────┘
                       ▼
                ┌──────────────┐
                │ Top-K Ranker │  sort by score desc, take top 10
                └──────┬───────┘
                       ▼
                ┌──────────────┐
                │ Explanation  │  per recommendation: matched skills,
                │ Generator    │  seniority match, salary fit
                └──────┬───────┘
                       ▼
                  Top 10 jobs + explanation
                       │
                       ▼
                  REST API JSON
```

**Output mẫu**:

```json
{
  "cv_id": 365,
  "recommendations": [
    {
      "rank": 1,
      "job_id": 23,
      "title": "Senior/Lead Frontend Developer",
      "company": "Zalo",
      "score": 0.847,
      "explanation": {
        "matched_skills": ["react", "javascript", "vue", "tailwind"],
        "skill_match_ratio": "8/9 (88.9%)",
        "seniority_match": "exact (senior)",
        "experience_fit": "3.5y in range [2y, 4y]",
        "missing_skills": ["webpack"]
      }
    },
    ...9 more...
  ],
  "model_version": "HeteroGraphSAGE-v2",
  "served_at": "2026-05-21T15:30:00Z"
}
```

### 3.2. Tích hợp production

**Đã có sẵn** trong production code (không phải xây mới):

| Component | File | Status |
|---|---|---|
| CV Parser | `backend/ml_service/cv_parser/parser.py` | ✅ Production |
| Embedding | `backend/ml_service/embedding/multilingual.py` | ✅ Production |
| HeteroGraph Model | `backend/ml_service/models/gnn.py` | ✅ Production |
| Inference Engine | `backend/ml_service/inference/engine.py` | ✅ Production |
| Reranker (hybrid scoring) | `backend/ml_service/reranker/ranker.py` | ✅ Production |
| REST API | `backend/apps/matching/views.py` (Django) | ✅ Production |
| Admin Dashboard | `admin/src/pages/admin/matching/` (React) | ✅ Production |

**Production stats** (đang vận hành):
- 364 CVs đã enroll
- 6,251 jobs đã crawl (LinkedIn)
- Hybrid score deploy: α=0.6, β=0.3, γ=0.1
- Latency p95: < 200ms cho 10K candidate jobs (qua sentence-transformers cache + GNN inductive inference)

### 3.3. Kịch bản phụ — Khuyến nghị ngược

**Input**: 1 job posting mới (HR tạo)

**Pipeline**: tương tự nhưng reverse — encode job, rank tất cả CVs trong pool → top 10 ứng viên phù hợp.

**Endpoint**: `POST /api/matching/jobs/{job_id}/candidates`

**Use case**: Recruiter dashboard, alert email khi có ứng viên match cao.

---

## 4. So sánh GNN vs LSTM, BiLSTM trên cùng dataset (CB12)

### 4.1. Bảng kết quả 5 models

| Model | NDCG@20 | Recall@20 | HR@20 | MRR | Wall/seed |
|---|---|---|---|---|---|
| **HeteroSAGE bipartite** | 0.1689 ± 0.006 | 0.4479 ± 0.010 | 0.4479 ± 0.010 | 0.1067 ± 0.005 | ~2.2 min |
| **HeteroSAGE hetero (skill+seniority)** | 0.1426 ± 0.015 | 0.3891 ± 0.029 | 0.3891 ± 0.029 | 0.0897 ± 0.011 | ~4.7 min |
| **LightGCN baseline (GNN bipartite)** | **0.2738 ± 0.001** | **0.6480 ± 0.005** | **0.6480 ± 0.005** | **0.1799 ± 0.000** | ~1.5 min |
| **LSTM (sequence baseline)** | 0.0763 ± 0.003 | 0.1985 ± 0.010 | 0.1985 ± 0.010 | 0.0529 ± 0.002 | ~5–7 min |
| **BiLSTM (sequence baseline)** | 0.0911 ± 0.009 | 0.2300 ± 0.019 | 0.2300 ± 0.019 | 0.0629 ± 0.006 | ~8–10 min |

**Đọc bảng**:

1. **LightGCN dominates** trên CB12 — NDCG@20=0.2738, gấp **3.6× LSTM** (0.0763) và **3.0× BiLSTM** (0.0911).
2. **GNN family > Sequence family**: cả 3 mô hình GNN (LightGCN, HeteroSAGE bipartite, HeteroSAGE hetero) đều thắng LSTM/BiLSTM với gap > 50% NDCG.
3. **BiLSTM > LSTM** (+19% NDCG) — đúng kỳ vọng, bidirectional context giúp encode skill list/job description tốt hơn.
4. **Hetero schema** trên CB12 không cải thiện được (skill extraction từ noisy text → signal yếu); chỉ có lợi khi data đã rich như JobFlow.
5. **Wall time**: GNN nhanh hơn nhờ ID embedding nhỏ; LSTM/BiLSTM tốn time hơn do encode toàn bộ vocab + sequence length 200.

### 4.2. Argument: Vì sao chọn GNN không chọn LSTM/BiLSTM

**3 lý do bản chất**:

#### Lý do 1: GNN khai thác được collaborative signal, LSTM thì không

| Aspect | GNN (HeteroSAGE, LightGCN) | LSTM/BiLSTM |
|---|---|---|
| **Sử dụng tương tác user-item** | ✅ Có — propagation qua edges | ❌ Không — chỉ encode text độc lập |
| **Phát hiện "users like you applied to X"** | ✅ Tự nhiên qua 2-hop propagation | ❌ Phải bổ sung manual collaborative features |
| **Scale với dataset interaction lớn** | ✅ Mini-batch sampling | ❌ Phải concat + sequence learning, kém efficient |

**Trên CB12**: LightGCN (đơn giản nhất trong họ GNN) đạt NDCG@20=0.27 chỉ với id embedding + propagation, **vượt LSTM/BiLSTM** dù sequence model có toàn bộ text job description.

#### Lý do 2: GNN xử lý hetero schema natively, LSTM phải workaround

Trên dataset có rich schema (skill, seniority, location, company), GNN có thể model trực tiếp các quan hệ:

```
CV --[has_skill]--> Skill <--[requires_skill]-- Job
CV --[has_seniority]--> Senior <--[requires_seniority]-- Job
CV --[applied_to]--> Job
```

LSTM/BiLSTM phải convert hetero schema → text string → tokenize. Mất structure, dilute signal:
- "Senior position requiring Python and SQL" — LSTM phải học rằng "Senior" = seniority, "Python" = skill từ ngữ cảnh
- GNN biết trước "Python" là skill node, "Senior" là seniority node — không cần học lại

#### Lý do 3: GNN inductive ổn định hơn LSTM cho job recommendation production

| Scenario production | GNN advantage |
|---|---|
| New job posted hàng ngày | GNN inductive infer được embedding chỉ từ neighbor (skill, seniority); LSTM phải có text + train từ đầu |
| Cold-start CV | GNN aggregate từ skill node sang job; LSTM phải có CV text |
| Update graph topology realtime | GNN re-infer rẻ (chỉ vài node); LSTM phải re-tokenize + re-train |

### 4.3. Khi nào LSTM thắng?

**Honest acknowledgement**: LSTM/BiLSTM có thể thắng GNN trên:
- Pure text task không có collaborative data (vd: rank documents bằng query)
- Long sequence tasks (sentiment analysis từ long review)
- Cases mà text semantic dominate over collaborative pattern

Trong job-rec, cả 2 signal đều quan trọng → kết hợp tốt nhất là **GNN cho collaborative + pre-trained text embedding cho semantic** (đề xuất tại Section 2, ưu tiên 4).

### 4.4. Kết luận cho thesis

> **GNN (cụ thể là HeteroGraphSAGE) là lựa chọn đúng cho job-rec vì 3 lý do bản chất**:
> 1. Khai thác collaborative signal từ historical interactions
> 2. Native hetero schema modeling (CV-Skill-Job-Seniority graph)
> 3. Inductive learning phù hợp production (job/CV mới liên tục)
>
> **LSTM/BiLSTM thua trên cùng dataset CB12** vì bỏ qua collaborative signal — chỉ có text encoding không đủ để rank job-rec accurately.
>
> Tuy nhiên, kết quả của em (HeteroSAGE bipartite/hetero) cũng **thua LightGCN baseline** trên CB12 — chứng minh rằng **complexity không miễn phí**: phải có data đủ rich (như JobFlow với curated skill) thì hetero arch mới thắng. Đây là một **negative result có giá trị** trong thesis.

---

## Phụ lục

### A. Files evidence

| Note | Evidence files |
|---|---|
| 1 (justification) | `backend/results/{movielens, careerbuilder, jobflow_hetersage}/summary.json`, `backend/results/lightgcn/*_summary.json` |
| 2 (improvements) | `specs/006-multi-dataset-benchmark/phases.md` (roadmap) |
| 3 (application) | `backend/ml_service/inference/engine.py`, `backend/apps/matching/views.py` |
| 4 (GNN vs LSTM) | `backend/results/{lstm, bilstm}/careerbuilder_summary.json` (Phase 5 output) |

### B. Reproduce instructions

Mọi kết quả reproducible:
```bash
cd backend
.venv/bin/python scripts/train_careerbuilder.py --seed 42 --output results/careerbuilder/seed42.json
.venv/bin/python scripts/train_lightgcn.py --dataset careerbuilder --seed 42 --output results/lightgcn/careerbuilder_seed42.json
.venv/bin/python scripts/train_lstm.py --dataset careerbuilder --seed 42 --output results/lstm/careerbuilder_seed42.json
.venv/bin/python scripts/train_lstm.py --dataset careerbuilder --seed 42 --bilstm --output results/bilstm/careerbuilder_seed42.json
```

### C. Liên hệ + git history

- Repo: `/Users/huynam/Documents/PROJECT/jobflow-gnn/`
- Phases roadmap: `specs/006-multi-dataset-benchmark/phases.md`
- Commit history: `git log --oneline -- backend/ml_benchmark/`
