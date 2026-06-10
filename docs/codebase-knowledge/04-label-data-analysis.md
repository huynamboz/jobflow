# Label Data Analysis (DB snapshot 2026-06-10)

Phân tích trực tiếp bảng `labeling_*` trong PostgreSQL — đây là **ground truth thật** mà checkpoint production được train trên đó (qua `export_dataset.py` → `data/processed/b89_full` → `run_train_save.py`).

## 1. Quy mô & nguồn

| Bảng | Số lượng |
|---|---|
| `HumanLabel` (nhãn) | **11.611** — `labeled_by=None` toàn bộ → **100% LLM label**, không có người |
| `PairQueue` labeled | 8.617 / 10.538 cặp (một cặp có thể được label nhiều lần qua các batch) |
| `LabelingCV` | 365 CV |
| `LabelingJob` | 6.251 job |

Batch có nhãn: **6** (3.499) · 7 (56) · **8** (3.031) · **9** (4.950) · 10 (75). Checkpoint production dùng batch **6, 8, 9, 10** (= dataset `b89_full`, 11.509 nhãn sau filter).

## 2. Schema nhãn (`HumanLabel`)

- `overall`: 0 = Không phù hợp / 1 = Phù hợp / 2 = Rất phù hợp
- 4 chiều, mỗi chiều 0/1/2: `skill_fit`, `seniority_fit`, `experience_fit`, `domain_fit`
  → **đây chính là nguồn nhãn aux-head của reranker** (bí ẩn ở feature 019 — đã giải)
- `note`, `batch`, `labeled_by` (None = LLM)

## 3. Phân phối

**Overall**: 0 → 7.778 (67%) · 1 → 3.009 (26%) · 2 → 824 (7%)

**Selection reason** (cách cặp được CHỌN đem label): random 3.495 · medium_overlap 2.178 · high_overlap 1.505 · hard_negative 1.439

**domain_fit**: 0 → 6.656 · 1 → 1.345 · 2 → 3.610

## 4. Crosstab — các phát hiện then chốt

### overall × domain_fit
| | dm=0 | dm=1 | dm=2 |
|---|---|---|---|
| **overall=0** | 6.556 | 427 | 795 |
| **overall=1** | 100 | 725 | 2.184 |
| **overall=2** | 0 | 193 | 631 |

→ Negative tương quan mạnh với domain mismatch (LLM **có** dùng domain khi chấm). Không có cặp "rất phù hợp" nào khác nghề.

### overall × skill_fit
| | sk=0 | sk=1 | sk=2 |
|---|---|---|---|
| **overall=0** | 6.037 | 1.515 | 226 |
| **overall=1** | 0 | 2.657 | 352 |
| **overall=2** | 0 | 0 | 824 |

→ `overall` gần như **hàm của skill_fit** (mọi overall=2 đều skill=2; overall≥1 đòi skill≥1). **Giải thích vì sao tune label-AUC cho β (skill) = 0.75**: nhãn vốn skill-driven.

### ⚠️ Slice quyết định: "skill CAO nhưng KHÁC nghề" (skill_fit=2, domain_fit=0)
Đây chính là pattern bug VFX (backend CV × Compositor-cần-python):

| | Số cặp |
|---|---|
| → overall=0 (đúng) | 132 |
| → overall=1 (**LLM chấm phù hợp dù khác nghề!**) | 100 |
| **Tổng** | **232 / 11.611 = 2.0%** |

**Hai vấn đề cộng hưởng:**
1. **Quá hiếm** — chỉ 2% tập nhãn là hard cross-domain negative, không đủ để GNN học ranh giới domain.
2. **Quá nhiễu** — 43% slice này bị label *positive* (LLM "tha" domain khi skill khớp mạnh) → tín hiệu mâu thuẫn, model học được rằng khác nghề đôi khi vẫn OK.

→ **Đây là gốc rễ định lượng của bug domain-mismatch** (backend CV → top VFX jobs) và của việc trọng số GNN thấp khi tune.

## 5. Hệ quả & hướng cải thiện (xem 08-improvement-opportunities.md)

1. **Bổ sung batch label cross-domain có chủ đích**: sinh PairQueue mới ưu tiên cặp (skill overlap cao × khác role_category) — vài nghìn cặp — rồi chạy LLM labeling với prompt **siết tiêu chí domain** (khác nghề ⇒ overall=0 trừ khi role tương thích thực sự).
2. **Làm sạch 100 cặp mâu thuẫn** (skill=2, dm=0, overall=1): re-label hoặc loại khỏi train.
3. Sau đó **retrain GNN + reranker** trên tập mới → kỳ vọng GNN tự học domain, α tăng tự nhiên, giảm phụ thuộc δ·domain vá ngoài.

## Cách tái lập phân tích này

```bash
cd backend && .venv/bin/python -c "
import django,os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); django.setup()
from django.db.models import Count
from apps.labeling.models import HumanLabel
print(list(HumanLabel.objects.values('overall','domain_fit').annotate(c=Count('id'))))
print(list(HumanLabel.objects.filter(skill_fit=2, domain_fit=0).values('overall').annotate(c=Count('id'))))
"
```
