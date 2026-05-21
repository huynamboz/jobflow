from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    embedding_provider: str = "english"
    embedding_dim: int = 384

    data_dir: Path = Path("./data")
    skill_alias_path: Path = Path(__file__).resolve().parent.parent / "data" / "skill-alias.json"

    service_port: int = 8001

    num_cvs: int = 800
    num_jobs: int = 1500
    num_positive_pairs: int = 2000
    random_seed: int = 42

    # GNN architecture
    gnn_hidden_channels: int = 128
    gnn_num_layers: int = 2

    # Training
    learning_rate: float = 1e-3
    weight_decay: float = 1e-5
    num_epochs: int = 50
    early_stopping_patience: int = 10

    # Hybrid scoring weights (alpha + beta + gamma = 1.0)
    hybrid_alpha: float = 0.6  # GNN score weight
    hybrid_beta: float = 0.3  # Skill overlap weight
    hybrid_gamma: float = 0.1  # Seniority match weight

    # Eligibility threshold for final recommendations
    eligibility_threshold: float = 0.65

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
