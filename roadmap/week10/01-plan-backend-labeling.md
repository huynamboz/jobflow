# Plan: Backend Labeling System (Week 10)

> Mục tiêu: Labeling là một **feature trong Admin panel**. Admin dùng tool này để label CV-Job pairs, dữ liệu được export cho ML training pipeline sau này.

---

## Context: Vị trí trong hệ thống

```
Admin Panel (React)
  ├── Dashboard / Stats
  ├── Jobs management
  ├── CVs management
  └── [NEW] Labeling Tool  ← Week 10 focus
        │
        │ REST API (IsAdmin permission — reuse auth hiện có)
        ▼
  apps/labeling/  (Django app mới)
    ├── LabelingCV     (snapshot CV để display, không phụ thuộc raw files)
    ├── LabelingJob    (snapshot Job để display)
    ├── PairQueue      (cặp CV-Job chờ label, pre-populated bởi smart selector)
    └── HumanLabel     (labels đã gán bởi admin)
        │
        ▼
  Export → ML Training Pipeline
    └── LabeledPair(cv_id, job_id, label, split)
```

**Auth**: Dùng `IsAdmin` permission có sẵn (`apps/users/permissions.py`) — không cần build thêm.

---

## Tại sao cần labeling system

Hệ thống hiện tại dùng proxy labels (skill overlap + seniority threshold). GNN đạt AUC 0.70 nhưng bị giới hạn bởi chất lượng signal này. Với **200–300 human labels**, training signal sẽ phản ánh đúng "job này có phù hợp với người này không" từ góc nhìn recruiter.

---

## Django Models (`apps/labeling/`)

### 1. `LabelingCV`
Snapshot thông tin CV để hiển thị trên UI — độc lập với raw files, không FK sang `apps/cvs/CV` (tránh coupling, CV trong apps/cvs gắn với user upload, còn đây là LinkedIn import cho ML).

```python
class LabelingCV(models.Model):
    cv_id            = models.IntegerField(unique=True)  # map với CVData.cv_id trong ML pipeline
    source           = models.CharField(max_length=50)   # "linkedin", "kaggle"
    skills           = models.JSONField()                # ["python", "django", ...]
    seniority        = models.CharField(max_length=20)   # "JUNIOR", "MID", ...
    experience_years = models.FloatField()
    education        = models.CharField(max_length=20)   # "BACHELOR", "MASTER", ...
    text_summary     = models.TextField()                # first 500 chars của CV text
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "labeling_cv"
```

### 2. `LabelingJob`
Snapshot thông tin Job để hiển thị.

```python
class LabelingJob(models.Model):
    job_id       = models.IntegerField(unique=True)      # map với JobData.job_id trong ML pipeline
    title        = models.CharField(max_length=200)
    skills       = models.JSONField()                    # ["python", "fastapi", ...]
    seniority    = models.CharField(max_length=20)
    salary_min   = models.IntegerField(null=True)
    salary_max   = models.IntegerField(null=True)
    text_summary = models.TextField()
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "labeling_job"
```

### 3. `PairQueue`
Cặp CV-Job được smart selector chọn để gán nhãn.

```python
class SelectionReason(models.TextChoices):
    MEDIUM_OVERLAP = "medium_overlap"  # 0.15 <= overlap < 0.40 → most informative
    HIGH_OVERLAP   = "high_overlap"    # overlap >= 0.40 → confirm positives
    HARD_NEGATIVE  = "hard_negative"   # same domain, wrong seniority → confirm negatives
    RANDOM         = "random"          # diversity

class PairStatus(models.TextChoices):
    PENDING = "pending"
    LABELED = "labeled"
    SKIPPED = "skipped"

class PairQueue(models.Model):
    cv                  = models.ForeignKey(LabelingCV, on_delete=models.CASCADE)
    job                 = models.ForeignKey(LabelingJob, on_delete=models.CASCADE)
    skill_overlap_score = models.FloatField()
    bm25_score          = models.FloatField(default=0.0)
    selection_reason    = models.CharField(max_length=30, choices=SelectionReason.choices)
    priority            = models.IntegerField(default=0)
    # priority được set lúc populate: medium_overlap=1, high_overlap=2, hard_negative=3, random=4
    # dùng để order queue đúng thứ tự thay vì dùng "?" random ordering (không reliable)
    status              = models.CharField(max_length=20, choices=PairStatus.choices,
                                           default=PairStatus.PENDING)
    split               = models.CharField(max_length=10, default="train")
    # split pre-assigned lúc populate: 70% train / 15% val / 15% test
    # đảm bảo test set cố định, không phụ thuộc vào thứ tự label
    created_at          = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "labeling_pair_queue"
        unique_together = ("cv", "job")
        ordering = ["priority", "cv_id"]  # medium_overlap first, group by CV
```

