"""Text embedders for the GORGONA AI learning plane.

Default is the GORGONA-owned deterministic HashingEmbedder (zero third-party weights).
When Cloudflare Workers AI credentials are configured (`GAI_CF_ACCOUNT_ID` and
`GAI_CF_API_TOKEN`), `CloudflareEmbedder` computes cross-lingual Matryoshka (MRL) 256-dim
embeddings via stdlib HTTPS so EN/RU/ES retrieval works across all 39 industries without
changing the `vector(256)` schema.
"""

import hashlib
import http.client
import json
import math
import os
import re
import unicodedata
from typing import Protocol

DIMENSIONS = 256
_DEFAULT_CF_EMBED_MODEL = "@cf/qwen/qwen3-embedding-0.6b"
_WORD = re.compile(r"\w+", re.UNICODE)


class Embedder(Protocol):
    version: str
    dimensions: int

    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    version = f"gorgona-hash-{DIMENSIONS}-v1"
    dimensions = DIMENSIONS

    def embed(self, text: str) -> list[float]:
        counts: dict[int, float] = {}
        for feature in _features(text):
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            index = value % DIMENSIONS
            sign = 1.0 if (value >> 63) & 1 else -1.0
            counts[index] = counts.get(index, 0.0) + sign
        vector = [0.0] * DIMENSIONS
        for index, raw in counts.items():
            vector[index] = math.copysign(math.log1p(abs(raw)), raw)
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector] if norm > 0 else vector


class CloudflareEmbedder:
    """Cross-lingual semantic embedder via Cloudflare Workers AI (Matryoshka 256d L2)."""

    dimensions = DIMENSIONS

    def __init__(
        self,
        account_id: str,
        api_token: str,
        model: str = _DEFAULT_CF_EMBED_MODEL,
        timeout: float = 20.0,
    ) -> None:
        self._account_id = account_id.strip()
        self._api_token = api_token.strip()
        self._model = model.strip() or _DEFAULT_CF_EMBED_MODEL
        self._timeout = timeout
        slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", self._model).strip("_")
        self.version = f"cf-{slug}-d{DIMENSIONS}-v1"

    def embed(self, text: str) -> list[float]:
        clean = text.strip()
        if not clean:
            return [0.0] * DIMENSIONS
        body = json.dumps({"model": self._model, "input": [clean[:4000]]}).encode("utf-8")
        conn = http.client.HTTPSConnection("api.cloudflare.com", 443, timeout=self._timeout)
        try:
            conn.request(
                "POST",
                f"/client/v4/accounts/{self._account_id}/ai/v1/embeddings",
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_token}",
                },
            )
            resp = conn.getresponse()
            raw = resp.read()
        finally:
            conn.close()
        if resp.status != 200:
            raise RuntimeError(f"Cloudflare embeddings HTTP {resp.status}")
        parsed = json.loads(raw.decode("utf-8"))
        data = parsed.get("data") or []
        if not data or not isinstance(data[0], dict):
            raise RuntimeError("Cloudflare embeddings returned empty data")
        full_vec = data[0].get("embedding") or []
        if len(full_vec) < DIMENSIONS:
            raise RuntimeError(f"Cloudflare embedding shorter than {DIMENSIONS} dims")
        prefix = [float(x) for x in full_vec[:DIMENSIONS]]
        norm = math.sqrt(sum(v * v for v in prefix))
        return [v / norm for v in prefix] if norm > 0 else prefix


def default_embedder() -> Embedder:
    """Resolve the active embedder from environment (defaults to deterministic HashingEmbedder)."""
    mode = os.environ.get("GAI_EMBEDDER", "auto").strip().lower() or "auto"
    account_id = os.environ.get("GAI_CF_ACCOUNT_ID", "").strip()
    api_token = os.environ.get("GAI_CF_API_TOKEN", "").strip()
    if mode != "hash" and account_id and api_token:
        model = os.environ.get("GAI_CF_EMBED_MODEL", _DEFAULT_CF_EMBED_MODEL)
        return CloudflareEmbedder(account_id=account_id, api_token=api_token, model=model)
    return HashingEmbedder()


def _features(text: str) -> list[str]:
    words = _WORD.findall(unicodedata.normalize("NFKC", text).casefold())
    features = [f"w:{w}" for w in words]
    for word in words:
        padded = f"<{word}>"
        features.extend(f"c:{padded[i : i + 3]}" for i in range(len(padded) - 2))
    return features


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))
