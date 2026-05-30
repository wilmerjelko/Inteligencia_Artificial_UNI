"""Analisis cualitativo de fallos: guarda FP/FN en disco y genera fig7."""
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image

from .data.transforms import get_eval_transforms
from .interpretability import GradCAM, denorm, overlay


def run_error_analysis(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    paths: list,
    cam_engine: GradCAM,
    output_dir: str = "outputs/errors",
    figures_dir: str = "figures",
    n_save: int = 5,
    threshold: float = 0.5,
) -> pd.DataFrame:
    """Clasifica los errores del modelo en FP y FN, los persiste y genera figura.

    Para cada tipo de error (FP y FN), guarda las top-n_save imagenes con mayor
    confianza incorrecta en subdirectorios, con la probabilidad en el nombre de
    archivo. Genera tambien error_log.csv y figures/fig7_error_analysis.png.

    Args:
        y_true: Etiquetas reales (0=normal, 1=cracked).
        y_prob: Probabilidades predichas por el modelo.
        paths: Lista de rutas de imagen correspondientes a y_true/y_prob.
        cam_engine: Instancia de GradCAM para visualizar los errores.
        output_dir: Directorio raiz para FP/FN y CSV.
        figures_dir: Directorio donde guardar fig7.
        n_save: Numero de imagenes a guardar por tipo de error.
        threshold: Umbral de decision binaria.

    Returns:
        DataFrame con todos los errores (ruta_imagen, etiqueta_real,
        etiqueta_predicha, probabilidad_predicha, tipo_error).
    """
    eval_tf = get_eval_transforms()
    errors_dir = Path(output_dir)
    fp_dir = errors_dir / "false_positives"
    fn_dir = errors_dir / "false_negatives"
    for d in [fp_dir, fn_dir]:
        d.mkdir(parents=True, exist_ok=True)

    y_pred = (y_prob >= threshold).astype(int)
    df = pd.DataFrame({
        "path": paths,
        "true": y_true.astype(int),
        "pred": y_pred,
        "prob": y_prob,
    })
    df = df[df["true"] != df["pred"]].copy()
    df["tipo_error"] = np.where(df["pred"] == 1, "FP", "FN")
    df["confidence_error"] = np.where(
        df["pred"] == 1, df["prob"], 1 - df["prob"]
    )
    df = df.sort_values("confidence_error", ascending=False)

    # Guardar error_log.csv
    log_path = errors_dir / "error_log.csv"
    df[["path", "true", "pred", "prob", "tipo_error"]].rename(columns={
        "path": "ruta_imagen",
        "true": "etiqueta_real",
        "pred": "etiqueta_predicha",
        "prob": "probabilidad_predicha",
    }).to_csv(log_path, index=False)

    fp_count = (df["tipo_error"] == "FP").sum()
    fn_count = (df["tipo_error"] == "FN").sum()
    print(f"error_log.csv -> {log_path}  ({len(df)} errores: FP={fp_count}, FN={fn_count})")

    # Guardar top-N FP y FN en disco con probabilidad en el nombre
    for tipo, save_dir in [("FP", fp_dir), ("FN", fn_dir)]:
        subset = df[df["tipo_error"] == tipo].head(n_save)
        for _, row in subset.iterrows():
            src = Path(row["path"])
            fname = f"{tipo.lower()}_prob{row['prob']:.3f}_{src.stem}{src.suffix}"
            shutil.copy(src, save_dir / fname)
        print(f"  {tipo}: {len(subset)} imagen(es) guardada(s) en {save_dir}")

    # Figura top-5 con Grad-CAM
    top5 = df.head(5)
    fig, axes = plt.subplots(1, len(top5), figsize=(18, 4))
    for ax, (_, row) in zip(axes, top5.iterrows()):
        img = Image.open(row["path"]).convert("RGB")
        x = eval_tf(img).unsqueeze(0)
        cam, prob = cam_engine(x)
        ax.imshow(overlay(denorm(x[0]), cam))
        tag_true = "cracked" if row["true"] == 1 else "normal"
        tag_pred = "cracked" if row["pred"] == 1 else "normal"
        ax.set_title(
            f"real={tag_true}\npred={tag_pred} ({prob:.2f})\n[{row['tipo_error']}]"
        )
        ax.axis("off")
    plt.suptitle("Top 5 errores con mayor confianza -- ResNet-50", fontsize=14)
    plt.tight_layout()
    fig7_path = Path(figures_dir) / "fig7_error_analysis.png"
    plt.savefig(fig7_path, dpi=150, bbox_inches="tight")
    plt.show()
    print(f"fig7 guardado -> {fig7_path}")

    return df