### 4. `HumanLabel`
Label thực tế từ admin.

```python
class LabelValue(models.IntegerChoices):
    NOT_SUITABLE = 0, "Không phù hợp"
    SUITABLE     = 1, "Phù hợp"
    STRONG_FIT   = 2, "Rất phù hợp"

class DimScore(models.IntegerChoices):
    BAD  = 0, "Không phù hợp"   # ❌
    OK   = 1, "Tạm được"        # ⚠️
    GOOD = 2, "Tốt"             # ✅

class HumanLabel(models.Model):
    pair           = models.ForeignKey(PairQueue, on_delete=models.CASCADE,
                                       related_name="labels")

    # Dimension scores (0=bad, 1=ok, 2=good)
    skill_fit      = models.IntegerField(choices=DimScore.choices)   # kỹ năng khớp
    seniority_fit  = models.IntegerField(choices=DimScore.choices)   # cấp bậc
    experience_fit = models.IntegerField(choices=DimScore.choices)   # số năm kinh nghiệm
    domain_fit     = models.IntegerField(choices=DimScore.choices)   # domain/ngành

    # Overall — admin confirm hoặc override suggested value từ client
    overall        = models.IntegerField(choices=LabelValue.choices)

    note           = models.TextField(blank=True)
    labeled_by     = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    @property
    def binary_label(self) -> int:
        """Map sang LabeledPair.label cho ML: overall >= 1 → 1, overall == 0 → 0"""
        return 1 if self.overall >= 1 else 0

    class Meta:
        db_table = "labeling_human_label"
```

> **Note**: `suggested_overall` được tính ở **frontend** (không phải server) khi admin chọn 4 dimension scores. Server chỉ nhận và lưu giá trị final.
>
> Logic frontend: `avg = (skill + seniority + experience + domain) / 4` → avg ≥ 1.5 → suggest 2, avg ≥ 0.75 → suggest 1, else → suggest 0.

---

## Smart Pair Selection Algorithm

### Số lượng target

- **300 pairs**, chia cho ~**40 CVs** × **~7–8 jobs/CV**
- `max_pairs_per_cv = 8` — tránh 1 CV chiếm quá nhiều slots, giảm context-switch khi label
- Grouping: khi label, admin label hết tất cả jobs của 1 CV rồi mới chuyển sang CV tiếp theo

### Phân bổ

```
40% medium_overlap  = 120 pairs  → most uncertain, max info gain
30% high_overlap    =  90 pairs  → confirm positives
20% hard_negative   =  60 pairs  → confirm negatives
10% random          =  30 pairs  → diversity
```

### Split pre-assignment (lúc populate, không phải lúc label)

```
70% train = 210 pairs
15% val   =  45 pairs
15% test  =  45 pairs  ← fixed, không đổi sau populate
```

Mỗi bucket (medium/high/hard/random) được split độc lập để đảm bảo tỷ lệ đồng đều.

### Algorithm

