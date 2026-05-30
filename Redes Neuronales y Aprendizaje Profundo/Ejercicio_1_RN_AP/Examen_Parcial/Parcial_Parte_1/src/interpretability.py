"""Grad-CAM y funciones de visualizacion (implementacion propia, sin libreria externa)."""
import cv2
import numpy as np
import torch
import torch.nn.functional as F

IMG_SIZE = 224
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD  = [0.229, 0.224, 0.225]


class GradCAM:
    """Grad-CAM minimalista (Selvaraju et al., 2017) para CNN con salida escalar.

    Registra activaciones y gradientes de la capa objetivo mediante hooks.
    Genera un mapa de calor normalizado del mismo tamano que la imagen de entrada.

    Args:
        model: Modelo PyTorch con salida escalar (logit).
        target_layer: Capa cuya activacion se usa para el mapa de calor.
    """

    def __init__(self, model: torch.nn.Module, target_layer: torch.nn.Module):
        self.model = model.eval()
        self.activations = None
        self.gradients = None
        target_layer.register_forward_hook(self._save_act)
        target_layer.register_full_backward_hook(self._save_grad)

    def _save_act(self, mod, inp, out):
        self.activations = out.detach()

    def _save_grad(self, mod, gin, gout):
        self.gradients = gout[0].detach()

    def __call__(self, x: torch.Tensor) -> tuple:
        """Computa el mapa Grad-CAM para la imagen x.

        Args:
            x: Tensor de forma (1, 3, H, W) normalizado con IMAGENET stats.

        Returns:
            (cam, prob) donde cam es ndarray (H, W) en [0,1] y prob es float.
        """
        device = next(self.model.parameters()).device
        x = x.to(device)
        self.model.zero_grad()
        logit = self.model(x).squeeze()
        logit.backward(retain_graph=True)
        weights = self.gradients.mean(dim=(2, 3), keepdim=True)
        cam = F.relu((weights * self.activations).sum(dim=1, keepdim=True))
        cam = F.interpolate(cam, size=(IMG_SIZE, IMG_SIZE), mode="bilinear", align_corners=False)
        cam = cam[0, 0].cpu().numpy()
        cam = (cam - cam.min()) / (cam.max() - cam.min() + 1e-8)
        return cam, torch.sigmoid(logit).item()


def denorm(img_tensor: torch.Tensor) -> np.ndarray:
    """Desnormaliza un tensor ImageNet y devuelve ndarray (H, W, 3) en [0,1]."""
    mean = np.array(IMAGENET_MEAN).reshape(3, 1, 1)
    std  = np.array(IMAGENET_STD).reshape(3, 1, 1)
    return np.clip(img_tensor.cpu().numpy() * std + mean, 0, 1).transpose(1, 2, 0)


def overlay(img_rgb: np.ndarray, cam: np.ndarray, alpha: float = 0.45) -> np.ndarray:
    """Superpone el mapa de calor JET sobre la imagen RGB.

    Args:
        img_rgb: ndarray (H, W, 3) en [0,1].
        cam: ndarray (H, W) en [0,1].
        alpha: Peso del heatmap (0=solo imagen, 1=solo heatmap).

    Returns:
        ndarray (H, W, 3) en [0,1].
    """
    heat = cv2.applyColorMap(np.uint8(255 * cam), cv2.COLORMAP_JET)[:, :, ::-1] / 255.0
    return np.clip(alpha * heat + (1 - alpha) * img_rgb, 0, 1)
