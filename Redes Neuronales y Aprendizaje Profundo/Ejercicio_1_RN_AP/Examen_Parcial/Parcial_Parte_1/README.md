# Parte 1 — Clasificación de Llantas Dañadas (CNN + ResNet-50)

**Examen Parcial — Redes Neuronales y Aprendizaje Profundo**
Docente: Dr. Aldo Camargo Fernández Baca
Grupo 2:
- Anahys Montes Chapilliquen
- Christian Fabrizzio Vizcardo Estupiñán
- Cristhian Massa Medina
- Freddy Antonio Huali Veliz
- Wilmer Jelko Lazaro Guerra

## Resumen del entregable
Clasificación binaria de imágenes de textura de llantas (`normal` vs `cracked`) sobre el dataset público
[Tire Texture Image Recognition](https://www.kaggle.com/datasets/jehanbhathena/tire-texture-image-recognition)
(1028 imágenes, CC0). Se entrenan y comparan **dos arquitecturas CNN**:

1. `TireCNN` — CNN entrenada desde cero en PyTorch (sin pesos preentrenados).
2. `ResNet-50` con *fine-tuning* (backbone preentrenado en ImageNet).

Se realizan estudios de ablación (BCE vs. Focal Loss, con/sin aumento de datos),
análisis de desbalance, interpretabilidad con **Grad-CAM** y galería cualitativa de errores.

## Resultados principales (test, 325 imágenes)

| Modelo            | Umbral | F1    | AUC   | Precisión | Recall |
| ----------------- | ------ | ----- | ----- | --------- | ------ |
| TireCNN (1.2 M)   | 0.50   | 0.715 | 0.760 | 0.854     | 0.614  |
| TireCNN (1.2 M)   | 0.37   | 0.754 | 0.760 | 0.860     | 0.671  |
| ResNet-50 FT (22 M) | 0.50 | 0.825 | 0.960 | **0.993** | 0.705  |
| ResNet-50 FT (22 M) | 0.38 | **0.844** | **0.960** | **0.994** | 0.733 |

Ablación (test F1): BCE+aug = 0.827, Focal(γ=2)+aug = 0.830, BCE sin aug = 0.689,
BCE + pos_weight = 0.771. **El aumento de datos es el factor más rentable**
(−14 puntos F1 al removerlo); las técnicas de desbalance no aportan o incluso restan
por *covariate shift* leve entre train y test.

Métricas completas en `metrics.json` (entorno Kaggle Notebooks, GPU T4 x2,
PyTorch 2.10.0 + CUDA 12.8, `SEED = 42`).

## Cómo ejecutarlo

### Opción A — Notebook (modo interactivo, recomendado para revisión)

El notebook detecta automáticamente Kaggle / Colab / local.

**Kaggle Notebooks (ejecución de referencia):**
1. Crear un nuevo notebook e importar `notebook_tire_classification.ipynb`.
2. Panel derecho → **+ Add Input → Datasets** → `jehanbhathena/tire-texture-image-recognition`.
3. Settings → **Accelerator = GPU T4 x2**.
4. **Save Version → Save & Run All (Commit)** — ~30 min.
5. Descargar `metrics.json` y `checkpoints/*.pt` desde **Output**.

**Google Colab:**
1. Abrir el notebook → `Runtime → Change runtime type → GPU`.
2. Subir `kaggle.json` cuando la celda lo pida.
3. `Runtime → Run all`.

**Local:**
```bash
pip install -r requirements.txt
# Tener ~/.kaggle/kaggle.json configurado
jupyter notebook notebook_tire_classification.ipynb
```

### Opción B — Línea de comandos (modo modular, un solo comando)

```bash
pip install -r requirements.txt

# Baseline (ResNet-50 completo con error analysis)
python src/main.py --config configs/config_baseline.yaml \
                   --data_dir "tire_data/Tire Textures"

# Ablaciones (ResNet-50 con distintas funciones de perdida / augmentation)
python src/main.py --config configs/config_ablation_focal.yaml    --data_dir "tire_data/Tire Textures"
python src/main.py --config configs/config_ablation_noaug.yaml    --data_dir "tire_data/Tire Textures"
python src/main.py --config configs/config_ablation_posweight.yaml --data_dir "tire_data/Tire Textures"
```

En Kaggle/Colab sustituir `tire_data/Tire Textures` por la ruta montada correspondiente.

## Estructura
```
Parte_1/
├── notebook_tire_classification.ipynb  # Pipeline completo (30 celdas)
├── src/
│   ├── main.py                         # Punto de entrada CLI
│   ├── train.py                        # Bucle entrenamiento + early stopping
│   ├── evaluate.py                     # Evaluacion sobre DataLoader
│   ├── losses.py                       # FocalLoss + compute_metrics
│   ├── interpretability.py             # Grad-CAM (implementacion propia)
│   ├── error_analysis.py               # Analisis FP/FN + fig7 + CSV
│   ├── data/
│   │   ├── dataset.py                  # TireDataset + build_loaders
│   │   └── transforms.py              # get_train_transforms / get_eval_transforms
│   └── models/
        ├── tirecnn.py                  # CNN entrenada desde cero (4 ConvBlocks)
│       └── transfer.py                # build_resnet50 + build_efficientnet_b0
├── configs/
│   ├── config_baseline.yaml
│   ├── config_ablation_bce_aug.yaml
│   ├── config_ablation_focal.yaml
│   ├── config_ablation_noaug.yaml
│   └── config_ablation_posweight.yaml
├── metrics.json                        # Resultados de la corrida en Kaggle
├── requirements.txt                    # Dependencias (PyYAML incluido)
└── README.md                           # Este archivo
```

## Reproducibilidad
- Semilla global fijada en `SEED = 42` (numpy, torch, random).
- División train/val/test estratificada (`training_data/` se re-divide en
  85 / 15 % para obtener un *validation set*; `testing_data/` queda intacto).
- Splits con `SEED = 42`: train = 597, val = 106, test = 325.
- Presupuesto de épocas en GPU: TireCNN = 50, ResNet head = 10, ResNet FT = 50,
  ablación = 15 por variante (early stopping con paciencia 10 sobre F1 val).
- Tiempo de referencia en Kaggle T4 x2: ~30 min para todo el pipeline.
