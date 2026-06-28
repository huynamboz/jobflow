# `ml_service` — Giải thích chi tiết các thành phần (để trình bày)

Tài liệu này mô tả toàn bộ lõi học máy của hệ thống (`backend/ml_service/`, ~10.000
dòng). Mọi con số đều **lấy từ mã nguồn + checkpoint thật** (`checkpoints/latest/`),
không phải giá trị mặc định trong code. Đọc theo thứ tự để nắm được *luồng dữ liệu*
từ lúc có CV/job đến lúc ra kết quả so khớp.

> **Số liệu production then chốt (đọc trước):**
> - GNN: backbone **HeteroGraphSAGE**, `hidden=256`, `num_layers=3`, embedding đa ngữ 384 chiều.
> - Node feature: CV **397**, job **397**, skill **385**, seniority **6**.
> - Trọng số hybrid (4 thành phần): **α=0,30 (GNN) · β=0,20 (kỹ năng) · γ=0,10 (cấp bậc) · δ=0,40 (lĩnh vực)**.
> - Calibration Platt: `a=7,96`, `b=−2,45`; ngưỡng đủ điều kiện `P ≥ 0,50`.
> - Pool huấn luyện: 366 CV, 6.251 job. Pool phục vụ live: ~8.930 job.
>
> *Lưu ý:* các giá trị `hidden=128/2 lớp` và `α=0,55/β=0,30/γ=0,15/δ=0` xuất hiện
> trong code chỉ là **mặc định**, bị **ghi đè** bởi `metadata.json` của checkpoint
> khi nạp mô hình. Khi trình bày hãy dùng số production ở trên.

---

## 0. Bức tranh tổng thể — pipeline 2 giai đoạn

Hệ thống là một bộ **gợi ý so khớp CV ↔ job** dựa trên **đồ thị không đồng nhất
(heterogeneous graph) + GNN**, theo kiến trúc kinh điển **truy hồi → xếp hạng lại**
(retrieve → rerank):

```
        DỮ LIỆU                    HUẤN LUYỆN (offline)              PHỤC VỤ (online)
   ┌──────────────┐          ┌───────────────────────┐      ┌──────────────────────────┐
   │ Crawler      │          │ Đồ thị (GraphBuilder)  │      │ match_cv(cv)             │
   │ CV parser    │ ──CVData │   ↓                    │      │  1. Inductive encode CV  │
   │ generator    │  JobData │ GNN (HeteroGraphSAGE)  │      │  2. RETRIEVE (shortlist) │
   │ resume_loader│ ───────▶ │   + BPR loss           │ ───▶ │  3. Hybrid 4-term score  │
   └──────────────┘          │   + curriculum neg     │ ckpt │  4. RERANK (MLP 23 feat) │
                             │   ↓                    │      │  5. Gates + penalties    │
                             │ Reranker MLP (5 trục)  │      │  6. Platt calibration    │
                             │ Calibrator (Platt)     │      │  → P(match) + xếp hạng   │
                             └───────────────────────┘      └──────────────────────────┘
```

- **Giai đoạn 1 (Retrieve):** từ cả kho job, tính nhanh một điểm tương tự để lấy
  **danh sách rút gọn** (~1000 job) → rồi chấm điểm tổ hợp đầy đủ trên danh sách đó.
- **Giai đoạn 2 (Rerank):** một MLP xếp hạng lại danh sách rút gọn bằng 23 đặc trưng,
  rồi **hiệu chuẩn Platt** đưa điểm về **xác suất tuyệt đối** so sánh được.

---

## 1. Cấu trúc thư mục `ml_service/`

