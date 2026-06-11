# JobFlow GNN — Slide Outline

> File này dùng để brief AI generate slides (Gamma / Beautiful.ai / Slidesgo / Canva).
> Mỗi slide ghi rõ: **Tiêu đề**, **Loại layout đề xuất**, **Nội dung chính (bullet)**, **Diagram / số liệu / chart**, **Speaker note**.
>
> Tổng: 9 sections · ~33 slides · ~20-25 phút thuyết trình.
> **Cập nhật 2026-06-11 — đồng bộ với hệ production (GNN v2)**. Nguồn số liệu: docs/codebase-knowledge/ (07, 11, 12).

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
  4. Pipeline dữ liệu: Extraction → Graph → Decision-boundary pairs → Agent labeling
  5. Mô hình: GNN (pretrain + finetune) + MLP Reranker
  6. Flow ranking 2-stage, trọng số tuned & gates
  7. Kết quả (2 bộ eval độc lập), hành trình cải tiến, demo, hướng phát triển

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
  - **Output:** Danh sách Job ranked theo độ phù hợp + giải thích (matched/missing skills, 4 chiều fit dạng điểm số 0-1)
  - **Constraint:** Latency < 3s, ranking phải explainable, **job mới crawl phải rank được không cần retrain**
- **Key message:** Đây là bài toán **ranking** (sắp xếp), không phải classification (phù hợp/không)

### Slide 1.3 — Lý do chọn đề tài
- **Layout:** 4 quadrant (2×2)
- **Quadrant 1 — Tính ứng dụng:** Giải quyết pain point thật của HR & job seeker (hệ chạy production cho workflow HR staffing nội bộ)
- **Quadrant 2 — Tính học thuật:** GNN là hướng nghiên cứu hot 2023-2026, ít project sinh viên VN làm
- **Quadrant 3 — Khả thi:** Có dataset (LinkedIn/Indeed/Adzuna crawl + CV thật), có open-source SDK (PyG)
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
| **GNN (chosen)** | Học embedding trên hetero-graph | Capture skill co-occurrence, transitive relation, **inductive với job mới** | Train phức tạp, cần label data |

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
  - Skill–Skill có quan hệ co-occurrence + semantic (React thường đi với Redux; Flask ≈ Django)
  - Cosine/keyword **không capture** được "CV biết Flask → làm được job Django"
  - GNN aggregates thông tin từ neighbor → embedding của CV giàu context hơn
- **Speaker note:** Năng lực "related-skill transfer" này được ĐO ĐƯỢC trong hệ: slice AUC 0.512 (model cũ, ngang đoán mò) → 0.705 (model hiện tại) trên 760 cặp chuyên biệt.

### Slide 2.3 — Vì sao GNN? (Phần 2 — Lợi ích cụ thể)
- **Layout:** 3 column với icon
- **Column 1 — Semantic richness:**
  Skill embedding học được từ co-occurrence + pretrain tự giám sát → "PostgreSQL ≈ MySQL" mà không cần ontology
- **Column 2 — Inductive (cold-start):**
  GraphSAGE là mô hình inductive: job mới crawl chỉ cần encode lại node (~60s cho 5.8k jobs) → **rank được ngay không cần retrain** — catalog "sống"
- **Column 3 — Explainability:**
  Trace path: CV → skill X → job; 4 chiều fit là công thức minh bạch tái lập được bằng tay

### Slide 2.4 — Vì sao 2-stage (hybrid retrieve + MLP rerank)?
- **Layout:** Diagram 2 box ngang + bảng
- **Diagram:**
  ```
  5,803 jobs ─[Stage 1: hybrid score, fast]─▶ Top 200 ─[Stage 2: MLP rerank ×23 features]─▶ Top K
  ```
- **Lý do:**
  | Stage | Mục đích | Trade-off |
  |---|---|---|
  | Hybrid retrieve (GNN+skill+seniority+domain) | Lọc 5.8k jobs → 200 candidates | Nhanh, recall cao |
  | MLP rerank | Sắp xếp 200 → K dùng 23 features | Chậm hơn nhưng precision cao |
- **Speaker note:** Pattern chuẩn của recommendation system (Google, Pinterest, YouTube đều dùng 2-stage). Thứ tự cuối = reranker × gates (đã sửa bug từng khiến sort cuối vô hiệu hoá reranker — A3).

