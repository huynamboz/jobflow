# Project Journey — Toàn bộ hành trình về "matching đúng bản chất"

> File tổng hợp duy nhất: đọc file này là nắm được TẤT CẢ những gì đã làm, vì sao, và số liệu ở đâu. Cập nhật: 2026-06-11 (thêm GNN v2). Mọi mục đều link tới artifact gốc.

## Bài toán & mục tiêu

Hệ matching CV↔job cho HR shadow-staffing, lõi là GNN (HeteroGraphSAGE) + reranker. Yêu cầu của chủ dự án: **làm đúng bản chất** — mọi con số có cơ sở, chất lượng đo được, không che khuyết điểm — để vừa dùng thật vừa trình bày được trước giám khảo.

## Dòng thời gian & kết quả

### Giai đoạn nền (trước chuỗi chính)
| Feature | Việc | Artifact |
|---|---|---|
| **018** Inductive job pool | Job mới crawl rank được không cần retrain (inductive encode + snapshot + hot-reload); match resolve 1:1 về `Job.id` | [specs/018](../../specs/018-inductive-job-pool/) |
| **019** Weight calibration | Tune α/β/γ bằng grid-search AUC (hết magic number); 4 chiều fit thành công thức minh bạch; single-source config | [specs/019](../../specs/019-match-weight-calibration/) + ablation |
| **020** Domain-aware | Phát hiện bug lạc nghề (backend CV → job VFX) qua eval 20-CV; thêm δ·domain + tune role-aware (chống degenerate bằng constrained objective); eval harness thành command | [specs/020](../../specs/020-domain-aware-ranking/) + dual ablation |

### Audit toàn chuỗi (bước ngoặt)
5 agent đọc code song song + forensics DB → **20 lỗ hổng A1-A20** ([09-pipeline-audit](09-pipeline-audit.md)) và **chuỗi nhân-quả gốc rễ**: chọn-cặp-label thiên skill → rubric 5 lỗi → nhãn mù domain/related-skill → GNN không học được → phải vá ngoài → tune ra trọng số lệch. Đẻ ra [10-master-plan](10-master-plan.md) 4 đợt.

### Đợt 0 — Fix nền pipeline (feature 021)
7 bug sửa + test: experience fields về pool (A1) · dedup nhãn export + graph guard raise khi cặp xung đột (A2: 2.994 nhãn trùng, 181 cặp có cả match+no_match) · **thứ tự cuối = reranker×gates, display monotonic** (A3 — trước đó sort cuối vô hiệu hoá reranker) · per-CV metrics (A7 — hết precision@5=1.0 ảo) · vá 3 lỗi rubric (A4-A6) · dedup 733 job trùng + serving guard (A9). **Baseline trung thực: 75%.** → [specs/021](../../specs/021-pipeline-foundation-fixes/)

### Đợt 1 — Relabel bằng Claude agents (feature 022)
- 3.800 cặp **decision-boundary buckets** (cross-domain hard-neg, related-skill positive, seniority hard-neg, missing-must-have, boundary) — quota đủ, 0 shortfall
- **Label bằng agent in-session** (không cần LLM provider): export/import/audit commands, **pilot gate** (bắt thêm 2 lỗi rubric: rule seniority bất đối xứng + rule tag `other` suy-từ-nội-dung), scale 151 chunk (Fable 25 + Sonnet 126 sau calibration chéo 93.9%), **inter-rater agreement 87%** ([agreement-report](../../specs/022-relabel-dataset-buckets/agreement-report.md), [pilot-report](../../specs/022-relabel-dataset-buckets/pilot-report.md))
- Re-label 427 cặp slice hỏng cũ → slice skill2/domain0 về **0% positive** (từ 43% nhiễu)
- **Dataset v4_relabel: 12.084 nhãn unique, positive 33.3%, graph 0 conflict** → `data/processed/v4_relabel`