| Thư mục | Vai trò | LOC |
|---|---|---|
| `graph/` | Định nghĩa **kiểu dữ liệu** (schema) + **dựng đồ thị** (builder) | ~390 |
| `embedding/` | Nhúng văn bản (sentence-transformers), 3 nhà cung cấp | ~130 |
| `models/` | **Kiến trúc GNN** (GraphSAGE/RGCN/GAT) + decoder + BPR loss | ~250 |
| `training/` | Vòng huấn luyện: BPR, lấy mẫu âm theo chương trình | ~650 |
| `reranker/` | MLP xếp hạng lại (23 đặc trưng, 5 trục) + hiệu chuẩn Platt | ~840 |
| `inference/` | **Engine phục vụ** (2 giai đoạn), truy hồi, pool, pgvector | ~2.150 |
| `evaluation/` | Độ đo (NDCG/Recall/MRR/AUC) + đánh giá theo từng CV | ~650 |
| `baselines/` | Baseline so sánh: BM25, cosine, skill-overlap | ~185 |
| `data/` | Sinh dữ liệu, nạp resume thật, đồ thị kỹ năng, từ điển kỹ năng | ~1.370 |
| `crawler/` | Thu thập job từ nhiều nguồn (Indeed/LinkedIn/Adzuna…) | ~1.600 |
| `verifier/` | Kiểm tra job còn sống + trích ngày đăng (Playwright) | ~1.520 |
| `cv_parser/` | Phân tích CV (PDF/DOCX) → dữ liệu có cấu trúc | ~325 |
| `config/` | Cấu hình theo biến môi trường (Pydantic Settings) | ~50 |

---

## 2. `graph/schema.py` — Các kiểu dữ liệu cốt lõi

Đây là "từ vựng" của cả hệ thống. Mọi nơi đều trao đổi qua các dataclass này.

**Loại nút (4):** `CV`, `JOB`, `SKILL`, `SENIORITY` (cấp bậc).

**Loại cạnh (đồ thị không đồng nhất):**
- `(cv, has_skill, skill)` — CV *có* kỹ năng (kèm trọng số **độ thành thạo 1–5**).
- `(job, requires_skill, skill)` — job *yêu cầu* kỹ năng (kèm **mức quan trọng 1–5**).
- `(cv, has_seniority, seniority)` / `(job, requires_seniority, seniority)`.
- `(cv, match, job)` / `(cv, no_match, job)` — **cạnh nhãn** (chỉ dùng khi huấn luyện).
- Cạnh cấu trúc: `(skill, relates_to, skill)`, `(job, similar_to, job)`,
  `(cv, similar_profile, cv)`.

**Các enum:**
- `SeniorityLevel`: INTERN(0) JUNIOR(1) MID(2) SENIOR(3) LEAD(4) MANAGER(5).
- `SkillCategory`: TECHNICAL(0) SOFT(1) TOOL(2) DOMAIN(3).
- `EducationLevel`: NONE(0) COLLEGE(1) BACHELOR(2) MASTER(3) PHD(4).

**Dataclass dữ liệu:**
- `CVData`: `cv_id, seniority, experience_years, education, skills[], skill_proficiencies[], text, role_category`.
- `JobData`: `job_id, seniority, skills[], skill_importances[], salary_min/max, text, experience_min/max, role_category`.
- `LabeledPair`: `cv_id, job_id, label(1/0), split(train/val/test), bucket` — `bucket`
  phục vụ **curriculum** (ví dụ `related_skill_positive`).

> **Điểm trình bày:** hệ dùng *đồ thị không đồng nhất* vì quan hệ CV–kỹ năng–job
> không phải một loại cạnh duy nhất. Kỹ năng là **nút trung gian** để hai CV/job
> "gặp nhau" qua kỹ năng chung, kể cả khi chưa từng có nhãn so khớp.

---

## 3. `embedding/` — Nhúng văn bản

Biến văn bản (mô tả CV/job, tên kỹ năng) thành vector số để GNN dùng.

- `EmbeddingProvider` (base): giao diện `encode(texts) → ndarray`, thuộc tính `dim`.
- 3 nhà cung cấp (đều **384 chiều**, chuẩn hoá L2):
  - `english` → `all-MiniLM-L6-v2`.
  - **`multilingual` → `paraphrase-multilingual-MiniLM-L12-v2`** ← **dùng ở production**
    (catalog có ~7% tiếng Việt; mô hình tiếng Anh đọc thành nhiễu).
  - `bge-small` → `BAAI/bge-small-en-v1.5` (mạnh hơn trên MTEB, cùng 384 chiều).
- Cùng 384 chiều nên đổi mô hình **không phải dựng lại** kích thước node.

