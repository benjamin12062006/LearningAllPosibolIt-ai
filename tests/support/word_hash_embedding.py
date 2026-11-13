"""Embedding de prueba: determinista, sin red y con significado mínimo.

Cada palabra suma 1 en una posición calculada con su hash; textos con palabras
en común quedan cerca. Basta para probar el índice sin llamar a Google, y cuenta
cuántos textos embebe para comprobar que lo que no cambió no se recalcula.
"""

import hashlib
import math
import re

from llama_index.core.base.embeddings.base import BaseEmbedding
from pydantic import PrivateAttr

WORD = re.compile(r"\w+")


class WordHashEmbedding(BaseEmbedding):
    dimensions: int = 64
    _embedded_texts: int = PrivateAttr(default=0)

    @property
    def embedded_texts(self) -> int:
        return self._embedded_texts

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for word in WORD.findall(text.lower()):
            digest = hashlib.sha256(word.encode()).digest()
            vector[int.from_bytes(digest[:4], "big") % self.dimensions] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def _get_text_embedding(self, text: str) -> list[float]:
        self._embedded_texts += 1
        return self._vector(text)

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._vector(query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._vector(query)
