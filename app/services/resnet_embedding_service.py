"""Service for generating normalized image embeddings using ResNet50."""

from pathlib import Path
from typing import Any, ClassVar, Dict, Optional, Tuple, Union
import numpy as np
from PIL import Image
import torch
import torch.nn as nn
from torchvision.models import ResNet50_Weights, resnet50

MODEL_NAME = "resnet50"
EMBEDDING_DIMENSION = 2048


class ResNet50EmbeddingService:
    """Service for generating normalized 2048-dimensional image embeddings with ResNet50."""

    _model_cache: ClassVar[Dict[Tuple[str, torch.device], Tuple[nn.Module, Any]]] = {}

    def __init__(
        self,
        device: Optional[Union[str, torch.device]] = None,
    ) -> None:
        """Initialize the ResNet50EmbeddingService and load model into memory once.

        Args:
            device: Execution device ('cuda', 'cpu', or torch.device). Auto-selects CUDA if available.
        """
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device if isinstance(device, str) else device)

        self.model, self.preprocess = self._get_or_load_model(self.device)

    @classmethod
    def _get_or_load_model(
        cls, device: torch.device
    ) -> Tuple[nn.Module, Any]:
        """Load and cache the ResNet50 feature extractor without the final fc layer."""
        cache_key = (MODEL_NAME, device)
        if cache_key not in cls._model_cache:
            try:
                weights = ResNet50_Weights.DEFAULT
                full_model = resnet50(weights=weights)
                # Remove final fully connected classification layer
                feature_extractor = nn.Sequential(*list(full_model.children())[:-1])
                feature_extractor = feature_extractor.to(device)
                feature_extractor.eval()
                preprocess = weights.transforms()
                cls._model_cache[cache_key] = (feature_extractor, preprocess)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to load ResNet50 model ({MODEL_NAME}) on {device}: {e}"
                ) from e
        return cls._model_cache[cache_key]

    def generate_image_embedding(self, image_source: Union[str, Path, Image.Image]) -> np.ndarray:
        """Generate a normalized 2048-dimensional float32 embedding for an image.

        Args:
            image_source: Path to an image file (str or Path) or a PIL Image instance.

        Returns:
            np.ndarray: L2-normalized float32 array of shape (2048,).

        Raises:
            FileNotFoundError: If the provided file path does not exist.
            ValueError: If image loading fails or resulting embedding fails validation.
            RuntimeError: If model inference fails.
        """
        image = self._load_image(image_source)

        try:
            tensor = self.preprocess(image).unsqueeze(0).to(self.device)
        except Exception as e:
            raise ValueError(f"Failed to preprocess image: {e}") from e

        try:
            with torch.inference_mode():
                features = self.model(tensor)
                features = torch.flatten(features, 1)
                features = features / features.norm(p=2, dim=-1, keepdim=True)
                embedding = features.squeeze(0).cpu().numpy().astype(np.float32)
        except Exception as e:
            raise RuntimeError(f"Error executing ResNet50 model inference: {e}") from e

        self._validate_embedding(embedding)
        return embedding

    def _load_image(self, image_source: Union[str, Path, Image.Image]) -> Image.Image:
        """Load and convert input image path to RGB PIL Image format."""
        if isinstance(image_source, (str, Path)):
            path = Path(image_source)
            if not path.exists():
                raise FileNotFoundError(f"Image file does not exist: {path}")
            if not path.is_file():
                raise ValueError(f"Path is not a file: {path}")
            try:
                return Image.open(path).convert("RGB")
            except Exception as e:
                raise ValueError(f"Failed to open/read image file at {path}: {e}") from e
        elif isinstance(image_source, Image.Image):
            return image_source.convert("RGB")
        else:
            raise TypeError(
                f"Unsupported image source type: {type(image_source).__name__}. "
                "Expected str, pathlib.Path, or PIL.Image.Image."
            )

    def _validate_embedding(self, embedding: np.ndarray) -> None:
        """Validate embedding data type, shape (2048,), and finite values."""
        if embedding.dtype != np.float32:
            raise ValueError(f"Expected embedding dtype float32, got {embedding.dtype}")
        if embedding.shape != (EMBEDDING_DIMENSION,):
            raise ValueError(
                f"Expected embedding dimension ({EMBEDDING_DIMENSION},), got {embedding.shape}"
            )
        if not np.all(np.isfinite(embedding)):
            raise ValueError("Generated embedding contains non-finite values (NaN or Inf).")
