# JobFlow GNN — Slide Outline

> File này dùng để brief AI generate slides (Gamma / Beautiful.ai / Slidesgo / Canva).
> Mỗi slide ghi rõ: **Tiêu đề**, **Loại layout đề xuất**, **Nội dung chính (bullet)**, **Diagram / số liệu / chart**, **Speaker note**.
>
> Tổng: 9 sections · ~32 slides · ~20-25 phút thuyết trình.

---

## Section 0 — Cover & Agenda  (2 slides)

### Slide 0.1 — Title
- **Layout:** Cover full-bleed
- **Tiêu đề:** *JobFlow GNN — Hệ thống Matching CV ↔ Job dựa trên Graph Neural Network*
- **Phụ đề:** Đồ án tốt nghiệp · 2026
- **Sub-info:** Tên SV · Tên GVHD · Tên trường
- **Visual:** Background gradient navy → slate; ảnh ẩn dụ "graph + CV + job" mờ ở góc

### Slide 0.2 — Agenda
- **Layout:** Bullet list 1 cột, icon số 1-7
- **Nội dung:**
  1. Giới thiệu bài toán & lý do chọn đề tài
  2. Khảo sát giải pháp hiện có & vì sao chọn GNN
  3. Tổng quan kiến trúc hệ thống
  4. Pipeline xử lý dữ liệu (Extraction → Graph → Pairs → Labels)
  5. Mô hình: GNN + MLP Reranker
  6. Flow ranking 2-stage & các penalty
  7. Kết quả, demo, hướng phát triển

---

## Section 1 — Giới thiệu bài toán  (3 slides)

### Slide 1.1 — Bối cảnh
- **Layout:** Split 50/50 (text trái — số liệu phải)
- **Bullet:**
  - Thị trường tuyển dụng IT VN: **>200k vị trí mở/năm**, hàng triệu CV nộp
  - Recruiter mất trung bình **6–10 phút/CV** để screening thủ công
  - Job board hiện tại (TopCV, ITViec, LinkedIn) chủ yếu dùng **keyword matching** → kết quả thiếu chính xác
- **Số liệu nổi bật (số to góc phải):**
  - 75% CV bị reject vì matching sai
  - 60% recruiter dùng filter cứng (years + tech keyword) → bỏ sót ứng viên tốt

### Slide 1.2 — Bài toán cụ thể
- **Layout:** Diagram trung tâm + 3 box dưới
- **Diagram:**
  ```
  CV (text) ──▶  ?  ──▶ Top-K Jobs (ranked)
  ```
- **3 box mô tả:**
  - **Input:** CV dạng PDF/DOCX hoặc text
  - **Output:** Danh sách Job ranked theo độ phù hợp + giải thích (matched/missing skills, fit dimensions)
  - **Constraint:** Latency < 3s, ranking phải explainable
- **Key message:** Đây là bài toán **ranking** (sắp xếp), không phải classification (phù hợp/không)

### Slide 1.3 — Lý do chọn đề tài
- **Layout:** 4 quadrant (2×2)
- **Quadrant 1 — Tính ứng dụng:** Giải quyết pain point thật của HR & job seeker
- **Quadrant 2 — Tính học thuật:** GNN là hướng nghiên cứu hot 2023-2026, ít project sinh viên VN làm
- **Quadrant 3 — Khả thi:** Có dataset (LinkedIn crawl + CV thật), có open-source SDK (PyG)
- **Quadrant 4 — Mở rộng:** Có thể scale lên Job recommendation, talent search, skill gap analysis

---

## Section 2 — Khảo sát & Lý do chọn GNN  (4 slides)

### Slide 2.1 — Các hướng giải pháp
- **Layout:** Bảng so sánh 4 cột
- **Bảng:**

| Approach | Cách làm | Ưu điểm | Nhược điểm |
|---|---|---|---|
| Keyword/TF-IDF | Match từ khóa skill | Đơn giản, fast | Bỏ qua synonym, semantic |
| Cosine + Embedding (BERT) | So sánh vector text | Hiểu semantic | Không capture relation skill ↔ skill |
| Learning-to-Rank (XGBoost) | Feature engineering + GBDT | Explainable | Không tận dụng cấu trúc đồ thị |
| **GNN (chosen)** | Học embedding trên hetero-graph | Capture skill co-occurrence, transitive relation | Train phức tạp, cần label data |

