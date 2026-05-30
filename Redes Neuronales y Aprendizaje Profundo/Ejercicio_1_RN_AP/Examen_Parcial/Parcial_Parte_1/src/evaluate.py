"""Evaluacion de modelos sobre un DataLoader."""
import numpy as np
import torch

from .losses import compute_metrics


@torch.no_grad()
def evaluate(model, loader, device=None) -> tuple:
    """Evalua el modelo en un DataLoader completo.

    Args:
        model: Modelo PyTorch en modo eval.
        loader: DataLoader que devuelve (x, y, path).
        device: Dispositivo PyTorch (None = auto-detectar).

    Returns:
        Tupla (metrics_dict, y_true, y_prob, paths) donde:
          - metrics_dict: accuracy, precision, recall, f1, auc
          - y_true: ndarray de etiquetas reales
          - y_prob: ndarray de probabilidades predichas
          - paths: lista de rutas de imagen
    """
    if device is None:
        device = next(model.parameters()).device
    model.eval()
    ys, ps, paths = [], [], []

    for x, y, p in loader:
        x = x.to(device)
        prob = torch.sigmoid(model(x).squeeze(1)).cpu().numpy()
        ys.extend(y.numpy())
        ps.extend(prob)
        paths.extend(p)

    ys = np.array(ys)
    ps = np.array(ps)
    return compute_metrics(ys, ps), ys, ps, paths
