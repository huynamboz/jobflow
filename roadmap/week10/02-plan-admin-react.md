# Plan: Admin React App (Week 10–11)

> Build React admin panel tại `/admin` trong root project. Admin dùng để quản lý jobs, CVs, và **label CV-Job pairs** cho ML training.

---

## Tech Stack

| Layer | Lib | Lý do |
|-------|-----|-------|
| Framework | React 18 + Vite + TypeScript | Fast build, type-safe |
| UI | HeroUI (NextUI v2) + Tailwind CSS | Đẹp, consistent design system |
| State | Zustand | Lightweight, no boilerplate |
| HTTP | Axios | Interceptors cho auth token |
| Routing | React Router v6 | Standard |
| Form | React Hook Form | Nhẹ, tích hợp validation |

---

## Pages & Routes

```
/login              → LoginPage       (public)
/                   → Dashboard       (admin only)
/labeling           → LabelingPage    (admin only) ← Week 10 focus
/jobs               → JobsPage        (admin only)
/cvs                → CVsPage         (admin only)
```

---

## Folder Structure

```
admin/
├── src/
│   ├── api/                    # Axios calls — chỉ HTTP, không có logic
│   │   ├── client.ts           # Axios instance + interceptors (attach token, handle 401)
│   │   ├── auth.api.ts         # login, me, refresh
│   │   ├── labeling.api.ts     # queue, submit, skip, stats, export
│   │   ├── jobs.api.ts         # list, detail
│   │   └── cvs.api.ts          # list, detail
│   │
│   ├── services/               # Business logic — transform data, compute derived values
│   │   ├── auth.service.ts     # save/clear token, decode JWT
│   │   └── labeling.service.ts # computeSuggestedOverall(dims), formatExport
│   │
│   ├── stores/                 # Zustand stores — app state
│   │   ├── auth.store.ts       # user, token, isAuthenticated
│   │   └── labeling.store.ts   # currentCV, pairs, progress, pendingSubmit
│   │
│   ├── types/                  # TypeScript interfaces
│   │   ├── auth.types.ts
│   │   ├── labeling.types.ts   # LabelingCV, LabelingJob, PairQueue, SubmitPayload
│   │   └── api.types.ts        # ApiResponse<T>, PaginatedResponse<T>
│   │
│   ├── hooks/                  # Custom hooks (compose store + api)
│   │   ├── useAuth.ts          # login, logout, isAdmin check
│   │   ├── useQueue.ts         # fetchQueue, submitLabel, skipPair
│   │   └── useStats.ts         # fetchStats
│   │
│   ├── components/
│   │   ├── layout/
│   │   │   ├── AppLayout.tsx   # Sidebar + Header + Outlet
│   │   │   ├── Sidebar.tsx     # Nav links
│   │   │   └── Header.tsx      # User info + logout
│   │   │
│   │   ├── labeling/           # Labeling-specific components
│   │   │   ├── CVPanel.tsx     # Hiển thị CV info (left panel)
│   │   │   ├── JobCard.tsx     # 1 job cần label (skill_fit, seniority_fit, ...)
│   │   │   ├── DimScoreInput.tsx  # 3-button selector: ❌ ⚠️ ✅
│   │   │   ├── OverallSelector.tsx # 0/1/2 overall + suggested highlight
│   │   │   ├── LabelingProgress.tsx # Progress bar labeled/total
│   │   │   └── StatsCard.tsx   # Stats dashboard cards
│   │   │
│   │   └── ui/                 # Atomic reusable components
│   │       ├── ProtectedRoute.tsx
│   │       ├── LoadingSpinner.tsx
│   │       └── ErrorBoundary.tsx
│   │
│   ├── pages/
│   │   ├── LoginPage.tsx
│   │   ├── DashboardPage.tsx
│   │   ├── LabelingPage.tsx    # Week 10 focus
│   │   ├── JobsPage.tsx
│   │   └── CVsPage.tsx
│   │
│   └── router/
│       └── index.tsx           # Route definitions + ProtectedRoute wrapper
│
├── index.html
├── package.json
├── tailwind.config.ts
├── vite.config.ts
└── tsconfig.json
```

---

## Data Flow

```
API call (api/)
    ↓ raw HTTP response
Service (services/)
    ↓ transform, validate, compute derived values
Hook (hooks/)
    ↓ update store + return data/handlers to component
Store (stores/)  ←→  Component (components/ + pages/)
```

**Nguyên tắc:**
- `api/` không biết về store
- `services/` không biết về store
- `stores/` không gọi API trực tiếp
- `hooks/` là điểm kết nối duy nhất giữa api + store + components

---

## Layer Chi Tiết

### `api/client.ts`
```ts
const client = axios.create({ baseURL: "http://localhost:8000/api" });

// Request interceptor: attach token
client.interceptors.request.use(config => {
  const token = useAuthStore.getState().token;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Response interceptor: 401 → logout
client.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) useAuthStore.getState().logout();
    return Promise.reject(err);
  }
);
```