### Slide 2.2 — Vì sao GNN? (Phần 1 — Cấu trúc dữ liệu là đồ thị)
- **Layout:** Diagram lớn ở giữa
- **Diagram:** Mini hetero-graph
  ```
  CV ──has_skill──▶ Skill ◀──requires──── Job
        ▲              │ relates_to              ▲
        │              ▼                          │
        └──── similar_profile ─── CV          requires_seniority
                                              ▼
                                         Seniority
  ```
- **Bullet (giải thích):**
  - CV–Skill–Job tự nhiên là quan hệ many-to-many → đồ thị
  - Skill–Skill có quan hệ co-occurrence (React thường đi với Redux, JavaScript)
  - Cosine/keyword **không capture** được "CV biết Vue → có thể học React nhanh"
  - GNN aggregates thông tin từ neighbor → embedding của CV giàu context hơn

### Slide 2.3 — Vì sao GNN? (Phần 2 — Lợi ích cụ thể)
- **Layout:** 3 column với icon
- **Column 1 — Semantic richness:**
  Skill embedding học được từ co-occurrence → "PostgreSQL ≈ MySQL" mà không cần ontology
- **Column 2 — Cold-start handling:**
  Job mới chỉ cần có skill → vẫn có embedding thông qua message passing
- **Column 3 — Explainability:**
  Có thể trace path: CV → skill X → job, dùng cho UI giải thích

### Slide 2.4 — Vì sao 2-stage (GNN retrieve + MLP rerank)?
- **Layout:** Diagram 2 box ngang + bảng
- **Diagram:**
  ```
  6,251 jobs  ─[Stage 1: GNN, fast]─▶  Top 200  ─[Stage 2: MLP, accurate]─▶  Top K
  ```
- **Lý do:**
  | Stage | Mục đích | Trade-off |
  |---|---|---|
  | GNN retrieve | Lọc 6k jobs → 200 candidates | Nhanh, recall cao |
  | MLP rerank | Sắp xếp 200 → K dùng 23 features | Chậm hơn nhưng precision cao |
- **Speaker note:** Đây là pattern chuẩn của recommendation system (Google, Pinterest, YouTube đều dùng 2-stage)

---

## Section 3 — Tổng quan kiến trúc  (2 slides)

### Slide 3.1 — Architecture diagram (1 slide full-bleed)
- **Layout:** Full image
- **Visual:** **Insert ảnh `architecture.png` đã export từ Excalidraw** (5 lanes: Raw Data → LLM Extraction → Graph DB → Training → Inference)
- **Caption ngắn:** "5 layers, từ raw text đến top-K ranked jobs"

### Slide 3.2 — Tech stack
- **Layout:** 4 cột (Backend / ML / Data / Frontend)
- **Backend:** Django REST Framework, PostgreSQL, Celery
- **ML:** PyTorch + PyG (HeteroSAGE), SentenceTransformers (`all-MiniLM-L6-v2`), scikit-learn (calibration)
- **Data / Pipeline:** LLM (GPT-4o / Claude) cho extraction & labeling, custom pair generator, hard negative mining
- **Frontend:** Next.js + Tailwind admin dashboard (recommend page có CV upload + drawer chi tiết)

---

## Section 4 — Pipeline xử lý dữ liệu  (5 slides)

### Slide 4.1 — Tổng quan dependency chain
- **Layout:** Vertical flow chart
- **Diagram:**
  ```
  1. CV batch extraction  ─┐
                            ├─▶ 3. Pair generation ─▶ 4. LLM labeling ─▶ 5. Train GNN ─▶ 6. Train MLP
  2. JD batch extraction  ─┘
  ```
- **Note:** Mỗi bước phụ thuộc bước trước → không skip được