---

## Section 3 — Tổng quan kiến trúc  (2 slides)

### Slide 3.1 — Architecture diagram (1 slide full-bleed)
- **Layout:** Full image
- **Visual:** **Insert ảnh `architecture.png` đã export từ Excalidraw** (5 lanes: Raw Data → LLM Extraction → Graph → Training → Inference)
- **Caption ngắn:** "5 layers, từ raw text đến top-K ranked jobs · job pool inductive hot-reload"

### Slide 3.2 — Tech stack
- **Layout:** 4 cột (Backend / ML / Data / Frontend)
- **Backend:** Django REST Framework, PostgreSQL, Celery (optional, fallback thread-pool)
- **ML:** PyTorch + PyG (HeteroGraphSAGE 256×3), SentenceTransformers (**paraphrase-multilingual-MiniLM-L12-v2** — đa ngữ, hỗ trợ job tiếng Việt), self-supervised pretrain, Platt calibration
- **Data / Pipeline:** LLM extraction (provider-agnostic) · **labeling bằng Claude agents** (rubric + pilot gate + agreement đo được) · decision-boundary pair generator · train remote GPU 1 lệnh
- **Frontend:** React + Vite + HeroUI admin dashboard (recommend page có CV upload + drawer chi tiết)

---

## Section 4 — Pipeline xử lý dữ liệu  (5 slides)

### Slide 4.1 — Tổng quan dependency chain
- **Layout:** Vertical flow chart
- **Diagram:**
  ```
  1. CV extraction (LLM)  ─┐
                            ├─▶ 3. Decision-boundary pair generation ─▶ 4. Agent labeling (pilot→scale→agreement)
  2. JD extraction (LLM)  ─┘                                                      │
                                                                                   ▼
                                              6. Train reranker ◀─ 5. Pretrain + finetune GNN
  ```
- **Note:** Mỗi bước phụ thuộc bước trước; chất lượng NHÃN quyết định trần của model (bài học lớn nhất của đề tài)

### Slide 4.2 — LLM Extraction
- **Layout:** Split 50/50 (CV trái — JD phải)
- **CV side:**
  - Input: raw text (PDF/DOCX → text)
  - Output: `{role_category, seniority 0-5, skills + proficiency 1-5, experience_years, education}`
  - Rule: chỉ extract skills **explicit mention**, không infer từ title
- **JD side:**
  - Input: raw JD text (LinkedIn/Indeed/Adzuna crawl)
  - Output: `{title, company, seniority 0-5 hoặc null, skills + importance 1-5, exp_min/max, salary, role_category 11 lớp}`
  - **Quality guards:** seniority null → suy từ experience_min (hết default MID bừa); skill không map catalog → **đếm + báo cáo** (hết drop âm thầm); cross-check seniority↔experience
- **Số liệu:** **5,803 active jobs** (sau dedup 733 trùng) · **366 CVs** · 1,898 job thiếu role đã được agent backfill

### Slide 4.3 — Heterogeneous Graph
- **Layout:** Diagram graph + bảng node
- **Diagram:** (dùng Excalidraw graph slice)
- **Bảng node features:**

| Node | Dims | Features |
|---|---|---|
| CV | 397 | 384-d **multilingual** embedding + exp_norm + edu_norm + **role one-hot (11)** |
| Job | 397 | 384-d embedding + salary_min/max norm + role one-hot (11) |
| Skill | 385 | 384-d embedding (skill name) + category |
| Seniority | 6 | One-hot (Intern=0 → Manager=5) |

- **Edge types:** has_skill (×proficiency), requires_skill (×importance), has/requires_seniority, relates_to (PMI + semantic cosine≥0.7), similar_to/similar_profile, match / no_match (label)
- **Guard:** graph build **raise lỗi** nếu 1 cặp (CV, job) mang cả match lẫn no_match — nhãn xung đột không bao giờ lọt vào training

### Slide 4.4 — Decision-Boundary Pair Generation (điểm khác biệt chính)
- **Layout:** Bảng + pie chart
- **Mở đầu (key message):** Nhãn cũ bị **thiên lệch skill, mù ranh giới nghề** (chỉ 2% negative cross-domain, 43% trong đó sai) → model học sai. Giải pháp: sinh cặp NHẮM VÀO RANH GIỚI QUYẾT ĐỊNH:

