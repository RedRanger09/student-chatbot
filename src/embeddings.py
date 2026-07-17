"""
Embedding utilities backed by Sentence Transformers.

Uses a process-wide singleton with lazy model loading so the model
is downloaded / initialized only once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from src.utils.logger import get_logger

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = get_logger(__name__)


class EmbeddingService:
    """
    Singleton embedding service.

    The SentenceTransformer model is loaded on first use (lazy), then
    reused for all subsequent document and query embeddings.
    """

    _instance: EmbeddingService | None = None
    _model: SentenceTransformer | None = None

    def __new__(cls, model_name: str = "all-MiniLM-L6-v2") -> EmbeddingService:
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._model_name = model_name
            instance._dimension: int | None = None
            cls._instance = instance
            logger.debug("EmbeddingService singleton created (model=%s)", model_name)
        return cls._instance

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        # ``__init__`` may run on every call; keep model_name aligned if
        # the singleton already exists with a different requested name.
        if not hasattr(self, "_model_name"):
            self._model_name = model_name
        elif model_name != self._model_name and type(self)._model is None:
            self._model_name = model_name

    @classmethod
    def get_instance(cls, model_name: str = "all-MiniLM-L6-v2") -> EmbeddingService:
        """Return the shared ``EmbeddingService`` instance."""
        return cls(model_name=model_name)

    @classmethod
    def reset_instance(cls) -> None:
        """
        Clear the singleton (primarily for tests).

        Unloads the in-memory model reference; does not delete cached files.
        """
        cls._instance = None
        cls._model = None

    @property
    def model_name(self) -> str:
        """Configured Sentence Transformers model identifier."""
        return self._model_name

    @property
    def dimension(self) -> int:
        """Embedding dimensionality (loads the model if needed)."""
        self._ensure_model_loaded()
        assert self._dimension is not None
        return self._dimension

    def embed_documents(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        """
        Embed document chunks.

        Args:
            texts: Chunk texts to embed.
            batch_size: Encode batch size.

        Returns:
            Float32 array of shape ``(n, dim)``, L2-normalized for cosine search.
        """
        return self._encode(texts, batch_size=batch_size, is_query=False)

    def embed_query(self, query: str) -> np.ndarray:
        """
        Embed a single search query.

        Returns:
            Float32 vector of shape ``(dim,)``, L2-normalized.
        """
        vectors = self._encode([query], batch_size=1, is_query=True)
        return vectors[0]

    def embed(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        """Batch-embed texts (alias for document embedding)."""
        return self.embed_documents(texts, batch_size=batch_size)

    def _ensure_model_loaded(self) -> None:
        """Load the SentenceTransformer model once (lazy)."""
        if type(self)._model is not None:
            if self._dimension is None:
                probe = type(self)._model.encode(["dimension_probe"], convert_to_numpy=True)  # type: ignore[union-attr]
                self._dimension = int(probe.shape[1])
            return

        logger.info("Loading embedding model: %s", self._model_name)
        from sentence_transformers import SentenceTransformer

        model: SentenceTransformer | None = None
        try:
            model = SentenceTransformer(self._model_name, local_files_only=True)
            logger.info("Loaded embedding model from local cache")
        except Exception:  # noqa: BLE001 — fall through to hub download
            model = None

        if model is None:
            try:
                model = SentenceTransformer(self._model_name)
            except Exception as exc:  # noqa: BLE001
                if not _looks_like_ssl_error(exc):
                    raise
                logger.warning(
                    "SSL verification failed while downloading/loading '%s'. "
                    "Retrying with a relaxed SSL context (common on Windows / "
                    "corporate proxies). Prefer fixing system certificates for production.",
                    self._model_name,
                )
                _enable_relaxed_ssl()
                model = SentenceTransformer(self._model_name)

        type(self)._model = model
        probe = model.encode(["dimension_probe"], convert_to_numpy=True)
        self._dimension = int(probe.shape[1])
        logger.info(
            "Embedding model ready: %s (dimension=%s)",
            self._model_name,
            self._dimension,
        )

    def _encode(
        self,
        texts: list[str],
        batch_size: int,
        is_query: bool,
    ) -> np.ndarray:
        if not texts:
            self._ensure_model_loaded()
            assert self._dimension is not None
            return np.zeros((0, self._dimension), dtype=np.float32)

        self._ensure_model_loaded()
        model = type(self)._model
        assert model is not None

        label = "query" if is_query else "documents"
        logger.info("Embedding %s %s (batch_size=%s)", len(texts), label, batch_size)

        vectors = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=len(texts) > 16,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        array = np.asarray(vectors, dtype=np.float32)
        logger.info("Embedding complete: shape=%s", array.shape)
        return array


def _looks_like_ssl_error(exc: BaseException) -> bool:
    """Return True if the exception chain suggests an SSL/TLS failure."""
    messages: list[str] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        messages.append(str(current).lower())
        messages.append(type(current).__name__.lower())
        current = current.__cause__ or current.__context__
    blob = " | ".join(messages)
    needles = (
        "ssl",
        "certificate",
        "certifi",
        "certificate_verify_failed",
        "client has been closed",
    )
    return any(n in blob for n in needles)


def _enable_relaxed_ssl() -> None:
    """
    Temporarily relax SSL verification for Hugging Face model downloads.

    Intended as a last-resort workaround when the host OS cannot validate
    Hugging Face certificates (e.g. intercepting antivirus / missing CA).
    """
    import ssl

    import httpx

    ssl._create_default_https_context = ssl._create_unverified_context  # noqa: SLF001

    original_init = httpx.Client.__init__

    def _init_with_verify_false(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.setdefault("verify", False)
        return original_init(self, *args, **kwargs)

    httpx.Client.__init__ = _init_with_verify_false  # type: ignore[method-assign]
