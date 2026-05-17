from __future__ import annotations

from typing import Any

from .base import BaseEmbedder


def get_embedder(config: dict[str, Any]) -> BaseEmbedder:
    """Return the configured embedder instance."""
    emb_cfg = config.get("embedding", {})
    provider = emb_cfg.get("provider", "local")
    batch_size = emb_cfg.get("batch_size", 32)

    if provider == "api":
        from .api_embedder import ApiEmbedder

        api_cfg = emb_cfg.get("api", {})
        model = api_cfg.get("model", "text-embedding-3-small")
        dimensions = api_cfg.get("dimensions")  # None = model default
        return ApiEmbedder(model=model, dimensions=dimensions, batch_size=batch_size)
    else:
        from .local_embedder import LocalEmbedder

        model_name = emb_cfg.get("local", {}).get("model_name", "all-MiniLM-L6-v2")
        return LocalEmbedder(model_name=model_name, batch_size=batch_size)