### Đợt 2 — Retrain + verify (feature 022)
- Train trên **server Neptune** (dana@10.9.0.4, RTX 3090 — quy trình [sync-and-train](../../.claude/commands/sync-and-train.md), 294s/vòng GNN): test per-CV AUC 0.813, **NDCG@10 0.894**, MRR 0.864; reranker acc 0.702
- Debug serving 5 vòng bằng eval harness: 45% (AUC-max weights — skill flood retrieve) → 60% (balanced — reranker bị job degenerate lừa) → fix A14 skew → **feature-dump tìm gốc** (job VFX chỉ còn 2 skill sau lọc catalog = A10 hiện hình) → **domain gate ×0.40** trong ordering (thực thi rule nhãn) → **90%**
- ⚠️ **NEGATIVE RESULT trung thực** (3 phép đo hội tụ): GNN decode không học được related-skill (AUC 0.512 vs semantic-skill thủ công 0.861; oversample ×3 vô hiệu) → DoD "α≥0.3" sửa chính thức bằng bằng chứng; hệ = **ensemble có kiểm chứng**, GNN giữ vai trò inductive + feature reranker
- Vòng đời metric khép kín: AUC-nhãn-bẩn → role-NDCG (chống degenerate) → nhãn sạch tự encode domain làm role-NDCG bão hoà → label-AUC sạch + eval định tính là bộ thước cuối ([07-evaluation-tuning](07-evaluation-tuning.md))

### Đợt 3 — Data-ops (feature 023 + main)
- **3.1** Role backfill: 1.898 job thiếu role → 48 agent phân loại (414 role IT, 1.484 đúng đắn giữ other) — command `backfill_job_roles`
- **3.5** Taxonomy sync — chìa khoá 2 ca trượt cuối: `infer_role` trả `data`/`ml` không bao giờ khớp `data_ml`/`data_eng` → canonical hoá + bảng related vào engine (data_ml↔data_eng=0.7, gate chỉ bắn khi 0.0) → **eval 20/20 (100%), on_domain@5 = 1.00, 0 off-domain**
- **3.6** A14 guard: reranker_meta lưu `trained_with_weights`, engine WARN khi lệch serving weights (quy tắc: tune trước → retrain reranker sau)
- **3.2** Skill-drop reporting trong sync (hết drop âm thầm — cơ chế lẽ ra bắt được vụ VFX-2-skill) · **3.3** seniority null→suy từ experience + cross-check mâu thuẫn
- **3.4** embedding đa ngữ — hoàn thành trong GNN v2 (dưới)

### GNN v2 — làm GNN "thông minh" thật (feature 024, 2026-06-10→11)
Câu hỏi: GNN decode kẹt ở đoán-mò (slice related-skill AUC 0.512) — cải thiện được không? **8 thí nghiệm có kiểm soát** ([12-gnn-v2-proposal](12-gnn-v2-proposal.md) bảng mục 6), mỗi vòng ~5 phút trên Neptune + đo ngay trên server (`measure_slice.py`):
- **Vòng 1 (r1a/r1b)**: aux role head + bucket-curriculum + slice early-stop → ❌ aux loss XUNG ĐỘT BPR (best epoch 19-22 rồi thoái hoá, pipeline sụp 0.62)
- **Vòng 2 (E1-E4)**: self-supervised pretrain (link-prediction, `run_pretrain.py`), skill-relation loss, GATv2 attention → ❌ tất cả kẹt trần slice ~0.55; chẩn đoán trung gian quan trọng: 95% cặp related CÓ cầu `relates_to` trong graph (thông tin có sẵn, model không khai thác) + phân biệt trong-bucket là bài toán ĐẾM partial-credit
- **Vòng 3 (E5)**: đổi embedding MiniLM tiếng-Anh → **paraphrase-multilingual-MiniLM-L12-v2** (384-dim drop-in) → 🚀 slice 0.512→**0.734** ngay lập tức — **nút thắt thật là chất lượng embedding đầu vào**, không phải training/kiến trúc
- **E6 = đa ngữ + pretrain → PROMOTED**: pipeline test AUC **0.860** (kỷ lục, cũ 0.813), NDCG@10 0.894, slice 0.705, **re-tune cho α=0.30** (GNN đồng-đứng-đầu với domain; DoD gốc "α≥0.3" đạt bằng thực lực sau khi từng bị sửa vì negative result), eval 20-CV giữ 100%
- **Held-out validation**: bộ 20 persona MỚI hoàn toàn (gài ca khó: Flask→Django, Svelte, Flutter, SRE, DBA, fresh-grad) → **20/20 (100%), on_domain@5 = 1.00** — không overfit harness; ca đẹp nhất: Flask CV → Python Developer (đúng năng lực related-skill mới), Fresh Grad → Internship/Graduate roles
- Vận hành: serving yêu cầu `EMBEDDING_PROVIDER=multilingual` (backend/.env — checkpoint↔provider phải đồng bộ); backbone pretrain `run_pretrain.py`; backup model cũ tại `checkpoints/backup_pre_v2`