```python
def generate_pair_queue(cvs, jobs, n_pairs=300, max_pairs_per_cv=8):
    """
    1. Tính overlap cho tất cả cặp CV-Job
    2. Phân loại theo selection_reason
    3. Giới hạn max_pairs_per_cv để tránh 1 CV chiếm quá nhiều
    4. Stratified sample theo tỷ lệ 40/30/20/10
    5. Pre-assign split 70/15/15 trong mỗi bucket
    6. Set priority: medium=1, high=2, hard=3, random=4
    """
    scorer = SkillOverlapScorer()
    buckets = {reason: [] for reason in SelectionReason}

    cv_pair_count = defaultdict(int)

    for cv in cvs:
        for job in jobs:
            if cv_pair_count[cv.cv_id] >= max_pairs_per_cv:
                continue
            overlap = scorer.score(cv, job)
            seniority_gap = abs(int(cv.seniority) - int(job.seniority))

            if 0.15 <= overlap < 0.40:
                reason = SelectionReason.MEDIUM_OVERLAP
            elif overlap >= 0.40:
                reason = SelectionReason.HIGH_OVERLAP
            elif seniority_gap > 1:
                reason = SelectionReason.HARD_NEGATIVE
            else:
                reason = SelectionReason.RANDOM

            buckets[reason].append((cv, job, overlap, reason))
            cv_pair_count[cv.cv_id] += 1

    ratio = {
        SelectionReason.MEDIUM_OVERLAP: 0.40,
        SelectionReason.HIGH_OVERLAP:   0.30,
        SelectionReason.HARD_NEGATIVE:  0.20,
        SelectionReason.RANDOM:         0.10,
    }
    priority_map = {
        SelectionReason.MEDIUM_OVERLAP: 1,
        SelectionReason.HIGH_OVERLAP:   2,
        SelectionReason.HARD_NEGATIVE:  3,
        SelectionReason.RANDOM:         4,
    }
    return stratified_sample(buckets, n_pairs, ratio, priority_map)
```

---

## API Endpoints

Tất cả endpoints yêu cầu `IsAdmin` permission (JWT token trong header).

### GET `/api/labeling/queue/`
Trả danh sách tất cả pending pairs của **CV hiện tại** (CV đầu tiên có pair PENDING, group by CV).
Admin label hết jobs của 1 CV rồi UI tự chuyển sang CV tiếp theo.

```json
Response:
{
  "cv": {
    "cv_id": 23,
    "skills": ["python", "django", "postgresql"],
    "seniority": "MID",
    "experience_years": 3.5,
    "education": "BACHELOR",
    "text_summary": "Backend developer with 3 years..."
  },
  "pairs": [
    {
      "pair_id": 142,
      "job": {
        "job_id": 891,
        "title": "Backend Engineer",
        "skills": ["python", "fastapi", "redis"],
        "seniority": "MID",
        "salary_min": 1500,
        "salary_max": 2500,
        "text_summary": "We are looking for..."
      },
      "hint": {
        "skill_overlap": 0.33,
        "common_skills": ["python"],
        "selection_reason": "medium_overlap"
      }
    }
  ],
  "progress": {
    "labeled": 87,
    "total": 300,
    "remaining": 213,
    "current_cv_pending": 6
  }
}
```

> **Tại sao group by CV**: Admin đọc 1 CV 1 lần, label 6–8 jobs liền → giảm cognitive load. Thay vì mỗi pair lại phải đọc CV mới.

### POST `/api/labeling/{pair_id}/submit/`
```json
Request:
{
  "skill_fit":      2,
  "seniority_fit":  1,
  "experience_fit": 2,
  "domain_fit":     2,
  "overall":        1,   // admin đã confirm hoặc override suggested value từ frontend
  "note":           ""
}

Response: { "status": "ok" }
```

### POST `/api/labeling/{pair_id}/skip/`
Bỏ qua pair không chắc chắn (status → SKIPPED).

### GET `/api/labeling/stats/`
```json
{
  "total_pairs": 300,
  "labeled": 87,
  "skipped": 12,
  "pending": 201,
  "label_distribution": {"0": 34, "1": 41, "2": 12},
  "by_reason": {
    "medium_overlap": {"labeled": 45, "total": 120},
    "high_overlap":   {"labeled": 30, "total": 90},
    "hard_negative":  {"labeled": 12, "total": 60},
    "random":         {"labeled": 0,  "total": 30}
  },
  "by_split": {
    "train": {"labeled": 65, "total": 210},
    "val":   {"labeled": 15, "total": 45},
    "test":  {"labeled": 7,  "total": 45}
  }
}
```