| Bucket | Điều kiện | Dạy model điều gì |
|---|---|---|
| cross_domain_hard_neg (32%) | skill overlap cao NHƯNG khác nghề | "Trùng skill ≠ hợp việc" (vụ Compositor) |
| related_skill_positive (20%) | overlap trực tiếp <0.15 nhưng expanded ≥0.5 | "Flask ≈ Django" — lợi thế của GNN |
| seniority_hard_neg (13%) | cùng nghề, lệch ≥2 bậc seniority | Junior ≠ Lead dù trùng skill |
| missing_must_have (10%) | thiếu ≥2 skill bắt buộc | Skill quan trọng ≠ skill phụ |
| boundary_medium (15%) | overlap 0.08-0.2 | Hiệu chuẩn vùng giữa thang điểm |
| anchors (10%) | random + positive dễ | Neo thang đo |

- **Total:** dataset v4 = **12,084 nhãn unique** (dedup latest-wins) · positive 33.3% · split 70/15/15 **stratified theo bucket**

### Slide 4.5 — Agent Labeling (thay LLM API)
- **Layout:** Flow 4 bước + 2 metric card
- **Flow:** Rubric 5 chiều (có rule cứng + worked examples) → **Pilot 180 cặp** (gate: phân phối từng bucket phải khớp kỳ vọng — bắt được 2 lỗi rubric trước khi scale) → **Scale 151 chunk** agents song song → **Double-label 200 cặp** đo đồng thuận
- **Metric cards:**
  - **Inter-rater agreement: 87%** (overall exact) · domain per-dim 98.5%
  - **0 vi phạm rule cứng** sau enforcement cơ học · graph 0 conflict
- **5 dimensions:** `skill_fit` · `experience_fit` · `seniority_fit` · `domain_fit` · `overall` (0/1/2; rule cứng: domain=0 → overall=0; skill=0 → overall=0)
- **Speaker note:** Chất lượng nhãn ĐO ĐƯỢC (pilot audit + agreement) thay vì tin LLM mù quáng — đây là phương pháp luận, không chỉ công cụ.

---

## Section 5 — Kiến trúc mô hình  (5 slides)

### Slide 5.1 — Tổng quan 2 model
- **Layout:** 2 box ngang
- **Box 1 — GNN (HeteroGraphSAGE):** pretrain tự giám sát → finetune BPR; học representation + link prediction
- **Box 2 — MLP Reranker:** Ordinal 3-class trên 23 features; quyết định thứ tự cuối
- **Tagline:** "GNN học `representation`, MLP học `ranking`"

### Slide 5.2 — GNN: Pretrain + Finetune (2 giai đoạn)
- **Layout:** Architecture diagram dọc + box pretrain
- **Giai đoạn 1 — Self-supervised pretrain (không cần nhãn):**
  Link prediction trên cạnh has_skill/requires_skill toàn đồ thị (che 30% cạnh, đoán lại bằng dot-product, BCE) → backbone học "skill nào đi với nghề nào" từ TOÀN BỘ 5.8k jobs (link-acc 0.80)
- **Giai đoạn 2 — Finetune BPR trên nhãn:**
  ```
  HeteroData (CV/Job/Skill/Seniority + 9 edge types, multilingual embeddings)
         │
  3 × HeteroSAGEConv (hidden=256, ReLU, Dropout)
         │
  Embeddings ∈ R^256 → MLPDecoder: concat([CV, Job]) → match score
  ```
- **Loss:** BPR `−logσ(pos − neg)` + hard-negative curriculum; early-stop theo blend val-AUC + related-slice AUC
- **Speaker note:** Vì sao pretrain? 366 CV là supervision nhỏ; cấu trúc đồ thị thì dồi dào — "bồi cấu trúc trước, supervised sau".

### Slide 5.3 — MLP Reranker Architecture
- **Layout:** Diagram + loss formula
- **Diagram:**
  ```
  Input: 23 features (per CV-Job pair)
       │
  Linear(23 → 64) + ReLU + Dropout ×2
       │
       ├─▶ main_head: Linear(64 → 3)   ← overall ordinal 3-class
       └─▶ aux_heads × 4: Linear(64 → 3) ← skill, exp, seniority, domain fit
  ```
