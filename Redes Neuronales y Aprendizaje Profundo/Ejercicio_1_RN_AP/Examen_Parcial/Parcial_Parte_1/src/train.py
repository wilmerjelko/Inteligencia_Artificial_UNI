"""Bucle de entrenamiento con early stopping por val F1."""
import time

import numpy as np
import pandas as pd
import torch

from .losses import compute_metrics


def train_model(
    model,
    loaders: dict,
    criterion,
    epochs: int = 10,
    lr: float = 1e-3,
    weight_decay: float = 1e-4,
    params_to_optimize=None,
    patience: int = 3,
    label: str = "model",
    device=None,
    use_amp: bool = False,
) -> tuple:
    """Entrena el modelo con AdamW + CosineAnnealingLR + early stopping por F1.

    Args:
        model: Modelo PyTorch.
        loaders: Dict con keys 'train' y 'val'.
        criterion: Funcion de perdida.
        epochs: Numero maximo de epocas.
        lr: Learning rate inicial.
        weight_decay: Regularizacion L2.
        params_to_optimize: Lista de parametros a optimizar (None = todos).
        patience: Epocas sin mejora en val F1 antes de parar.
        label: Etiqueta para los logs.
        device: Dispositivo PyTorch (None = auto-detectar).
        use_amp: Activar mixed precision (requiere CUDA).

    Returns:
        (model_best, history_df)
    """
    if device is None:
        device = next(model.parameters()).device
    model.to(device)

    opt = torch.optim.AdamW(
        params_to_optimize or model.parameters(),
        lr=lr,
        weight_decay=weight_decay,
    )
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(epochs, 1))
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    history, best_f1, best_state, bad = [], -1.0, None, 0

    for ep in range(1, epochs + 1):
        model.train()
        t0, losses = time.time(), []

        for x, y, _ in loaders["train"]:
            x, y = x.to(device), y.to(device)
            opt.zero_grad(set_to_none=True)
            if use_amp:
                with torch.amp.autocast("cuda"):
                    logits = model(x).squeeze(1)
                    loss = criterion(logits, y)
                scaler.scale(loss).backward()
                scaler.step(opt)
                scaler.update()
            else:
                logits = model(x).squeeze(1)
                loss = criterion(logits, y)
                loss.backward()
                opt.step()
            losses.append(loss.item())

        sched.step()
        val_metrics, *_ = _eval_fast(model, loaders["val"], device)

        history.append({
            "epoch": ep,
            "train_loss": float(np.mean(losses)),
            **{f"val_{k}": v for k, v in val_metrics.items()},
        })
        print(
            f"[{label}] ep {ep:02d} | loss {np.mean(losses):.3f} | "
            f"val F1 {val_metrics['f1']:.3f} | val AUC {val_metrics['auc']:.3f} | "
            f"{time.time() - t0:.1f}s"
        )

        if val_metrics["f1"] > best_f1:
            best_f1 = val_metrics["f1"]
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            bad = 0
        else:
            bad += 1
            if bad >= patience:
                print(f"Early stopping en epoch {ep}")
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    return model, pd.DataFrame(history)


@torch.no_grad()
def _eval_fast(model, loader, device):
    """Evaluacion rapida interna (sin guardar paths)."""
    model.eval()
    ys, ps, paths = [], [], []
    for x, y, p in loader:
        x = x.to(device)
        prob = torch.sigmoid(model(x).squeeze(1)).cpu().numpy()
        ys.extend(y.numpy())
        ps.extend(prob)
        paths.extend(p)
    ys, ps = np.array(ys), np.array(ps)
    return compute_metrics(ys, ps), ys, ps, paths