### `api/labeling.api.ts`
```ts
export const labelingApi = {
  getQueue:    ()         => client.get<ApiResponse<QueueResponse>>("/labeling/queue/"),
  submit:      (id, data) => client.post<ApiResponse<void>>(`/labeling/${id}/submit/`, data),
  skip:        (id)       => client.post<ApiResponse<void>>(`/labeling/${id}/skip/`),
  getStats:    ()         => client.get<ApiResponse<StatsResponse>>("/labeling/stats/"),
  export:      ()         => client.get<ApiResponse<ExportItem[]>>("/labeling/export/"),
};
```

### `services/labeling.service.ts`
```ts
// Computed trên frontend, không cần request thêm
export function computeSuggestedOverall(dims: DimScores): 0 | 1 | 2 {
  const avg = (dims.skill_fit + dims.seniority_fit + dims.experience_fit + dims.domain_fit) / 4;
  if (avg >= 1.5) return 2;
  if (avg >= 0.75) return 1;
  return 0;
}
```

### `stores/auth.store.ts`
```ts
interface AuthStore {
  user: User | null;
  token: string | null;
  setAuth: (user, token) => void;
  logout: () => void;
  isAuthenticated: () => boolean;
}
```

### `stores/labeling.store.ts`
```ts
interface LabelingStore {
  currentCV: LabelingCV | null;
  pairs: PairQueue[];          // tất cả pending pairs của CV hiện tại
  progress: ProgressStats;
  activePairId: number | null; // pair đang được highlight/focus
  setQueue: (data: QueueResponse) => void;
  markLabeled: (pairId: number) => void;
  markSkipped: (pairId: number) => void;
}
```

---

## Labeling Page UX

```
┌─────────────────────────────────────────────────────────┐
│  [Progress] 87 / 300 labeled  ████████░░░░░░░  29%     │
├──────────────────┬──────────────────────────────────────┤
│                  │  Job 1: Backend Engineer           ▼ │
│  CV #202         │  Skills: python, fastapi, redis      │
│  MID • 3.5 yrs   │  Seniority: MID • Salary: $1500–2500 │
│  BACHELOR        │                                      │
│                  │  skill_fit:      ❌  ⚠️  [✅]        │
│  Skills:         │  seniority_fit:  ❌  [⚠️]  ✅        │
│  • python        │  experience_fit: ❌  ⚠️  [✅]        │
│  • django        │  domain_fit:     ❌  ⚠️  [✅]        │
│  • postgresql    │                                      │
│                  │  Suggested: Phù hợp (1) ← auto      │
│  Summary:        │  Overall: [0]  [1★]  [2]            │
│  Backend dev...  │                                      │
│                  │  Note: ________________             │
│                  │                                      │
│                  │  [Skip]           [Submit →]         │
│                  ├──────────────────────────────────────┤
│                  │  Job 2: Python Developer          ▼  │
│                  │  ...                                 │
└──────────────────┴──────────────────────────────────────┘
```

**Interaction flow:**
1. Load queue → hiện CV bên trái, danh sách jobs bên phải (collapsed)
2. Click vào job → expand form
3. Admin chọn 4 dims → `suggested_overall` auto-highlight
4. Admin confirm overall → Submit → job collapse, next job auto-expand
5. Khi hết jobs của CV → fetch queue mới (CV tiếp theo)

---

## Implementation Order

### Week 10 (backend xong, frontend foundation)

1. **Init project** — Vite + React + TypeScript + Tailwind + HeroUI
2. **api/ layer** — client.ts, auth.api.ts, labeling.api.ts
3. **types/** — tất cả TypeScript interfaces
4. **stores/** — auth.store.ts, labeling.store.ts
5. **services/** — labeling.service.ts (computeSuggestedOverall)
6. **hooks/** — useAuth.ts, useQueue.ts
7. **Layout + Router** — AppLayout, Sidebar, ProtectedRoute
8. **LoginPage** — form + auth flow
9. **LabelingPage** — CVPanel + JobCard + DimScoreInput + submit flow
10. **DashboardPage** — stats cards

### Week 11 (polish + jobs/CVs pages)

11. **JobsPage** — list jobs từ backend
12. **CVsPage** — list CVs
13. **Export button** — download JSON for ML
14. **UX polish** — keyboard shortcuts (1/2/3 cho dims, Enter submit, S skip)

---

## Keyboard Shortcuts (UX cho labeling nhanh)

| Key | Action |
|-----|--------|
| `1` / `2` / `3` | Chọn DimScore (0/1/2) cho dimension đang focus |
| `Tab` | Next dimension |
| `Enter` | Submit label |
| `S` | Skip pair |

Mục tiêu: label 1 cặp trong < 30 giây khi quen.