> **Quan trọng:** `.env` phải đặt `EMBEDDING_PROVIDER=multilingual` cho khớp checkpoint;
> lệch nhà cung cấp = điểm vô nghĩa (không gian vector khác nhau).

---

## 4. `graph/builder.py` — Dựng đồ thị + đặc trưng node

`GraphBuilder.build(cvs, jobs, skill_catalog, pairs) → HeteroData`. Đây là nơi
**văn bản + thuộc tính** biến thành **ma trận đặc trưng node** và **các cạnh**.

### 4.1 Đặc trưng node (số chiều chính xác)

| Node | Chiều | Thành phần |
|---|---|---|
| **CV** | **397** | nhúng văn bản 384 + kinh nghiệm(chuẩn hoá) 1 + học vấn(chuẩn hoá) 1 + role one-hot 11 |
| **Job** | **397** | nhúng văn bản 384 + lương min(chuẩn hoá) 1 + lương max(chuẩn hoá) 1 + role one-hot 11 |
| **Skill** | **385** | nhúng tên kỹ năng 384 + nhóm kỹ năng 1 |
| **Seniority** | **6** | ma trận đơn vị 6×6 (mỗi cấp một node) |

- **11 role categories:** other, frontend, backend, fullstack, qa, devops, data_ml,
  mobile, ba, data_eng, design. CV và job **dùng chung** taxonomy này → so lĩnh vực
  được. Role suy ra bằng `infer_role()` nếu chưa gán sẵn.
- Lương/kinh nghiệm/học vấn được **min-max chuẩn hoá** trên tập đang dựng.
  *(Đây chính là chỗ tính năng "lương" gần đây được sửa: nạp giá trị USD/năm nhất
  quán thay vì số thô lẫn period — xem mục train/serve skew.)*

### 4.2 Các cạnh

- **CV/job → skill**: kèm trọng số (thành thạo / mức quan trọng 1–5).
- **CV/job → seniority**: mỗi node một cạnh tới cấp bậc của nó.
- **skill ↔ skill (`relates_to`)**: hai nguồn —
  - **PMI** đồng xuất hiện: `PMI = log(P(a,b)/(P(a)P(b)))`, lọc `đếm ≥ 3`, tối đa
    **10 cạnh/kỹ năng**, chuẩn hoá về [0,1].
  - **Ngữ nghĩa**: cosine nhúng > **0,70**, tối đa 5 cạnh mới/kỹ năng (bù cho cặp
    hiếm gặp nhưng cùng nghĩa).
- **job ↔ job / cv ↔ cv (`similar_to`/`similar_profile`)**: Jaccard kỹ năng ≥ 0,3,
  giữ top-5.
- **Cạnh nhãn `match`/`no_match`**: từ dữ liệu huấn luyện; builder **báo lỗi** nếu một
  cặp (cv,job) vừa match vừa no_match (ép khử trùng ở thượng nguồn).

---

## 5. `models/gnn.py` + `models/losses.py` — Kiến trúc GNN

### 5.1 Bộ mã hoá (encoder)
- **`HeteroGraphSAGE`** (production): mỗi loại node có một **phép chiếu tuyến tính**
  về `hidden=256`, rồi backbone **GraphSAGE** (tổng hợp **mean**) được bọc
  `to_hetero()` để chạy trên đồ thị không đồng nhất, **3 lớp**.
- **`MLPDecoder`**: nhận `[z_cv ‖ z_job]` (2×256) → Linear(512→256) → ReLU →
  Linear(256→1) → 1 điểm logit cho mỗi cặp.
- **`role_head`**: Linear(256→11) — **đầu phụ phân loại lĩnh vực**, *chỉ khi huấn
  luyện*, ép không gian embedding tách cụm theo nghề (không có nó, AUC lát-cắt-liên-quan ≈ 0,51).
- Hai biến thể đối chứng (cho ablation luận văn): **`HeteroRGCN`** (trọng số riêng
  theo loại cạnh) và **`HeteroGAT`** (attention thay mean). *Đã thử nghiệm: trên dữ
  liệu hiện có, không biến thể nào vượt mean-aggregator — xem `specs/028/ablation.md`.*