### GET `/api/labeling/export/`
Export toàn bộ labeled pairs sang format ML training.

```json
[
  {
    "cv_id": 23,
    "job_id": 891,
    "label": 1,
    "split": "train",
    "skill_fit": 2,
    "seniority_fit": 1,
    "experience_fit": 2,
    "domain_fit": 2,
    "overall": 1
  }
]
```

---

## Export Pipeline → ML Training

### Label mapping
```
HumanLabel.overall = 0  →  LabeledPair.label = 0  (no match)
HumanLabel.overall = 1  →  LabeledPair.label = 1  (match)
HumanLabel.overall = 2  →  LabeledPair.label = 1  (strong match, still positive)
```

### Dimension scores — 3 cách dùng cho ML

**Cách 1 (ngay bây giờ):** Chỉ dùng `overall` → `binary_label` cho `LabeledPair`. Compatible với pipeline hiện tại.

**Cách 2 (sau khi có 200+ labels):** Phân tích dimension scores để improve `PairLabeler`:
```python
# VD: skill_fit=2 nhưng domain_fit=0 → proxy label sai vì thiếu domain constraint
# → update PairLabeler để thêm domain matching
```

**Cách 3 (future):** Multi-task learning — GNN predict cả 4 dimensions + overall. Mỗi dimension là auxiliary loss.

### Split strategy
- **Test set cố định từ human labels** — pre-assigned lúc populate, không đổi
- Train/val có thể mix human + proxy labels
- Tỷ lệ: 70% train / 15% val / 15% test

```python
human_labels = load_human_labels("export.json")   # từ API export
proxy_labels = labeler.create_pairs(...)           # proxy labels hiện tại

test_pairs   = [p for p in human_labels if p.split == "test"]   # human only
train_pairs  = proxy_labels_train + [p for p in human_labels if p.split == "train"]
```

---

## Quality Control

**Single labeler:**
- Sau mỗi 50 pairs, review lại 10 pairs đã label để check consistency
- UI hiện thị lại 10 pairs ngẫu nhiên đã label để so sánh

---

## Management Command

```bash
python manage.py populate_pair_queue \
    --cvs-path data/linkedin_cvs.json \
    --jobs-path data/raw_jobs.jsonl \
    --n-pairs 300 \
    --max-per-cv 8
```

Command thực hiện theo thứ tự:
1. Load CVs và Jobs từ files
2. Upsert `LabelingCV` và `LabelingJob` (create_or_update theo cv_id/job_id)
3. Tính skill overlap và BM25 score cho tất cả cặp
4. Chọn 300 pairs theo stratified sampling với max_per_cv=8
5. Pre-assign split (70/15/15) trong mỗi bucket
6. Set priority theo selection_reason
7. Bulk insert vào `PairQueue` (skip existing pairs)

---

## Implementation Order

1. **`apps/labeling/` app** — tạo app mới, register trong INSTALLED_APPS
2. **Models** — LabelingCV, LabelingJob, PairQueue, HumanLabel + migrations
3. **Management command** — `populate_pair_queue`
4. **Serializers + Views** — DRF ViewSets
5. **URL routing** — mount vào `api/labeling/`
6. **Test với React UI** (week 11)

---

## Kết quả kỳ vọng sau labeling

| Labels | Expected AUC-ROC | Note |
|--------|-----------------|------|
| 0 (proxy only) | 0.70 (hiện tại) | Ceiling của proxy labels |
| 200 human | 0.72–0.75 | Mixed training |
| 300 human | 0.73–0.77 | ~40 CVs × ~7 jobs, test set 45 pairs |
| 500 human | 0.75–0.80 | Human test set credible |

Quan trọng nhất: **test set từ human labels** cho phép đo performance thật sự, không bị inflated bởi proxy label bias.