- **Score formula (highlight box):**
  $$score = E[class] = \frac{0 \cdot p_0 + 1 \cdot p_1 + 2 \cdot p_2}{2} \in [0, 1]$$
- **Loss:** CrossEntropy (main) + 0.3 × Σ CE(aux) · Platt calibration sau train
- **Quy tắc vận hành (A14):** reranker PHẢI train với đúng hybrid weights đang serve (feature stage1_score phụ thuộc weights) — engine tự cảnh báo nếu lệch
- **Accuracy:** 0.706 (3-class, nhãn sạch v4)

### Slide 5.4 — 23 Features (chia 4 nhóm)
- **Layout:** 4 column với icon nhóm
- **Group 1 — Text/Skill similarity (4):** text_similarity, skill_overlap_jaccard, skill_overlap_weighted, semantic_skill_overlap
- **Group 2 — Skill counting (5):** missing_required_count, missing_required_ratio, matched_skill_count, total_job_skills, skill_coverage_ratio
- **Group 3 — Seniority/Role/Exp (7):** seniority_distance, seniority_score, role_penalty, experience_years, cv_skill_count, skill_specificity, experience_gap
- **Group 4 — Stage 1 signals & edge cases (7):** stage1_score, gnn_score, gnn_rank, must_have_cap_triggered, edge_case_penalty_triggered, role_category_match, tool_ratio
- **Speaker note:** Trọng số 23 features được **học từ data**, không hardcode

### Slide 5.5 — Vì sao ordinal 3-class thay vì binary/regression?
- **Layout:** Bảng so sánh 3 approach
- **Bảng:**

| Approach | Loss | Vấn đề |
|---|---|---|
| Binary (fit/not-fit) | BCE | Mất thông tin "strong" vs "suitable" → ranking không tốt |
| Regression (score 0–1) | MSE | Label rời rạc → noise cao, khó converge |
| **Ordinal 3-class (chosen)** | CE + ordinal | Tận dụng thứ bậc 0<1<2, expected value cho score mượt |

- **Speaker note:** Nhãn 3 mức đến thẳng từ rubric labeling (0/1/2) — model và ground truth nói cùng một ngôn ngữ.

---

## Section 6 — Flow Ranking 2-Stage  (5 slides)

### Slide 6.1 — Sequence diagram
- **Layout:** Sequence diagram dạng swim-lane
- **Diagram:**
  ```
  User ──upload CV──▶ API ──parse──▶ LLM Extractor ──structured CV──▶ Engine
                                                                          │
                                                  Stage 1 (hybrid 4-term) ┤
                                                  Stage 2 (MLP rerank)    ┤
                                                  Gates (domain/exp/sen)  ┘
                                                                  │
  User ◀──top-K + 4 dim scores + skills──── API ◀───────────────────┘
  ```

### Slide 6.2 — Stage 1: Hybrid retrieve top 200 (trọng số TUNED từ data)
- **Layout:** Formula box lớn + giải thích
- **Formula (highlight):**
  $$score_{stage1} = 0.30 \cdot GNN + 0.20 \cdot skill + 0.10 \cdot seniority + 0.40 \cdot domain$$
- **Trong đó:**
  - `GNN = 0.6 · gnn_decode(cv_emb, job_emb) + 0.4 · cosine(cv_text, job_text)`
  - `skill` = weighted overlap theo importance + related-skill ×0.6 (PMI/semantic)
  - `seniority = max(0, 1 − |Δsen| × 0.4)` · `domain` = role match 1.0 / related 0.7 / unknown 0.5 / mismatch 0.0
- **Key message:** Trọng số **KHÔNG hardcode** — grid-search trên nhãn sạch với constrained objective (max role-NDCG s.t. label-AUC ≥ 0.85·max). **α=0.30: GNN đồng-trụ-cột với domain** — kết quả của việc sửa đúng nút thắt (embedding đa ngữ); 3 lần tune trước chỉ ra 0.05-0.15.

### Slide 6.3 — Stage 2: Rerank với MLP
- **Layout:** Diagram + flow
- **Diagram:**
  ```
  Top 200 candidates
        │
  Extract 23 features cho mỗi pair
        │
  MLP forward → softmax 3-class → score = E[class]/2
        │
  × penalty product (gates — slide sau)
        │
  Sort theo (reranker × gates) → Top K · display score remap monotonic
  ```