### 5.2 Hàm mất mát
- **`bpr_loss(pos, neg) = −log σ(pos − neg).mean()`** — Bayesian Personalized
  Ranking: ép điểm cặp *phù hợp* cao hơn cặp *không phù hợp*. Đây là loss học **xếp
  hạng** (không phải phân loại tuyệt đối) — đúng bản chất bài toán gợi ý.

> **Điểm trình bày:** mô hình **inductive** — job/CV mới được mã hoá bằng cách thêm
> node tạm vào đồ thị đông cứng rồi encode 1 lần, **không cần train lại**. Đây là chìa
> khoá để hệ mở rộng kho job mà trọng số vẫn cố định.

---

## 6. `training/trainer.py` — Vòng huấn luyện

- `TrainConfig`: `model_type, hidden_channels, num_layers, lr=1e-3, weight_decay=1e-5,
  epochs, patience, dropout, drop_edge_rate, full_space_neg…`.
- **Lấy mẫu âm theo chương trình (hard-negative curriculum):**
  - Âm "khó" = trùng kỹ năng ≥ 0,15 **và** lệch cấp bậc ≤ 1 (giống nhưng vẫn sai).
  - Tỉ lệ âm khó tăng dần: epoch <5 → 0%, <20 → 30%, còn lại → 70% (học dễ trước,
    khó sau). Positive "liên quan kỹ năng" được nhân 3 xác suất chọn làm anchor.
- **Loss:** BPR + (tuỳ chọn) coherence cạnh kỹ năng + (tuỳ chọn) phụ phân loại role.
- **Dừng sớm:** tín hiệu `0,8·val_AUC + 0,2·AUC_lát_cắt_liên_quan`, đo **theo từng CV**
  rồi macro-average; âm validation cố định để eval tất định.
- Đầu ra `TrainResult`: mô hình tốt nhất + lịch sử + `data_clean` (đồ thị đã **gỡ cạnh
  nhãn** để phục vụ).

---

## 7. `reranker/` — Xếp hạng lại + hiệu chuẩn

### 7.1 `features.py` — 23 đặc trưng cho mỗi cặp (CV, job)
Nhóm chính: tương tự văn bản; overlap kỹ năng (Jaccard / có trọng số / ngữ nghĩa);
số kỹ năng quan trọng còn thiếu; khoảng cách cấp bậc + điểm cấp bậc; penalty lĩnh
vực; số năm kinh nghiệm + khoảng cách kinh nghiệm; độ hiếm/đặc thù kỹ năng; tỉ lệ
"tool"; **điểm & hạng GNN giai đoạn 1**; cờ must-have / edge-case. `set_stage1_context()`
bơm điểm-hạng giai đoạn 1 vào trước khi trích.

### 7.2 `ranker.py` — MLP đa nhiệm
- Thân chung: `Linear(23→64) → ReLU → Dropout(0,2) → Linear(64→64) → ReLU → Dropout(0,2)`.
- Đầu chính: `Linear(64→3)` (ordinal: 0 không hợp / 1 hợp / 2 rất hợp); điểm tổng =
  kỳ vọng `(p₁·1 + p₂·2)/2 ∈ [0,1]`.
- **4 đầu phụ** (chỉ khi train): mỗi đầu `Linear(64→3)` cho **5 trục** —
  `skill_fit, experience_fit, seniority_fit, domain_fit` (+ overall ở đầu chính).
- `score_batch_with_dims()` trả `(điểm_tổng, mức_từng_trục)`.

### 7.3 `calibration.py` — Hiệu chuẩn Platt
- Hồi quy logistic 1 biến trên `rank_score`: `P = σ(a·score + b)` (production `a=7,96, b=−2,45`).
- `transform_single()` đưa điểm thô → **xác suất tuyệt đối** [0,1], **so sánh được
  giữa các nhân viên** và ổn định qua các lần chạy.
- `trained_with` = vân tay sha256 của `reranker.pt` → engine cảnh báo nếu lệch phiên bản.

> **Điểm trình bày:** điểm hiển thị = `P(match)` đã hiệu chuẩn, **không** phải điểm
> thô. Nghĩa: "xác suất cặp được ground-truth chấm là phù hợp". Đủ điều kiện khi `P ≥ 0,50`.