### Slide 4.2 — LLM Extraction
- **Layout:** Split 50/50 (CV trái — JD phải)
- **CV side:**
  - Input: raw text (PDF/DOCX → text)
  - Output: `{role_category, seniority 0-5, skills + proficiency 1-5, experience_years, education}`
  - Rule: chỉ extract skills **explicit mention**, không infer từ title
- **JD side:**
  - Input: raw JD text (LinkedIn crawl)
  - Output: `{title, company, location, seniority 0-5*, skills + importance 1-5, exp_min/max, salary, degree}`
  - **Override rule (quan trọng):** title chứa `intern/fresher/trainee/co-op/thực tập` → seniority=0 cứng
- **Số liệu:** ~6,251 JDs · 364 CVs trong checkpoint hiện tại

### Slide 4.3 — Heterogeneous Graph
- **Layout:** Diagram graph + bảng node
- **Diagram:** (dùng Excalidraw graph slice)
- **Bảng node features:**

| Node | Dims | Features |
|---|---|---|
| CV | 386 | 384-d sentence embedding + experience_years + education_level |
| Job | 397 | 384-d embedding + salary_min/max norm + role_category one-hot (11) |
| Skill | 385 | 384-d embedding (skill name) + category |
| Seniority | 6 | One-hot (Intern=0 → Manager=5) |

- **Edge types:** has_skill, requires_skill, has_seniority, requires_seniority, relates_to (PMI), similar_profile (Jaccard ≥ 0.3), match / no_match

### Slide 4.4 — Pair Generation Strategy
- **Layout:** Bảng 3 cột + pie chart
- **Bảng:**

| Type | Cách chọn | Số lượng |
|---|---|---|
| high_overlap | Jaccard ≥ 0.5 + same role | ~1,505 |
| medium_overlap | Jaccard 0.2–0.5 + same/related role | ~2,178 |
| hard_negative | Stage-1 score ≥ 0.50 nhưng Jaccard < 0.35 | ~3,360 |
| random | Random CV × Job | ~3,495 |

- **Total:** **~11,565 pairs** (v2 dataset) · split 70/15/15 (train/val/test)
- **Pie chart bên phải:** show tỉ lệ 4 loại
- **Speaker note:** Hard negative mining là chìa khóa giúp model phân biệt cases khó

### Slide 4.5 — LLM Labeling
- **Layout:** 5 dimension cards + distribution chart
- **5 dimensions (mỗi card):**
  - `skill_fit` 0/1/2 — CV skills đáp ứng JD requirements?
  - `experience_fit` 0/1/2 — số năm có phù hợp?
  - `seniority_fit` 0/1/2 — seniority có khớp?
  - `domain_fit` 0/1/2 — role_category có khớp?
  - `overall` 0/1/2 — kết luận tổng (label chính)
- **Distribution chart (bar) — overall (v2 dataset, 11,565 pairs):**
  - 0 (not fit): 7,732 — 67%
  - 1 (suitable): 3,009 — 26%
  - 2 (strong): 824 — 7%
- **Note:** Class imbalance được xử lý bằng weighted loss

---

## Section 5 — Kiến trúc mô hình  (5 slides)

### Slide 5.1 — Tổng quan 2 model
- **Layout:** 2 box ngang
- **Box 1 — GNN (HeteroSAGE):** Học embedding nodes + link prediction
- **Box 2 — MLP Reranker:** Ordinal 3-class classifier trên 23 features
- **Tagline:** "GNN học `representation`, MLP học `ranking`"

### Slide 5.2 — GNN Architecture (HeteroSAGE)
- **Layout:** Architecture diagram dọc
- **Diagram:**
  ```
  HeteroData (CV/Job/Skill/Seniority + 9 edge types)
         │
         ▼
  HeteroSAGEConv layer 1  (hidden=256)
         │ ReLU + Dropout
         ▼
  HeteroSAGEConv layer 2  (hidden=256)
         │ ReLU + Dropout
         ▼
  HeteroSAGEConv layer 3  (hidden=256)
         │
         ▼
  Output embeddings: CV, Job, Skill ∈ R^256
         │
         ▼
  MLPDecoder: concat([CV_emb, Job_emb]) → Linear → match score
  ```
