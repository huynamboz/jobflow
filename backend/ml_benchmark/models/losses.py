from __future__ import annotations

import torch
import torch.nn.functional as F


def bpr_loss(pos_scores: torch.Tensor, neg_scores: torch.Tensor) -> torch.Tensor:
    """Bayesian Personalized Ranking loss.

    loss = -log(sigmoid(pos - neg)).mean()
    """
    return -F.logsigmoid(pos_scores - neg_scores).mean()
