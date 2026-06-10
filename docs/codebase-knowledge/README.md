# Codebase Knowledge

Bộ tài liệu nghiên cứu toàn bộ codebase (sinh 2026-06-10, từ phân tích code + DB thật). Đọc [01-architecture-overview.md](01-architecture-overview.md) trước — nó là bản đồ + mục lục.

| # | File | Trả lời câu hỏi |
|---|---|---|
| 01 | [architecture-overview](01-architecture-overview.md) | Hệ thống gồm gì, data chảy thế nào? |
| 02 | [graph-features](02-graph-features.md) | Đồ thị/node features/role taxonomy/skill layer? |
| 03 | [labeling-pipeline](03-labeling-pipeline.md) | Nhãn sinh ra thế nào (LLM label)? |
| 04 | [label-data-analysis](04-label-data-analysis.md) | Data nhãn thực tế trông ra sao (phân phối, gap)? |
| 05 | [training-pipeline](05-training-pipeline.md) | GNN + reranker train thế nào, checkpoint chứa gì? |
| 06 | [inference-pipeline](06-inference-pipeline.md) | Serving 2-stage, hybrid score, job pool live? |
| 07 | [evaluation-tuning](07-evaluation-tuning.md) | Tune weights + eval harness + lịch sử số liệu 019/020? |
| 08 | [improvement-opportunities](08-improvement-opportunities.md) | Cần cải thiện gì, ưu tiên ra sao? |
| 09 | [pipeline-audit](09-pipeline-audit.md) | Audit end-to-end: 20 lỗ hổng xếp hạng + kế hoạch fix theo đợt |
| 10 | [master-plan](10-master-plan.md) | **Kế hoạch tổng quan 4 đợt** (checkbox tracking, DoD) — bắt đầu từ đây |
| 11 | [project-journey](11-project-journey.md) | **Tổng hợp TOÀN BỘ hành trình** (018→023): timeline, số liệu, artifact — đọc 1 file nắm hết |
| 12 | [gnn-v2-proposal](12-gnn-v2-proposal.md) | **Proposal GNN v2** (handoff đầy đủ): chẩn đoán, 3 vòng cải thiện, quy trình, bẫy đã biết |

Quy ước: khi codebase đổi đáng kể (retrain, đổi pipeline), cập nhật doc tương ứng trong cùng PR.
