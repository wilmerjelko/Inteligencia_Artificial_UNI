#!/usr/bin/env python3
"""report_tables.py -- Genera las tablas Markdown del informe desde metrics_runs.json.

Uso:
    python src/report_tables.py --work_dir .

Imprime por stdout las tablas listas para pegar en informe_pregunta_1.md.
"""
import argparse
import json
from pathlib import Path


def _fmt(v, decimals=3):
    if v is None:
        return "N/A"
    try:
        return f"{float(v):.{decimals}f}"
    except (TypeError, ValueError):
        return str(v)


def tabla_41(runs: dict) -> str:
    """Tabla 4.1 — Resultados generales en test (TireCNN + baseline)."""
    lines = [
        "### Tabla 4.1 — Resultados en test\n",
        "| Modelo | Umbral | Accuracy | Precisión | Recall | F1 | AUC-ROC |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    order = ["ablation_scratch", "baseline"]   # TireCNN, ResNet-50
    for key in order:
        if key not in runs:
            continue
        r = runs[key]
        model_label = {
            "ablation_scratch": "TireCNN (1.2 M params)",
            "baseline":         "ResNet-50 FT (22 M entren.)",
        }.get(key, key)
        n_params = {"ablation_scratch": "1.2 M", "baseline": "22 M"}.get(key, "?")
        # thr 0.50
        m05 = r.get("test_thr05", {})
        lines.append(
            f"| {model_label} | 0.50 | {_fmt(m05.get('accuracy'))} | "
            f"{_fmt(m05.get('precision'))} | {_fmt(m05.get('recall'))} | "
            f"{_fmt(m05.get('f1'))} | {_fmt(m05.get('auc'))} |"
        )
        # thr optimo
        mopt = r.get("test_thr_opt", {})
        thr  = _fmt(mopt.get("threshold", 0.5), decimals=2)
        lines.append(
            f"| {model_label} | {thr} | {_fmt(mopt.get('accuracy'))} | "
            f"{_fmt(mopt.get('precision'))} | {_fmt(mopt.get('recall'))} | "
            f"{_fmt(mopt.get('f1'))} | {_fmt(mopt.get('auc'))} |"
        )
    return "\n".join(lines)


def tabla_cm(runs: dict) -> str:
    """Tabla 4.2 — Matriz de confusión del baseline (ResNet-50)."""
    if "baseline" not in runs:
        return "*(baseline no encontrado en metrics_runs.json)*"
    cm = runs["baseline"].get("cm_opt", {})
    tn, fp = cm.get("tn", "?"), cm.get("fp", "?")
    fn, tp = cm.get("fn", "?"), cm.get("tp", "?")
    thr = _fmt(runs["baseline"].get("test_thr_opt", {}).get("threshold", 0.5), decimals=2)
    lines = [
        f"### Tabla 4.2 — Matriz de confusión ResNet-50 (umbral óptimo = {thr})\n",
        "| | Pred = normal | Pred = cracked |",
        "| --- | --- | --- |",
        f"| **Real = normal** | TN = {tn} | FP = {fp} |",
        f"| **Real = cracked** | FN = {fn} | TP = {tp} |",
    ]
    return "\n".join(lines)


def tabla_43(runs: dict) -> str:
    """Tabla 4.3 — Ablaciones."""
    abl_map = {
        "ablation_bce_aug":    "ResNet-50 + BCE + aug. (línea base)",
        "ablation_focal":      "ResNet-50 + Focal (γ=2) + aug.",
        "ablation_noaug":      "ResNet-50 + BCE sin aug.",
        "ablation_posweight":  "ResNet-50 + BCE + pos_weight",
        "baseline":            "ResNet-50 baseline (50 épocas)",
    }
    keys = [k for k in abl_map if k in runs]
    if len(keys) < 2:
        return "*(se necesitan al menos 2 variantes de ablación en metrics_runs.json)*"

    lines = [
        "### Tabla 4.3 — Ablaciones\n",
        "| Variante | F1 test (opt) | AUC test | Δ F1 vs línea base |",
        "| --- | --- | --- | --- |",
    ]
    # referencia = ablation_bce_aug o baseline
    ref_key  = "ablation_bce_aug" if "ablation_bce_aug" in runs else "baseline"
    ref_f1   = runs[ref_key].get("test_thr_opt", {}).get("f1", None)

    for k in keys:
        label = abl_map.get(k, k)
        f1    = runs[k].get("test_thr_opt", {}).get("f1", None)
        auc   = runs[k].get("test_thr_opt", {}).get("auc", None)
        delta = ""
        if ref_f1 is not None and f1 is not None and k != ref_key:
            d = float(f1) - float(ref_f1)
            delta = f"{d:+.3f}"
        elif k == ref_key:
            delta = "—"
        lines.append(f"| {label} | {_fmt(f1)} | {_fmt(auc)} | {delta} |")
    return "\n".join(lines)


def resumen_metricas(runs: dict) -> str:
    """Bloque de texto con los valores clave para actualizar la discusión."""
    lines = ["### Valores clave para la discusión del informe\n"]
    for key, label in [("ablation_scratch", "TireCNN"), ("baseline", "ResNet-50")]:
        if key not in runs:
            continue
        mopt = runs[key].get("test_thr_opt", {})
        m05  = runs[key].get("test_thr05", {})
        thr  = _fmt(mopt.get("threshold", 0.5), decimals=2)
        lines.append(f"**{label}**")
        lines.append(f"  - F1 (thr=0.50) = {_fmt(m05.get('f1'))} | AUC = {_fmt(m05.get('auc'))}")
        lines.append(f"  - F1 (thr={thr}) = {_fmt(mopt.get('f1'))} | AUC = {_fmt(mopt.get('auc'))}")
        lines.append(f"  - Accuracy={_fmt(mopt.get('accuracy'))} | Precision={_fmt(mopt.get('precision'))} | Recall={_fmt(mopt.get('recall'))}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Genera tablas Markdown del informe desde metrics_runs.json")
    parser.add_argument("--work_dir", default=".",
                        help="Directorio raiz del proyecto (donde esta metrics_runs.json)")
    args = parser.parse_args()

    runs_path = Path(args.work_dir) / "metrics_runs.json"
    if not runs_path.exists():
        print(f"ERROR: {runs_path} no encontrado.")
        return

    with open(runs_path) as f:
        runs = json.load(f).get("runs", {})

    sep = "\n" + "─" * 70 + "\n"
    print(sep)
    print(resumen_metricas(runs))
    print(sep)
    print(tabla_41(runs))
    print(sep)
    print(tabla_cm(runs))
    print(sep)
    print(tabla_43(runs))
    print(sep)
    print("✓ Copia las tablas anteriores al informe_pregunta_1.md")


if __name__ == "__main__":
    main()
