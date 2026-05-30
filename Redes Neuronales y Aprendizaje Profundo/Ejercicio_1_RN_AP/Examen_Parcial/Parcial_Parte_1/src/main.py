#!/usr/bin/env python3
"""main.py -- Punto de entrada unico para entrenamiento y evaluacion de clasificacion de llantas.

Uso rapido:
    python src/main.py --config configs/config_baseline.yaml
    python src/main.py --config configs/config_ablation_focal.yaml --data_dir /ruta/al/dataset

El parametro --data_dir sobreescribe data_dir del YAML (util en Colab/Kaggle).
"""
import argparse
import json
import os
import random
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import torch
import yaml
from sklearn.metrics import confusion_matrix as sk_cm

warnings.filterwarnings("ignore")

# Asegurar que la raiz del proyecto este en el path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.data.dataset import build_loaders
from src.data.transforms import get_eval_transforms, get_train_transforms
from src.error_analysis import run_error_analysis
from src.evaluate import evaluate
from src.interpretability import GradCAM
from src.losses import FocalLoss, compute_metrics
from src.models.tirecnn import TireCNN
from src.models.transfer import build_efficientnet_b0, build_resnet50
from src.train import train_model


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _list_images(folder: Path) -> pd.DataFrame:
    exts = {".jpg", ".jpeg", ".png", ".bmp"}
    rows = []
    for cls_dir in sorted(folder.iterdir()):
        if cls_dir.is_dir():
            for p in cls_dir.iterdir():
                if p.suffix.lower() in exts:
                    label = 1 if cls_dir.name.lower() == "cracked" else 0
                    rows.append({"path": str(p), "label": label, "class": cls_dir.name})
    return pd.DataFrame(rows)