- **Loss:** BPR (Bayesian Personalized Ranking) — `−logσ(pos_score − neg_score)` trên (match vs negative-sampled)
- **Training:** Adam, lr=1e-3, early stopping (patience=10)
- **Note:** Default config trong trainer là 2 layers/hidden=128, nhưng checkpoint hiện tại train với 3 layers/hidden=256

### Slide 5.3 — MLP Reranker Architecture
- **Layout:** Diagram + loss formula
- **Diagram:**
  ```
  Input: 23 features (per CV-Job pair)
       │
       ▼
  Linear(23 → 64) + ReLU + Dropout(0.2)
       │
       ▼
  Linear(64 → 64) + ReLU + Dropout(0.2)
       │
       ├─▶ main_head: Linear(64 → 3)   ← overall ordinal 3-class
       └─▶ aux_heads × 4: Linear(64 → 3) ← skill_fit, exp_fit, sen_fit, domain_fit
  ```
- **Score formula (highlight box):**
  $$score = E[class] = \frac{0 \cdot p_0 + 1 \cdot p_1 + 2 \cdot p_2}{2} \in [0, 1]$$
- **Loss:** CrossEntropy (main) + 0.3 × sum(CE for aux heads)
- **Calibration:** Platt scaling sau khi train: `a = 1.016, b = -1.078`

### Slide 5.4 — 23 Features (chia 4 nhóm)
- **Layout:** 4 column với icon nhóm
- **Group 1 — Text/Skill similarity (4):** text_similarity, skill_overlap_jaccard, skill_overlap_weighted, semantic_skill_overlap
- **Group 2 — Skill counting (5):** missing_required_count, missing_required_ratio, matched_skill_count, total_job_skills, skill_coverage_ratio
- **Group 3 — Seniority/Role/Exp (7):** seniority_distance, seniority_score, role_penalty, experience_years, cv_skill_count, skill_specificity, experience_gap
- **Group 4 — Stage 1 signals & edge cases (7):** stage1_score, gnn_score, gnn_rank, must_have_cap_triggered, edge_case_penalty_triggered, role_category_match, tool_ratio
- **Speaker note:** Trọng số 23 features được **học từ data**, không hardcode

### Slide 5.5 — Vì sao chọn ordinal 3-class thay vì binary/regression?
- **Layout:** Bảng so sánh 3 approach
- **Bảng:**

| Approach | Loss | Vấn đề |
|---|---|---|
| Binary (fit/not-fit) | BCE | Mất thông tin "strong" vs "suitable" → ranking không tốt |
| Regression (score 0–1) | MSE | Label LLM rời rạc → noise cao, khó converge |
| **Ordinal 3-class (chosen)** | CE + ordinal | Tận dụng thứ bậc 0<1<2, expected value cho score mượt |

- **Kết quả:** AUC tăng từ 0.79 (binary) → **0.876 (ordinal)** — improvement +8.7 điểm

---

## Section 6 — Flow Ranking 2-Stage  (5 slides)

### Slide 6.1 — Sequence diagram
- **Layout:** Sequence diagram dạng swim-lane
- **Diagram:**
  ```
  User ──upload CV──▶ API ──parse──▶ LLM Extractor ──structured CV──▶ Engine
                                                                          │
                                                          Stage 1 (GNN) ──┤
                                                          Stage 2 (MLP) ──┤
                                                          Penalties ─────┘
                                                                  │
  User ◀──top-K + explanations──── API ◀────────────────────────────┘
  ```

### Slide 6.2 — Stage 1: Retrieve top 50
- **Layout:** Formula box lớn + giải thích
- **Formula (highlight):**
  $$score_{stage1} = 0.55 \cdot GNN + 0.30 \cdot skill\_overlap + 0.15 \cdot seniority$$