- **Speaker note:** Thứ tự cuối THUỘC VỀ reranker×gates — từng có bug sort theo điểm hiển thị đè mất reranker (A3), đã fix + có test chống tái diễn.

### Slide 6.4 — Gates (penalty product — nhân vào cả thứ tự lẫn điểm)
- **Layout:** Bảng penalty rules + visual examples
- **Bảng:**

| Tình huống | Multiplier | Cơ sở |
|---|---|---|
| **Khác nghề (domain_fit = 0)** | **× 0.40** | Thực thi rule ground-truth `domain=0 → not match` |
| `cv_exp < job_exp_min` (thiếu năm KN) | × 0.40 | under-qualified |
| `cv_exp − job_exp_min > 3yr` | × 0.85 | over-qualified nhẹ |
| `job_sen − cv_sen ≥ 2` (thiếu cấp) | × 0.70 | seniority gap |
| `cv_sen − job_sen ≥ 2` (overqual cấp) | × 0.75 | seniority gap |
- **Example bottom:** "Backend CV × job Compositor (VFX) → domain gate ×0.40 → tụt khỏi top" — chính là ca lỗi nổi tiếng nhất đã được giải
- **Speaker note:** Gate không phải magic number — mỗi gate phản chiếu một rule trong rubric nhãn.

### Slide 6.5 — Output API Response
- **Layout:** JSON code block + ảnh UI bên phải
- **JSON sample:**
  ```json
  {
    "job_id": 1234,
    "score": 0.82,
    "match_level": "strong",
    "matched_skills": ["react", "typescript", "redux"],
    "missing_skills": ["nextjs"],
    "dim_scores": {
      "skill_fit": 0.85,
      "experience_fit": 1.0,
      "seniority_fit": 0.7,
      "domain_fit": 1.0
    },
    "title": "Senior Frontend Developer",
    "company": "ABC Corp"
  }
  ```
- **Note:** 4 chiều là **điểm số 0-1 từ công thức minh bạch** (tái lập được bằng tay) — không phải nhãn mờ good/ok/weak
- **Visual phải:** Screenshot recommend page (job card + drawer)

---

## Section 7 — Kết quả & Đánh giá  (5 slides)

### Slide 7.1 — Metrics tổng quan (đo TRUNG THỰC per-CV)
- **Layout:** 4 metric card lớn (KPI tiles)
- **Cards:**
  - **AUC-ROC: 0.860** (test, per-CV trên 240 CV)
  - **NDCG@10: 0.894** · MRR: 0.862
  - **Eval định tính: 20/20 (100%)** top-1 đúng nghề — trên CẢ 2 bộ test độc lập
  - **Related-skill AUC: 0.705** (từ 0.512 — năng lực GNN đo được)
- **Subtitle:** "Test set: 15% của 12,084 nhãn sạch · metrics per-CV (đã loại artifact NDCG=1.0 ảo của cách đo cũ)"

### Slide 7.2 — Hành trình cải tiến (câu chuyện chính của đề tài)
- **Layout:** Line chart (eval on-domain %) + bảng mốc
- **Bảng:**

| Mốc | Eval on-domain | Việc làm | Bài học |
|---|---|---|---|
| Tune trên nhãn bẩn | lạc nghề (VFX top-1) | grid-search AUC | metric đúng + nhãn sai = trọng số sai |
| Audit toàn chuỗi | — | 20 lỗ hổng A1-A20 | tìm gốc rễ thay vì vá ngọn |
| Đợt 0: fix 7 bug nền | **75%** | baseline trung thực đầu tiên | đo đúng trước khi cải thiện |
| Đợt 1: relabel 12k nhãn | — | agent labeling + pilot gate, agreement 87% | chất lượng nhãn đo được |
| Đợt 2: retrain + domain gate | **90%** | kiến trúc 2 tầng chạy đúng | gate = thực thi rule nhãn |
| Đợt 3: role backfill + taxonomy | **100%** | 1.9k job role + fix taxonomy lệch | data-ops cũng là ML |
| **GNN v2: embedding đa ngữ + pretrain** | **100%** (+ held-out 100%) | 8 thí nghiệm có kiểm soát | **nút thắt là INPUT, không phải thuật toán** |

- **Chart:** đường 75 → 90 → 100, kèm chú thích AUC pipeline 0.813 → **0.860**