def _set_seeds(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def _build_criterion(cfg: dict, device: torch.device):
    loss_type = cfg.get("loss", "bce")
    if loss_type == "focal":
        return FocalLoss(
            gamma=cfg.get("focal_gamma", 2.0),
            alpha=cfg.get("focal_alpha", 0.5),
        )
    if loss_type == "bce_pos_weight":
        pw = cfg.get("_pos_weight", 1.0)
        return torch.nn.BCEWithLogitsLoss(
            pos_weight=torch.tensor([pw], device=device)
        )
    return torch.nn.BCEWithLogitsLoss()


def _build_model(cfg: dict) -> torch.nn.Module:
    arch = cfg.get("model", "tirecnn")
    freeze = cfg.get("freeze_backbone", True)
    if arch == "resnet50":
        return build_resnet50(freeze_backbone=freeze)
    if arch == "efficientnet_b0":
        return build_efficientnet_b0(freeze_backbone=freeze)
    return TireCNN(dropout=cfg.get("dropout", 0.4))


# ---------------------------------------------------------------------------
# Figuras por ejecucion
# ---------------------------------------------------------------------------

def _optimal_threshold(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    best_thr, best_f1 = 0.5, 0.0
    for t in np.arange(0.05, 0.95, 0.01):
        m = compute_metrics(y_true, y_prob, threshold=float(t))
        if m["f1"] > best_f1:
            best_f1, best_thr = m["f1"], float(t)
    return best_thr


def _cm_dict(y_true: np.ndarray, y_prob: np.ndarray, threshold: float) -> dict:
    y_pred = (y_prob >= threshold).astype(int)
    tn, fp, fn, tp = sk_cm(y_true, y_pred).ravel()
    return {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}


def _save_fig4(df_tr, df_val, df_test, out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(3)
    w = 0.35
    dfs = [df_tr, df_val, df_test]
    n_n = [int((d["label"] == 0).sum()) for d in dfs]
    n_c = [int((d["label"] == 1).sum()) for d in dfs]
    ax.bar(x - w / 2, n_n, w, label="Normal",  color="#4878CF")
    ax.bar(x + w / 2, n_c, w, label="Cracked", color="#D65F5F")
    ax.set_xticks(x)
    ax.set_xticklabels(["Train", "Val", "Test"])
    ax.set_ylabel("Imagenes")
    ax.set_title("Distribucion de clases por split")
    ax.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "fig4_dataset_splits.png", dpi=120, bbox_inches="tight")
    plt.close()


def _save_fig6(y_true: np.ndarray, y_prob: np.ndarray,
               label: str, out_dir: Path, canonical: bool = False) -> None:
    thrs = np.arange(0.05, 0.95, 0.01)
    P, R, F = [], [], []
    for t in thrs:
        m = compute_metrics(y_true, y_prob, threshold=float(t))
        P.append(m["precision"]); R.append(m["recall"]); F.append(m["f1"])
    best = thrs[int(np.argmax(F))]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(thrs, P, label="Precision", color="#4878CF")
    ax.plot(thrs, R, label="Recall",    color="#D65F5F")
    ax.plot(thrs, F, label="F1",        color="#6ACC65", lw=2)
    ax.axvline(best, color="gray", ls="--", alpha=0.7, label=f"Optimo={best:.2f}")
    ax.set_xlabel("Umbral"); ax.set_ylabel("Metrica")
    ax.set_title(f"P/R/F1 vs umbral ({label})")
    ax.legend(); plt.tight_layout()
    fname = "fig6_umbral_precision_recall.png" if canonical else f"fig6_{label}.png"
    plt.savefig(out_dir / fname, dpi=120, bbox_inches="tight")
    plt.close()


def _save_fig_cm(cm_d: dict, label: str, out_dir: Path, canonical: bool = False) -> None:
    arr = np.array([[cm_d["tn"], cm_d["fp"]], [cm_d["fn"], cm_d["tp"]]])
    fig, ax = plt.subplots(figsize=(5, 4))
    sns.heatmap(arr, annot=True, fmt="d", cmap="Blues",
                xticklabels=["Normal", "Cracked"],
                yticklabels=["Normal", "Cracked"], ax=ax)
    ax.set_xlabel("Prediccion"); ax.set_ylabel("Real")
    ax.set_title(f"Confusion matrix ({label})")
    plt.tight_layout()
    fname = "fig3_confusion_matrix.png" if canonical else f"fig3_{label}_cm.png"
    plt.savefig(out_dir / fname, dpi=120, bbox_inches="tight")
    plt.close()


def _save_fig5(history: pd.DataFrame, label: str, out_dir: Path, canonical: bool = False) -> None:
    """Curvas de loss en train y F1/AUC en validacion por epoch."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    # --- Loss ---
    ax = axes[0]
    ax.plot(history["epoch"], history["train_loss"], color="#4878CF", label="Train loss")
    ax.set_xlabel("Epoch"); ax.set_ylabel("Loss")
    ax.set_title(f"Perdida en entrenamiento ({label})")
    ax.legend(); ax.grid(alpha=0.3)

    # --- F1 + AUC validacion ---
    ax = axes[1]
    if "val_f1" in history.columns:
        ax.plot(history["epoch"], history["val_f1"],  color="#6ACC65", label="Val F1",  lw=2)
    if "val_auc" in history.columns:
        ax.plot(history["epoch"], history["val_auc"], color="#D65F5F", label="Val AUC", lw=2)
    ax.set_xlabel("Epoch"); ax.set_ylabel("Score")
    ax.set_title(f"F1 y AUC en validacion ({label})")
    ax.set_ylim(0, 1.05); ax.legend(); ax.grid(alpha=0.3)

    plt.suptitle(f"Historial de entrenamiento — {label}", fontsize=13)
    plt.tight_layout()
    fname = "fig5_training_history.png" if canonical else f"fig5_{label}_history.png"
    plt.savefig(out_dir / fname, dpi=120, bbox_inches="tight")
    plt.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Tire Classification -- Trainer")
    parser.add_argument("--config", required=True, help="Ruta al archivo YAML de configuracion")
    parser.add_argument(
        "--data_dir", default=None,
        help="Override de data_dir (directorio con training_data/ y testing_data/)"
    )
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if args.data_dir:
        cfg["data_dir"] = args.data_dir

    if "data_dir" not in cfg or cfg["data_dir"] is None:
        print("ERROR: data_dir no especificado. Usa --data_dir o definelo en el YAML.")
        sys.exit(1)

    # -- Setup --
    seed = cfg.get("seed", 42)
    _set_seeds(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    on_gpu = device.type == "cuda"
    num_workers = cfg.get(
        "num_workers",
        2 if (on_gpu or sys.platform != "win32") else 0,
    )
    print(f"Device: {device}  |  Config: {args.config}")

    # -- Dataset --
    data_dir = Path(cfg["data_dir"])
    df_train_full = _list_images(data_dir / "training_data")
    df_test       = _list_images(data_dir / "testing_data")

    from sklearn.model_selection import train_test_split
    df_tr, df_val = train_test_split(
        df_train_full,
        test_size=cfg.get("val_split", 0.15),
        stratify=df_train_full["label"],
        random_state=seed,
    )
    print(f"train={len(df_tr)}  val={len(df_val)}  test={len(df_test)}")

    img_size  = cfg.get("img_size", 224)
    use_aug   = cfg.get("augmentation", True)
    train_tf  = get_train_transforms(img_size) if use_aug else get_eval_transforms(img_size)
    eval_tf   = get_eval_transforms(img_size)

    loaders = build_loaders(
        df_tr, df_val, df_test, train_tf, eval_tf,
        batch_size=cfg.get("batch_size", 32),
        num_workers=num_workers,
    )

    # -- pos_weight (calculado a partir del train split) --
    if cfg.get("loss") == "bce_pos_weight":
        n_neg = int((df_tr["label"] == 0).sum())
        n_pos = int((df_tr["label"] == 1).sum())
        cfg["_pos_weight"] = n_neg / max(n_pos, 1)
        print(f"pos_weight = {cfg['_pos_weight']:.3f}  (neg={n_neg}, pos={n_pos})")

    # -- Modelo y criterio --
    model     = _build_model(cfg).to(device)
    criterion = _build_criterion(cfg, device)
    arch      = cfg.get("model", "tirecnn")
    patience  = cfg.get("patience", 10 if on_gpu else 3)

    # -- Directorio de salida --
    work_dir = Path(cfg.get("work_dir", "."))
    ckpt_dir = work_dir / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    # -- Entrenamiento --
    if arch in ("resnet50", "efficientnet_b0"):
        # Fase 1: solo cabeza
        params_head  = [p for p in model.parameters() if p.requires_grad]
        epochs_head  = cfg.get("epochs_head", 10 if on_gpu else 2)
        model, hist1 = train_model(
            model, loaders, criterion,
            epochs=epochs_head, lr=cfg.get("lr_head", 1e-3),
            params_to_optimize=params_head, patience=patience,
            label=f"{arch}/head", device=device, use_amp=on_gpu,
        )
        # Fase 2: fine-tuning gradual
        default_ft = (
            ["layer3", "layer4", "fc"] if arch == "resnet50"
            else ["features.7", "features.8", "classifier"]
        )
        ft_layers = cfg.get("ft_layers", default_ft)
        for name, p in model.named_parameters():
            p.requires_grad = any(name.startswith(lyr) for lyr in ft_layers)
        params_ft   = [p for p in model.parameters() if p.requires_grad]
        epochs_ft   = cfg.get("epochs", 50 if on_gpu else 5)
        model, hist2 = train_model(
            model, loaders, criterion,
            epochs=epochs_ft, lr=cfg.get("lr_ft", 1e-4),
            params_to_optimize=params_ft, patience=patience,
            label=f"{arch}/FT", device=device, use_amp=on_gpu,
        )
        history = pd.concat([hist1, hist2], ignore_index=True)
    else:
        epochs = cfg.get("epochs", 50 if on_gpu else 8)
        model, history = train_model(
            model, loaders, criterion,
            epochs=epochs, lr=cfg.get("lr", 1e-3),
            patience=patience, label=arch, device=device, use_amp=on_gpu,
        )

    # -- Evaluacion en test --
    test_metrics, y_true, y_prob, paths = evaluate(model, loaders["test"], device=device)
    print(f"\nTEST (thr=0.50): {json.dumps({k: round(v, 4) for k, v in test_metrics.items()}, indent=2)}")

    # -- Umbral optimo y metricas finales --
    opt_thr = _optimal_threshold(y_true, y_prob)
    opt_metrics = compute_metrics(y_true, y_prob, threshold=opt_thr)
    cm_opt = _cm_dict(y_true, y_prob, opt_thr)
    print(f"TEST (thr_opt={opt_thr:.2f}): F1={opt_metrics['f1']:.4f}  AUC={opt_metrics['auc']:.4f}")

    # -- Guardar checkpoint --
    ckpt_name = cfg.get("checkpoint_name", f"{arch}.pt")
    torch.save(model.state_dict(), ckpt_dir / ckpt_name)
    print(f"Checkpoint: {ckpt_dir / ckpt_name}")

    # -- Figuras de esta ejecucion --
    figures_dir = work_dir / "figures"
    figures_dir.mkdir(exist_ok=True)
    run_label   = Path(args.config).stem.replace("config_", "")
    is_baseline = run_label == "baseline"
    _save_fig4(df_tr, df_val, df_test, figures_dir)
    _save_fig5(history, run_label, figures_dir, canonical=is_baseline)
    _save_fig6(y_true, y_prob, run_label, figures_dir, canonical=is_baseline)
    _save_fig_cm(cm_opt, run_label, figures_dir, canonical=is_baseline)
    print(f"Figuras guardadas en: {figures_dir}")

    # -- Acumular resultados en metrics_runs.json --
    runs_path = work_dir / "metrics_runs.json"
    runs = {}
    if runs_path.exists():
        with open(runs_path) as f:
            runs = json.load(f).get("runs", {})
    runs[run_label] = {
        "model":       arch,
        "config":      Path(args.config).name,
        "augmentation": use_aug,
        "loss":        cfg.get("loss", "bce"),
        "test_thr05":  dict(test_metrics),
        "test_thr_opt": {**opt_metrics, "threshold": opt_thr},
        "cm_opt":      cm_opt,
        "dataset":     {"train": len(df_tr), "val": len(df_val), "test": len(df_test)},
    }
    with open(runs_path, "w", encoding="utf-8") as f:
        json.dump({"runs": runs}, f, indent=2)
    print(f"Acumulado en: {runs_path}")

    # metrics_run.json (compatibilidad con colab_runner)
    with open(work_dir / "metrics_run.json", "w", encoding="utf-8") as f:
        json.dump({
            "config": str(args.config),
            "test_metrics": {**opt_metrics, "threshold": opt_thr},
        }, f, indent=2)

    # -- Error analysis opcional --
    if cfg.get("run_error_analysis", False):
        if arch == "resnet50":
            cam_layer = model.layer4[-1]
        elif arch == "efficientnet_b0":
            cam_layer = model.features[-1]
        else:
            cam_layer = model.blocks[-1]
        cam_engine = GradCAM(model, cam_layer)
        run_error_analysis(
            y_true, y_prob, paths, cam_engine,
            output_dir=str(work_dir / "outputs" / "errors"),
            figures_dir=str(figures_dir),
        )


if __name__ == "__main__":
    main()