- **Trong đó:**
  - `GNN_score = 0.6 · gnn_decode(cv_emb, job_emb) + 0.4 · cosine(cv_text, job_text)`
  - `skill_overlap` = weighted Jaccard (theo importance) + PMI bonus (×0.6) cho related skills
  - `seniority_score = max(0, 1 - |cv_sen - job_sen| × 0.4)`
- **Note:** Trọng số `0.55/0.30/0.15` là **hardcode heuristic**, chỉ dùng để retrieve

### Slide 6.3 — Stage 2: Rerank với MLP
- **Layout:** Diagram + flow
- **Diagram:**
  ```
  Top 50 candidates
        │
        ▼
  Extract 23 features cho mỗi pair
        │
        ▼
  MLP forward → softmax 3-class
        │
        ▼
  score = E[class] = (0·p₀ + 1·p₁ + 2·p₂) / 2
        │
        ▼
  Apply penalties (next slide)
        │
        ▼
  Sort → Top K (mặc định K=10)
  ```

### Slide 6.4 — Post-rerank Penalties
- **Layout:** Bảng penalty rules + visual examples
- **Bảng:**

| Tình huống | Multiplier | Label |
|---|---|---|
| `cv_exp < job_exp_min` (thiếu năm KN) | × 0.40 | `experience_fit = weak` |
| `cv_exp − job_exp_min > 3yr` (overqual về exp) | × 0.85 | `experience_fit = weak` |
| `job_seniority − cv_seniority ≥ 2` (thiếu cấp) | × 0.70 | `seniority_fit = weak` |
| `cv_seniority − job_seniority ≥ 2` (overqual cấp) | × 0.75 | `seniority_fit = weak` |
| Role mismatch (cv_role ≠ job_role) | giảm nhẹ | — |
| Must-have skill thiếu (importance ≥ 4) | giảm theo số thiếu | — |

- **Example bottom:** "CV 2 năm × Job yêu cầu 5+ năm → score × 0.40 → tụt hạng"

### Slide 6.5 — Output API Response
- **Layout:** JSON code block + ảnh UI bên phải
- **JSON sample:**
  ```json
  {
    "job_id": 1234,
    "score": 0.82,
    "match_level": "strong",
    "eligible": true,
    "matched_skills": ["react", "typescript", "redux"],
    "missing_skills": ["next.js"],
    "dim_scores": {
      "skill_fit": "good",
      "experience_fit": "good",
      "seniority_fit": "good",
      "domain_fit": "good"
    },
    "title": "Senior Frontend Developer",
    "company": "ABC Corp",
    "salary_min": 25000000, "salary_max": 40000000
  }
  ```
- **Visual phải:** Screenshot recommend page (job card + drawer)

---

## Section 7 — Kết quả & Đánh giá  (4 slides)

### Slide 7.1 — Metrics tổng quan
- **Layout:** 4 metric card lớn (KPI tiles)
- **Cards:**
  - **AUC-ROC:** 0.876
  - **NDCG@5:** 1.000
  - **MRR:** 1.000
  - **Calibrated reranker:** ECE < 0.05
- **Subtitle:** "Test set: 15% của 11,611 pairs · 1,742 pairs"

### Slide 7.2 — Lịch sử cải tiến qua các tuần
- **Layout:** Line chart (AUC theo tuần) + bảng
- **Bảng:**

| Tuần | AUC | Labels | Reranker | Ghi chú |
|---|---|---|---|---|
| 1 | 0.550 | ~2,000 | None | Synthetic baseline |
| 2 | 0.712 | 9,889 | Rule-based | Real data |
| 9 | 0.701 | 9,889 | Rule-based | Fix early stopping |
| 10 (b89) | 0.790 | 5,206 | Binary MLP | LLM labels (biased) |
| 10 (v2) | 0.786 | 11,565 | Binary MLP 81.2% | Dataset cân bằng |
| **11** | **0.876** | **11,611** | **Ordinal 3-class** | 23 features, intern fix |

- **Chart:** Line tăng từ 0.55 → 0.876 (highlight bước nhảy week 10→11)

### Slide 7.3 — Ranking quality theo domain
- **Layout:** Bảng + bar chart ngang
- **Bảng:**