---

## 8. `inference/engine.py` — Engine phục vụ (trái tim hệ thống)

`InferenceEngine.match_cv(cv, top_k, retrieve_n)` chạy 6 bước:

1. **Mã hoá CV một lần:** `cv_text_vec` (384) + `cv_gnn_emb` (inductive encode, có
   khoá `_inductive_lock` để tuần tự hoá).
2. **Giai đoạn 1 — Truy hồi:** `retriever.shortlist(cv, …, k)` lấy ~`retrieve_k=1000`
   ứng viên; rồi `_score_pair_fast()` chấm **điểm tổ hợp đầy đủ** trên danh sách rút
   gọn; sắp xếp lấy `retrieve_n`.
3. **Hybrid 4 thành phần** (trong `_score_pair_fast`):
   ```
   base = α·gnn + β·skill + γ·seniority + δ·domain      (α=0,30 β=0,20 γ=0,10 δ=0,40)
     gnn        = 0,6·σ(decoder) + 0,4·cosine_văn_bản
     skill      = overlap kỹ năng có trọng số + thưởng ngữ nghĩa (0,6·PMI)
     seniority  = max(0, 1 − 0,4·|Δcấp bậc|)
     domain     = role_domain_fit ∈ {0; 0,5; 0,7; 1,0}   (SOFT, không lọc cứng)
   score = base × penalty(role) × must_have × edge_case
   ```
4. **Giai đoạn 2 — Rerank:** nếu reranker đã train → `score_batch_with_dims()` xếp lại
   danh sách (điểm giai đoạn 1 vẫn là điểm gốc; reranker quyết thứ tự).
5. **Gates + penalty** (`_penalty_product`): nhân hệ số phạt —
   - **Domain gate** 0,40 nếu lệch lĩnh vực rõ.
   - **Experience gate** 0,40 nếu thiếu năm KN / 0,85 nếu thừa > 3 năm.
   - **Seniority gate** 0,70 (job cao hơn ≥2 bậc) / 0,75 (CV cao hơn ≥2 bậc).
   - Đồng thời tính **5 trục minh bạch** `_dimension_scores` (công thức tay, tái lập được).
6. **Hiệu chuẩn + kết quả:** sắp theo `rank_score = (reranker hoặc stage1) × penalty`,
   lấy top_k, `P = Platt(rank_score)`, `eligible = P ≥ 0,50`. Trả `JobMatchResult`
   kèm `score_breakdown` (trọng số, từng thành phần, gates, penalty) → **giải thích được**.

> Mọi điểm thành phần và gate đều là **công thức tường minh** (không hộp đen ngoài GNN
> + reranker), nên có thể tái lập bằng tay khi bảo vệ.

---

## 9. `inference/retrieval/` — Truy hồi hoán đổi được (feature 027)

Giao diện `Retriever.shortlist(cv, cv_text_vec, cv_gnn_emb, k) → [(job_idx, sim)]`,
chọn qua `RETRIEVAL_MODE`:
- **`exact`** (mặc định, đối chứng A/B): chấm `_score_pair_fast` trên **toàn kho** —
  O(N), giống hệt code cũ.
- **`vector`** (Stage A): **vector hoá** điểm recall = `α·gnn_proxy + β·skill + γ·sen
  + δ·domain` bằng matmul + `argpartition` top-k → O(N) nhưng nhanh hơn nhiều; recall@1000 ≈ 1,0.
- Điểm cuối (tổ hợp chính xác + reranker + Platt) **vẫn** chạy trên danh sách rút gọn
  → chất lượng/hiệu chuẩn không đổi.

---

## 10. Quản lý kho job (job pool) — feature 018/027

Trọng số mô hình **đông cứng**; chỉ **node job được mã hoá lại** khi kho thay đổi.

- **`checkpoint.py`**: nạp/lưu `model.pt, graph.pt, cvs.json, jobs.json, metadata.json`
  (chứa `hybrid_weights`, `node_dims`, `train_config`).
