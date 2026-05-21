"""JobFlow-GNN benchmark sandbox — forked from ml_service for thesis multi-dataset benchmarking.

This is a frozen fork of backend/ml_service. Do not import from production ml_service
inside this package; the sandbox must stay self-contained so it can be refactored
freely without breaking production.

Core modules:
    crawler     — only RawJob (dataclass kept for data/skill_extractor dep)
    cv_parser   — CVParser (kept for data/linkedin_cv_loader dep)
    embedding   — EmbeddingProvider
    graph       — GraphBuilder, schema
    models      — HeteroGraphSAGE, HeteroRGCN
    training    — Trainer
    evaluation  — metrics
    baselines   — BM25, Cosine, SkillOverlap baselines
    data        — dataset loaders, labeler, skill normalization
    config      — settings
    utils       — helpers
"""