### Slide 7.3 — Câu chuyện GNN 2 hồi (điểm nhấn học thuật)
- **Layout:** 2 panel trái-phải
- **Panel trái — Hồi 1 (negative result trung thực):**
  - GNN decode AUC 0.512 trên slice related-skill = ngang đoán mò (3 phép đo độc lập hội tụ)
  - Tune ra α=0.05 → trung thực sửa mục tiêu thay vì ép số
- **Panel phải — Hồi 2 (giải được bằng thí nghiệm có kiểm soát):**
  - 6 thí nghiệm training/kiến trúc (aux head, curriculum, skill-rel loss, pretrain, GATv2) → đều kẹt trần ~0.55
  - Đổi embedding tiếng-Anh → **đa ngữ**: slice 0.512 → **0.734** ngay lập tức
  - Bản production (đa ngữ + pretrain): re-tune **α = 0.30** — GNN thật sự gánh tín hiệu
- **Key message:** "Khi mọi can thiệp thuật toán kẹt cùng một trần — nghi chất lượng tín hiệu đầu vào"

### Slide 7.4 — Validation 2 lớp (chống overfit harness)
- **Layout:** Bảng 2 cột + ví dụ
- **Bảng:**

| Bộ test | Kết quả |
|---|---|
| Harness 20 CV cố định (dùng trong vòng lặp tune) | 20/20 (100%) · on_domain@5 = 1.00 |
| **Held-out 20 persona MỚI** (Flask, Svelte, SRE, DBA, QA, fresh-grad…) | **20/20 (100%) · on_domain@5 = 1.00** |

- **Ca chứng minh năng lực:**
  - **Flask CV → Python/Django Developer top-1** (related-skill transfer — đúng cái GNN được sinh ra để làm)
  - Fresh grad 0 kinh nghiệm → Internship/Graduate roles (gates hoạt động tinh tế)
  - QA CV → Software Testing/QA Specialist (sau khi bổ sung suy luận role qa/ba/design)

### Slide 7.5 — Demo / Screenshots
- **Layout:** 2-3 ảnh screenshot lớn
- **Ảnh đề xuất:**
  1. **Trang upload CV** (form + sample)
  2. **Top K results** (job cards với match score + "Why it matches" accordion 4 chiều)
  3. **Drawer chi tiết** (skills sorted by importance, dim_scores 0-1, description, JD source URL)

---

## Section 8 — Hạn chế & Hướng phát triển  (3 slides)

### Slide 8.1 — Hạn chế hiện tại (trung thực)
- **Layout:** 5 row với icon warning
- **Bullet:**
  - **366 CV** là supervision nhỏ — trần kế tiếp cần thêm CV (import dataset public + augmentation)
  - Job ngách (Flutter, Unity, DBA) còn ít trong pool → match hợp lệ nhưng chất lượng trung bình — cần crawl thêm
  - Nhãn do AI agents (có gate + agreement 87%) — chưa có chuyên gia HR thẩm định độc lập
  - Chưa có A/B test với user thật
  - Global-decode AUC của model BPR là thước méo (offset giữa CV) — phải dùng per-CV metrics

### Slide 8.2 — Hướng phát triển
- **Layout:** Timeline 3 mốc
- **Ngắn hạn:** Crawl thêm job ngách; thẩm định nhãn bởi chuyên gia HR; A/B test nội bộ
- **Trung hạn:** Tăng CV vài bậc (public datasets + augmentation, re-label bằng pipeline agent có sẵn); thử edge-aware conv (GATv2 + edge features)
- **Dài hạn:** Feedback loop từ kết quả apply thật → online learning; mở rộng sang talent search & skill-gap analysis

### Slide 8.3 — Đóng góp của đề tài
- **Layout:** 3 box icon
- **Đóng góp 1 — Học thuật:**
  GNN heterogeneous + ordinal reranker cho recruitment matching; **câu chuyện negative-result-được-giải** bằng 8 thí nghiệm có kiểm soát (nút thắt = embedding đa ngữ) — mẫu mực phương pháp thực nghiệm
- **Đóng góp 2 — Phương pháp luận data:**
  Pipeline labeling-by-agents với chất lượng đo được (decision-boundary buckets + pilot gate + inter-rater agreement) — tái sử dụng được cho domain khác