- **`job_pool_snapshot.py`**: snapshot trên đĩa (`jobs.json`, `job_embeddings.pt`,
  `job_text_vecs.npy`, `meta.json`) — ghi nguyên tử (temp → đổi tên). Server live
  **hot-reload theo mtime**. `model_sig` phải khớp, lệch → quay về pool checkpoint đông cứng.
- **`pgvector_store.py`** (Stage B): bảng `job_pool_vec(job_id, gnn_emb vector,
  text_vec vector, role_category, model_fingerprint, content_hash, updated_at)`,
  upsert theo lô 500. *Là kho lưu* (load lúc khởi động), không phải chỉ-mục ANN mỗi request.
- **`pool_diff.py`** (Stage C): `content_hash = sha256(skills, importances, seniority,
  text)` → rebuild **tăng dần**, chỉ encode job mới/đổi. *(Lưu ý: hash không gồm lương
  → đổi feature lương phải `rebuild_job_pool --full`.)*
- **`role_classifier.py`**: `infer_role()` (title → kỹ năng → mặc định) +
  `role_match_penalty` ∈ {1,0 / 0,7 / 0,45}.

---

## 11. `evaluation/` + `baselines/` — Đo lường

- **`metrics.py`**: `ndcg@k, recall@k, precision@k, hit_rate@k, mrr, auc_roc`
  (NDCG = DCG/IDCG; MRR = 1/hạng-positive-đầu-tiên).
- **`per_cv_evaluator.py`**: giao thức **xếp hạng đầy đủ theo từng CV** rồi macro-
  average (đúng nghĩa "chất lượng gợi ý cho từng người", không phải xếp gộp toàn cặp).
  Có biến thể 2 giai đoạn (đo cả recall@retrieve_n = trần của giai đoạn 1).
- **`baselines/`**: `BM25` (k1=1,5, b=0,75), `Cosine` (nhúng văn bản), `SkillOverlap`
  (Jaccard, dựng ma trận vector hoá) — để chứng minh GNN hơn baseline.

---

## 12. `data/` — Sinh & chuẩn hoá dữ liệu

- **`generator.py`**: sinh CV/job/nhãn tổng hợp (phân phối cấp bậc, số kỹ năng, độ
  thành thạo theo cấp; `SENIORITY_TO_SALARY_USD` cho lương **theo năm, đơn vị USD**).
  → đây là lý do feature lương ở serving phải đưa về **USD/năm** cho khớp lúc train
  (sửa *train/serve skew*).
- **`resume_loader.py`**: nạp resume thật (Kaggle 4.817 + bộ 54k, lọc title IT).
- **`skill_taxonomy.py`**: từ điển kỹ năng, 8 cụm (fullstack_web, backend_python…),
  template sinh văn bản CV/job.
- **`skill_normalization.py`**: `SkillNormalizer.normalize()` đưa biến thể → tên chuẩn
  (từ `skill-alias.json`); kỹ năng lạ bị loại.
- **`skill_graph.py`**: dựng PMI đồng xuất hiện + cạnh ngữ nghĩa + cạnh tương tự job/CV.

---

## 13. Ngoại vi: thu thập, phân tích CV, kiểm tra job

- **`crawler/`**: giao diện `CrawlProvider.fetch()` → `RawJob`; factory tự khám phá
  provider. Nguồn: **JobSpy** (Indeed, scraping), **LinkedIn** (Playwright + phiên đăng
  nhập lưu sẵn), **Adzuna/Remotive/RemoteOK/Freelancer** (REST API). `storage.py` khử
  trùng 2 lớp (URL + **fingerprint** chuẩn hoá title/company/city) → JSONL.
  *(Đây là nơi feature lương vừa thêm `salary_interval` để bắt period.)*
- **`cv_parser/parser.py`**: `CVParser` đọc PDF (pdfplumber)/DOCX (python-docx) → tách
  mục → trích kỹ năng (n-gram + normalizer) → suy cấp bậc/kinh nghiệm/học vấn → `CVData`.
- **`verifier/`**: kiểm tra job LinkedIn còn sống không + trích **ngày đăng**
  (`date_extractor`: JSON-LD → thuộc tính `<time>` → text tương đối, kẹp ±730 ngày).
  `browser_pool` (Playwright persistent, sao chép profile dùng-rồi-xoá),
  `auth_guard` (bất biến: cookie `li_at` trên domain linkedin), `service`/`backfill_service`
  (ghi DB sau khi đóng browser để an toàn ORM).

