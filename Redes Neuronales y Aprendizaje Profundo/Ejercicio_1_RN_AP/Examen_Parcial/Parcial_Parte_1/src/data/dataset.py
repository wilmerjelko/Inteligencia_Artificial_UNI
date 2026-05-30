"""Dataset de texturas de llantas y factory de DataLoaders."""
from pathlib import Path

import pandas as pd
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset


class TireDataset(Dataset):
    """Dataset PyTorch para imagenes de llantas (normal / cracked).

    Args:
        df: DataFrame con columnas 'path' (str) y 'label' (int 0/1).
        transform: Transformacion torchvision a aplicar a cada imagen.
    """

    def __init__(self, df: pd.DataFrame, transform):
        self.df = df.reset_index(drop=True)
        self.transform = transform

    def __len__(self) -> int:
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        img = Image.open(row["path"]).convert("RGB")
        return (
            self.transform(img),
            torch.tensor(row["label"], dtype=torch.float32),
            row["path"],
        )


def build_loaders(
    df_tr: pd.DataFrame,
    df_val: pd.DataFrame,
    df_test: pd.DataFrame,
    train_tf,
    eval_tf,
    batch_size: int = 32,
    num_workers: int = 0,
) -> dict:
    """Construye los DataLoaders de train / val / test."""
    return {
        "train": DataLoader(
            TireDataset(df_tr, train_tf),
            batch_size=batch_size, shuffle=True, num_workers=num_workers,
        ),
        "val": DataLoader(
            TireDataset(df_val, eval_tf),
            batch_size=batch_size, shuffle=False, num_workers=num_workers,
        ),
        "test": DataLoader(
            TireDataset(df_test, eval_tf),
            batch_size=batch_size, shuffle=False, num_workers=num_workers,
        ),
    }