- **Đóng góp 3 — Thực tiễn:**
  Hệ end-to-end production (crawl → extraction → graph → train remote 1 lệnh → API → admin UI), inductive với job mới, mọi con số truy được nguồn gốc, guards tự động chống regression

---

## Section 9 — Q&A  (1 slide)

### Slide 9.1 — Thank You / Q&A
- **Layout:** Cover style đơn giản
- **Tiêu đề:** *Cảm ơn thầy cô — Q&A*
- **Sub:** Github repo + email + (optional) demo URL
- **Visual:** Background mờ của architecture diagram

---

## Phụ lục — Backup slides (chuẩn bị cho câu hỏi)

### Backup 1 — Vì sao trọng số α=0.30/β=0.20/γ=0.10/δ=0.40?
- Grid-search bước 0.05 trên simplex 4 chiều, nhãn sạch v4
- Objective *balanced*: max role-NDCG@10 s.t. label-AUC ≥ 0.85·max và δ ≤ 0.4 (chống degenerate δ=1.0)
- Kết quả: label-AUC 0.786 · role-NDCG 0.994 · AUC-max winner (0.20/0.75/0.05/0) thua xa về role-NDCG (0.819)
- Lịch sử α: 0.05 (model cũ) → 0.30 (sau embedding đa ngữ) — bằng chứng GNN "thông minh lên" đo được

### Backup 2 — Vòng đời metric (3 hồi — nếu giám khảo hỏi sâu)
1. label-AUC trên nhãn bẩn → trọng số thiên skill → lạc nghề
2. role-NDCG chữa được nhưng degenerate nếu không constrain (δ=1.0)
3. Nhãn sạch tự encode domain → role-NDCG bão hoà 1.0 → bộ thước cuối = label-AUC sạch + slice AUC + eval định tính (và AUC pairwise toàn cục ≠ chất lượng retrieve top-K)

### Backup 3 — Checkpoint structure
```
checkpoints/latest/
├── model.pt            # GNN weights (pretrain→finetune, multilingual)
├── graph.pt            # HeteroData snapshot
├── reranker.pt         # MLP weights (trained with serving weights — A14)
├── reranker_meta.json  # feature names + trained_with_weights (guard)
├── calibration.json    # Platt scaling
└── metadata.json       # node dims + hybrid_weights (single source of truth)
checkpoints/job_pool/   # snapshot pool 5.8k jobs (inductive, hot-reload, model_signature guard)
```

### Backup 4 — Tại sao không dùng BERT/LLM trực tiếp để rank?
- Cost: LLM API ≈ $0.5/CV cho 5.8k jobs; BERT cross-encoder ~30s/CV
- Không capture skill graph structure, không inductive
- LLM dùng đúng chỗ: extraction + labeling (offline, có gate chất lượng), không phải ranking online

### Backup 5 — So sánh với commercial product
| Tiêu chí | TopCV | LinkedIn Recruiter | **JobFlow GNN** |
|---|---|---|---|
| Method | Keyword + filter | Embedding (proprietary) | **GNN inductive + tuned hybrid + ordinal MLP** |
| Explainable | Không | Một phần | **Có (matched/missing skills, 4 dim scores công thức)** |
| Job mới | Re-index | ? | **Inductive — rank ngay không retrain** |
| Chất lượng đo được | Không công bố | Không công bố | **2 bộ eval 100% + agreement nhãn 87% công khai** |

### Backup 6 — Hard rules trong rubric nhãn (nếu hỏi về ground truth)
- skill_fit=0 → overall=0 · domain_fit=0 → overall=0
- Job cao hơn CV ≥2 bậc → overall=0; CV cao hơn job ≥2 bậc → overall≤1 (bất đối xứng)
- Transferable skill: Flask≈Django, Vue≈React... được nửa tín chỉ
- seniority_fit là công thức thuần: |Δ|≥2→0, |Δ|=1→1, else 2

### Backup 7 — Guards tự động (nếu hỏi về độ tin cậy vận hành)
- Graph conflict → raise khi build · Reranker↔weights skew (A14) → warn khi load
- Skill-drop khi sync → đếm + báo cáo · Pool snapshot ↔ model signature → reject khi lệch
- Serving dedup (title+company) · eval_matching = regression guard chạy 1 lệnh