---

## 14. Bảng tra số liệu nhanh (để bảo vệ)

| Hạng mục | Giá trị production |
|---|---|
| Backbone GNN | HeteroGraphSAGE (mean), `to_hetero` |
| hidden / lớp | **256 / 3** |
| Nhúng văn bản | multilingual MiniLM, **384** chiều |
| Node CV/job/skill/seniority | **397 / 397 / 385 / 6** |
| Decoder | MLP 512→256→1 |
| Loss huấn luyện | **BPR** + curriculum hard-negative (0→30→70%) |
| Trọng số hybrid α/β/γ/δ | **0,30 / 0,20 / 0,10 / 0,40** |
| GNN nội bộ (gnn_score) | 0,6·σ(decoder) + 0,4·cosine |
| Reranker | MLP 23 feat → 64→64→3, 4 đầu phụ (5 trục) |
| Calibration | Platt `a=7,96, b=−2,45`; đủ điều kiện `P ≥ 0,50` |
| Gates | domain 0,40 · exp 0,40/0,85 · seniority 0,70/0,75 |
| Truy hồi | exact (mặc định) / vector; shortlist `retrieve_k=1000` |
| Kho train / serve | 366 CV, 6.251 job / ~8.930 job live |

---

## 15. Câu hỏi phòng vệ thường gặp & cách trả lời

**H: Vì sao dùng GNN mà không chỉ cosine văn bản?**
Đ: Cosine chỉ thấy *tương tự văn bản*. GNN lan truyền tín hiệu qua **kỹ năng chung**
nên hai CV/job chưa từng có nhãn vẫn liên hệ được; đồng thời học từ **nhãn so khớp**
(BPR) thay vì chỉ ngữ nghĩa bề mặt. Baseline BM25/cosine/skill-overlap có sẵn để so.

**H: Mô hình có học lại khi thêm job mới không?**
Đ: Không. GNN **inductive** — job/CV mới được encode bằng cách gắn node tạm vào đồ thị
đông cứng. Chỉ rebuild *embedding job*, trọng số giữ nguyên.

**H: Điểm hiển thị nghĩa là gì?**
Đ: `P(match)` **đã hiệu chuẩn Platt** — xác suất cặp được ground-truth chấm phù hợp,
**tuyệt đối** và so sánh được giữa nhân viên. Không phải điểm thô.

**H: Vì sao điểm tổ hợp 4 thành phần chứ không để GNN quyết hết?**
Đ: GNN decode đơn lẻ trên dữ liệu thưa nhãn yếu (AUC quanh 0,5). Kỹ năng/cấp bậc/lĩnh
vực là **công thức tường minh, giải thích được**, bù cho GNN và cho phép kiểm soát
(gates) — quan trọng với người dùng HR. Trọng số được tune (`tune_hybrid_weights`).

**H: Hệ chống lệch lĩnh vực (frontend ↔ devops) thế nào?**
Đ: Hai tầng — `domain` là thành phần mềm (δ=0,40, lớn nhất) **và** một **gate cứng**
nhân 0,40 khi lệch rõ; cộng `role_match_penalty` {1,0/0,7/0,45}.

**H: Đã cải tiến kiến trúc encoder chưa?**
Đ: Đã thử attention (GAT), RGCN, sum, L2, jumping-knowledge, độ sâu, trọng-số-cạnh,
DropEdge, contrastive — trên cả bộ công khai (bão hoà) lẫn nội bộ (còn dư địa). **Không
hướng nào vượt mean-aggregator ngoài độ lệch chuẩn**; nút thắt là *dữ liệu* (nhãn phủ
~0,53%), không phải kiến trúc. Chi tiết: `specs/028-gnn-attention-aggregation/ablation.md`.

---

*Tệp mã tham chiếu:* `backend/ml_service/` · checkpoint `backend/checkpoints/latest/`
(metadata.json là nguồn chân lý cho trọng số/cấu hình lúc phục vụ).
