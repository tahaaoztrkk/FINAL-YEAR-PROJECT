"""Genişletme sağlayıcıları.

Ağır bağımlılıkları olan sağlayıcılar burada içe aktarılmaz; ``build_provider``
onları ihtiyaç anında yükler.
"""

from .mock import MockProvider
from .ngram import NGramProvider

__all__ = ["MockProvider", "NGramProvider"]
