"""Modelos de Transfer Learning: ResNet-50 y EfficientNet-B0 con cabeza binaria."""
import torch.nn as nn
from torchvision import models


def build_resnet50(freeze_backbone: bool = True) -> nn.Module:
    """ResNet-50 preentrenado en ImageNet con cabeza lineal binaria.

    Estrategia de fine-tuning aplicada:
      Fase 1: freeze_backbone=True, entrenar solo fc (lr=1e-3, 10 ep)
      Fase 2: descongelar layer3, layer4, fc (lr=1e-4, 50 ep)
    """
    net = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V2)
    if freeze_backbone:
        for p in net.parameters():
            p.requires_grad = False
    net.fc = nn.Linear(net.fc.in_features, 1)
    return net


def build_efficientnet_b0(freeze_backbone: bool = True) -> nn.Module:
    """EfficientNet-B0 preentrenado en ImageNet con cabeza binaria adaptada.

    Reemplaza el clasificador original (1280->1000) por:
      Dropout(0.3) -> Linear(1280,512) -> ReLU -> Dropout(0.3) -> Linear(512,1)

    Estrategia de fine-tuning aplicada:
      Fase 1: freeze_backbone=True, entrenar solo classifier (lr=1e-3, 10 ep)
      Fase 2: descongelar features.7, features.8, classifier (lr=5e-5, 50 ep)
    """
    net = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.IMAGENET1K_V1)
    if freeze_backbone:
        for p in net.parameters():
            p.requires_grad = False
    in_features = net.classifier[1].in_features  # 1280
    net.classifier = nn.Sequential(
        nn.Dropout(p=0.3, inplace=True),
        nn.Linear(in_features, 512),
        nn.ReLU(inplace=True),
        nn.Dropout(p=0.3),
        nn.Linear(512, 1),
    )
    return net
