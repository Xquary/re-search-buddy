"""Persistent store of embeddings for files dropped into `input/raw/`."""

from .reader import read_text, SUPPORTED_EXTENSIONS
from .store import InputStore, ScanResult

__all__ = ["InputStore", "ScanResult", "read_text", "SUPPORTED_EXTENSIONS"]