## Bảng tiến hoá chất lượng (eval 20-CV cố định)

```
019 tune nhãn bẩn:       lạc nghề (backend CV → Compositor/Animator)
020 vá δ·domain:         90%  (nhưng đo khi bug A3 bypass reranker)
Đợt 0 fix nền:           75%  ← baseline trung thực đầu tiên
Đợt 2 retrain v4:        90%  ← kiến trúc 2 tầng chạy đúng
023 role+taxonomy:      100%  ← 0 off-domain
GNN v2 (024):           100%  ← giữ đỉnh + held-out 100% + α=0.30 (GNN gánh thật)
```

## Trạng thái hệ hiện tại

- **Model (GNN v2/E6)**: HeteroGraphSAGE 256×3, node features 397-dim (embedding ĐA NGỮ 384 + role one-hot 11 + extras), self-supervised pretrain → BPR finetune; slice related-skill AUC 0.705 (từ 0.512)
- **Weights**: `0.30·GNN + 0.20·skill + 0.10·seniority + 0.40·domain` (metadata.json — single source) + domain gate ×0.40 + exp/sen gates; thứ tự = reranker×gates (acc 0.706, A14-synced); 4 dim hiển thị = công thức minh bạch
- **Eval**: harness 20-CV 100% · held-out 20-CV mới 100% · pipeline test AUC 0.860 / NDCG@10 0.894 (per-CV, 240 CV)
- **Guards tự động**: graph conflict (raise) · reranker↔weights skew (warn) · skill-drop (report) · model_signature (snapshot) · serving dedup
- **Quy trình tái lập 1 lệnh**: train remote (`sync-and-train`), label bằng agents (export→pilot→scale→agreement→import), eval (`eval_matching`), tune (`tune_hybrid_weights`)
- Test suite ~40 test xanh; memory lưu server Neptune

## Tư liệu cho luận văn (đã có sẵn, chỉ cần biên soạn)

1. 2 bảng ablation ([019](../../specs/019-match-weight-calibration/ablation.md) nhãn bẩn, [020/v4](../../specs/020-domain-aware-ranking/ablation.md) dual-metric) — minh hoạ "metric sai → trọng số sai"
2. [Pilot](../../specs/022-relabel-dataset-buckets/pilot-report.md) + [agreement](../../specs/022-relabel-dataset-buckets/agreement-report.md) report — phương pháp đảm bảo chất lượng nhãn
3. [Audit 20 lỗ hổng](09-pipeline-audit.md) + chuỗi nhân-quả — phần "phân tích hệ thống"
4. **Câu chuyện GNN trọn vẹn 2 hồi** ([07](07-evaluation-tuning.md) + [12](12-gnn-v2-proposal.md)): hồi 1 negative result (3 phép đo hội tụ → sửa DoD trung thực); hồi 2 — 8 thí nghiệm có kiểm soát tìm ra nút thắt thật (embedding) → α 0.05→0.30 → DoD khôi phục bằng thực lực. Mẫu mực phương pháp khoa học cho luận văn
5. Bảng tiến hoá 75→90→100% (+ held-out 100%) với nguyên nhân từng bước

## Đọc tiếp ở đâu

[README](README.md) (mục lục 11 docs) · [10-master-plan](10-master-plan.md) (checkbox chi tiết) · [01-architecture](01-architecture-overview.md) (bản đồ hệ) · CLAUDE.md (gotchas vận hành)
