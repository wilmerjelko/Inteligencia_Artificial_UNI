"""CNN de 4 bloques convolucionales entrenada desde cero para clasificacion binaria de llantas."""
import torch.nn as nn


class ConvBlock(nn.Module):
    """Bloque Conv->BN->ReLU->Conv->BN->ReLU->MaxPool."""

    def __init__(self, in_c: int, out_c: int):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_c, out_c, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_c),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_c, out_c, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_c),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )

    def forward(self, x):
        return self.block(x)


class TireCNN(nn.Module):
    """CNN entrenada desde cero: 4 ConvBlocks + GlobalAvgPool + cabeza FC binaria.

    Arquitectura: 3->32->64->128->256 canales, GAP, dropout=0.4,
    FC(256,128)->ReLU->FC(128,1).
    """

    def __init__(self, dropout: float = 0.4):
        super().__init__()
        self.b1 = ConvBlock(3, 32)
        self.b2 = ConvBlock(32, 64)
        self.b3 = ConvBlock(64, 128)
        self.b4 = ConvBlock(128, 256)
        self.gap = nn.AdaptiveAvgPool2d(1)
        self.head = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(dropout),
            nn.Linear(256, 128),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(128, 1),
        )

    def forward(self, x):
        x = self.b1(x); x = self.b2(x); x = self.b3(x); x = self.b4(x)
        return self.head(self.gap(x))

    def feature_map(self, x):
        """Devuelve el mapa de activacion tras el ultimo ConvBlock (para Grad-CAM)."""
        x = self.b1(x); x = self.b2(x); x = self.b3(x); x = self.b4(x)
        return x