| Domain | Jobs trong DB | Quality |
|---|---|---|
| Frontend | 746 | Excellent |
| QA | 630 | Excellent |
| Fullstack | 868 | Good |
| Data ML | 515 | Good |
| DevOps | 492 | Medium |
| Backend | 373 | Medium (ít data) |
| Design | 252 | Medium |
| BA | 216 | Medium |
| Mobile | 149 | Weak (quá ít data) |
| Data Eng | 147 | Weak (quá ít data) |

- **Insight:** Quality tỉ lệ thuận với data size → cần crawl thêm Mobile/Data Eng

### Slide 7.4 — Demo / Screenshots
- **Layout:** 2-3 ảnh screenshot lớn
- **Ảnh đề xuất:**
  1. **Trang upload CV** (form + sample)
  2. **Top K results** (job cards với match_level badge)
  3. **Drawer chi tiết** (skills sorted by importance, dim_scores, description, JD source URL)

---

## Section 8 — Hạn chế & Hướng phát triển  (3 slides)

### Slide 8.1 — Hạn chế hiện tại
- **Layout:** 5 row với icon warning
- **Bullet:**
  - Stage-1 weights hardcode (`0.55/0.30/0.15`) — chưa học từ data
  - Mobile / Data Eng data quá ít (<150 jobs) → ranking yếu
  - LLM labeling cost cao (~$0.01/pair) → khó scale lên 100k+ pairs
  - Chưa có A/B test với user thật
  - Engine load checkpoint từ `jobs.json` → cần patch khi update DB

### Slide 8.3 — Đóng góp của đề tài
- **Layout:** 3 box icon
- **Đóng góp 1 — Học thuật:**
  Áp dụng GNN heterogeneous + ordinal reranker cho recruitment matching — chưa nhiều paper VN
- **Đóng góp 2 — Thực tiễn:**
  System hoàn chỉnh end-to-end (data → train → API → admin UI), có thể deploy production
- **Đóng góp 3 — Open source:**
  Pipeline labeling + pair generation reusable cho domain khác (e-commerce, education...)

---

## Section 9 — Q&A  (1 slide)

### Slide 9.1 — Thank You / Q&A
- **Layout:** Cover style đơn giản
- **Tiêu đề:** *Cảm ơn thầy cô — Q&A*
- **Sub:** Github repo + email + (optional) demo URL
- **Visual:** Background mờ của architecture diagram

---

## Phụ lục — Backup slides (chuẩn bị cho câu hỏi)

### Backup 1 — Hard Negative Mining chi tiết
- Cách `mine_hard_negatives.py` quét toàn bộ CV×Job pool, score qua Stage-1, lấy pairs model nhầm để đưa vào PairQueue → LLM label

### Backup 2 — SkillNormalizer
- 218 canonical identifiers, alias map ("React.js" → "react", "PostgreSQL" → "postgresql")
- Skill không map được → bỏ qua

### Backup 3 — Checkpoint structure
```
checkpoints/gnn_v2/
├── model.pt            # GNN weights (encoder + decoder)
├── graph.pt            # HeteroData snapshot
├── reranker.pt         # MLP weights
├── reranker_meta.json  # Feature names, normalization stats
├── jobs.json           # Job metadata (engine load từ đây, không từ DB)
├── calibration.json    # Platt scaling: a, b
└── metadata.json       # Training config + node dims + dataset counts
```

### Backup 4 — Tại sao không dùng BERT/LLM trực tiếp?
- Cost: BERT inference cho 6k jobs/CV ≈ 30s · LLM API ≈ $0.5/CV
- Không capture skill graph structure
- Không học từ feedback của LLM labeling (waste signal)

### Backup 5 — So sánh với commercial product
| Tiêu chí | TopCV | LinkedIn Recruiter | **JobFlow GNN** |
|---|---|---|---|
| Method | Keyword + filter | Embedding (proprietary) | **GNN + ordinal MLP** |
| Explainable | Không | Một phần | **Có (matched/missing skills, dim_scores)** |
| Open data | Không | Không | **Có (open dataset crawl)** |
