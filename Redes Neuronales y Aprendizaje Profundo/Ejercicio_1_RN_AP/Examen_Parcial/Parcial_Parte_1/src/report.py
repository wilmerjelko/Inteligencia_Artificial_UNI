#!/usr/bin/env python3
"""report.py -- Genera fig1 y fig2 comparativos a partir de metrics_runs.json.

Debe ejecutarse DESPUES de haber corrido todos los configs con main.py.

Uso:
    python src/report.py --work_dir .
"""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def _fig1_comparison(runs: dict, out_dir: Path) -> None:
    """Comparativa de metricas en test para todos los runs (umbral optimo)."""
    if len(runs) < 2:
        print("fig1: se necesitan al menos 2 runs. Saltando.")
        return

    metrics_keys = ["accuracy", "precision", "recall", "f1", "auc"]
    labels = list(runs.keys())
    x = np.arange(len(metrics_keys))
    w = min(0.8 / len(labels), 0.25)
    colors = ["#4878CF", "#D65F5F", "#6ACC65", "#B47CC7", "#C4AD66", "#77BEDB"]

    fig, ax = plt.subplots(figsize=(11, 5))
    for i, label in enumerate(labels):
        tm = runs[label].get("test_thr_opt", runs[label].get("test_thr05", {}))
        vals = [tm.get(k, 0.0) for k in metrics_keys]
        offset = (i - (len(labels) - 1) / 2.0) * w
        bars = ax.bar(x + offset, vals, w,
                      label=label, color=colors[i % len(colors)], alpha=0.85)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.01,
                    f"{v:.3f}", ha="center", va="bottom", fontsize=7)

    ax.set_xticks(x)
    ax.set_xticklabels([k.upper() for k in metrics_keys])
    ax.set_ylim(0, 1.18)
    ax.set_ylabel("Score")
    ax.set_title("Comparativa de metricas en test (umbral optimo por F1-val)")
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    out = out_dir / "fig1_metricas_comparativa.png"
    plt.savefig(out, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"Guardado: {out}")


def _fig2_ablation(runs: dict, out_dir: Path) -> None:
    """Ablacion: F1 y AUC en test para variantes clave."""
    abl_keys = [k for k in runs
                if "ablation" in k or k in ("baseline", "ablation_focal",
                                             "ablation_noaug", "ablation_scratch")]
    if len(abl_keys) < 2:
        print("fig2: se necesitan al menos 2 variantes de ablacion. Saltando.")
        return

    f1s  = [runs[k].get("test_thr_opt", {}).get("f1",  0.0) for k in abl_keys]
    aucs = [runs[k].get("test_thr_opt", {}).get("auc", 0.0) for k in abl_keys]

    x = np.arange(len(abl_keys))
    w = 0.35
    fig, ax = plt.subplots(figsize=(10, 5))
    b1 = ax.bar(x - w / 2, f1s,  w, label="F1 test",  color="#4878CF", alpha=0.85)
    b2 = ax.bar(x + w / 2, aucs, w, label="AUC test", color="#D65F5F", alpha=0.85)
    for bar, v in list(zip(b1, f1s)) + list(zip(b2, aucs)):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.005,
                f"{v:.3f}", ha="center", va="bottom", fontsize=8)

    short_labels = [k.replace("ablation_", "").replace("_", "\n") for k in abl_keys]
    ax.set_xticks(x)
    ax.set_xticklabels(short_labels, fontsize=9)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Score")
    ax.set_title("Estudio de ablacion: F1 y AUC en test (umbral optimo)")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    out = out_dir / "fig2_ablacion.png"
    plt.savefig(out, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"Guardado: {out}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera fig1 y fig2 desde metrics_runs.json")
    parser.add_argument("--work_dir", default=".",
                        help="Directorio raiz del proyecto (donde esta metrics_runs.json)")
    args = parser.parse_args()

    work_dir  = Path(args.work_dir)
    runs_path = work_dir / "metrics_runs.json"

    if not runs_path.exists():
        print(f"ERROR: {runs_path} no encontrado. Ejecuta primero src/main.py para cada config.")
        return

    with open(runs_path) as f:
        data = json.load(f)
    runs = data.get("runs", {})

    if not runs:
        print("metrics_runs.json no contiene runs.")
        return

    print(f"Runs disponibles: {list(runs.keys())}")
    out_dir = work_dir / "figures"
    out_dir.mkdir(exist_ok=True)

    _fig1_comparison(runs, out_dir)
    _fig2_ablation(runs, out_dir)
    print("Reporte completado.")


if __name__ == "__main__":
    main()
