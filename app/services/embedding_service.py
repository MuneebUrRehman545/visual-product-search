"""Service for generating normalized image embeddings using OpenCLIP."""

from pathlib import Path
from typing import Any, ClassVar, Dict, Optional, Tuple, Union
import numpy as np
import open_clip
from PIL import Image
import torch

MODEL_NAME = "ViT-B-32"
PRETRAINED_WEIGHTS = "laion2b_s34b_b79k"
EMBEDDING_DIMENSION = 512


class EmbeddingService:
    """Service for generating normalized image embeddings with OpenCLIP."""

    _model_cache: ClassVar[Dict[Tuple[str, str, torch.device], Tuple[torch.nn.Module, Any]]] = {}

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        pretrained: str = PRETRAINED_WEIGHTS,
        device: Optional[Union[str, torch.device]] = None,
    ) -> None:
        """Initialize the EmbeddingService and load model into memory once.

        Args:
            model_name: OpenCLIP model architecture name.
            pretrained: Pretrained dataset weights identifier.
            device: Execution device ('cuda', 'cpu', or torch.device). Auto-selects CUDA if available.
        """
        self.model_name = model_name
        self.pretrained = pretrained

        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device if isinstance(device, str) else device)

        self.model, self.preprocess = self._get_or_load_model(
            self.model_name, self.pretrained, self.device
        )

    @classmethod
    def _get_or_load_model(
        cls, model_name: str, pretrained: str, device: torch.device
    ) -> Tuple[torch.nn.Module, Any]:
        """Load and cache the OpenCLIP model and preprocessing transform."""
        cache_key = (model_name, pretrained, device)
        if cache_key not in cls._model_cache:
            try:
                model, _, preprocess = open_clip.create_model_and_transforms(
                    model_name, pretrained=pretrained
                )
                model = model.to(device)
                model.eval()
                cls._model_cache[cache_key] = (model, preprocess)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to load OpenCLIP model '{model_name}' ({pretrained}) on {device}: {e}"
                ) from e
        return cls._model_cache[cache_key]

    def generate_image_embedding(self, image_source: Union[str, Path, Image.Image]) -> np.ndarray:
        """Generate a normalized 512-dimensional float32 embedding for an image.

        Args:
            image_source: Path to an image file (str or Path) or a PIL Image instance.

        Returns:
            np.ndarray: L2-normalized float32 array of shape (512,).

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
            with torch.no_grad():
                features = self.model.encode_image(tensor)
                features = features / features.norm(dim=-1, keepdim=True)
                embedding = features.squeeze(0).cpu().numpy().astype(np.float32)
        except Exception as e:
            raise RuntimeError(f"Error executing OpenCLIP model inference: {e}") from e

        self._validate_embedding(embedding)
        return embedding

    def _load_image(self, image_source: Union[str, Path, Image.Image]) -> Image.Image:
        """Load and convert input image to RGB PIL Image format."""
        if isinstance(image_source, (str, Path)):
            path = Path(image_source)
            if not path.exists():
                raise FileNotFoundError(f"Image file does not exist: {path}")
            if not path.is_file():
                raise ValueError(f"Path is not a file: {path}")
            try:
                return Image.open(path).convert("RGB")
            except Exception as e:
                raise ValueError(f"Failed to open image file at {path}: {e}") from e
        elif isinstance(image_source, Image.Image):
            return image_source.convert("RGB")
        else:
            raise TypeError(
                f"Unsupported image source type: {type(image_source).__name__}. "
                "Expected str, pathlib.Path, or PIL.Image.Image."
            )

    def _validate_embedding(self, embedding: np.ndarray) -> None:
        """Validate embedding data type, shape, and value sanity."""
        if embedding.dtype != np.float32:
            raise ValueError(f"Expected embedding dtype float32, got {embedding.dtype}")
        if embedding.shape != (EMBEDDING_DIMENSION,):
            raise ValueError(
                f"Expected embedding dimension ({EMBEDDING_DIMENSION},), got {embedding.shape}"
            )
        if not np.all(np.isfinite(embedding)):
            raise ValueError("Generated embedding contains non-finite values (NaN or Inf).")
