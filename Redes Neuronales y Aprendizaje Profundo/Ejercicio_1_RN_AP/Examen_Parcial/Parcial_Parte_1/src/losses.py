"""Funciones de perdida y metricas de evaluacion."""
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


class FocalLoss(nn.Module):
    """Focal loss binaria (Lin et al., 2017).

    Reduce el peso de ejemplos faciles y enfoca el entrenamiento
    en ejemplos dificiles mediante el factor (1-pt)^gamma.
    """

    def __init__(self, gamma: float = 2.0, alpha: float = 0.5):
        super().__init__()
        self.gamma = gamma
        self.alpha = alpha

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        bce = F.binary_cross_entropy_with_logits(logits, target, reduction="none")
        p = torch.sigmoid(logits)
        pt = p * target + (1 - p) * (1 - target)
        alpha_t = self.alpha * target + (1 - self.alpha) * (1 - target)
        loss = alpha_t * (1 - pt) ** self.gamma * bce
        return loss.mean()


def compute_metrics(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    threshold: float = 0.5,
) -> dict:
    """Calcula accuracy, precision, recall, F1 y AUC-ROC."""
    y_pred = (y_prob >= threshold).astype(int)
    return {
        "accuracy":  float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall":    float(recall_score(y_true, y_pred, zero_division=0)),
        "f1":        float(f1_score(y_true, y_pred, zero_division=0)),
        "auc":       float(roc_auc_score(y_true, y_prob))
                     if len(set(y_true)) > 1 else float("nan"),
    }
