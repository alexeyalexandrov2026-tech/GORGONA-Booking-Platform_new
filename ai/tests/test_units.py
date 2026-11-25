"""Pure logic: embedder and evidence validation rules (no database)."""

from uuid import uuid4

import pytest

from gorgona_ai.embedder import (
    DIMENSIONS,
    CloudflareEmbedder,
    HashingEmbedder,
    cosine,
    default_embedder,
)
from gorgona_ai.evidence import EvidenceRejectedError, normalise, parse
from tests.conftest import envelope


def test_embedder_is_deterministic_normalised_and_semantic_by_overlap() -> None:
    e = HashingEmbedder()
    a, b = e.embed("gel manicure please"), e.embed("gel manicure please")
    assert a == b
    assert len(a) == DIMENSIONS
    assert abs(cosine(a, a) - 1.0) < 1e-9
    near = cosine(e.embed("gel manicure please"), e.embed("can I get a gel manicure"))
    far = cosine(e.embed("gel manicure please"), e.embed("lash lift and tint"))
    assert near > far
    assert e.embed("") == [0.0] * DIMENSIONS


def test_contact_data_is_redacted_from_free_text() -> None:
    text, n = normalise("Mail me at jane.doe@example.test or call +1 555 010 2345  please")
    assert "example.test" not in text
    assert "555" not in text
    assert n == 2
    assert text == "Mail me at [redacted] or call [redacted] please"


def test_non_production_evidence_never_trains() -> None:
    raw = envelope(uuid4(), "correction", {"text": "gel", "corrected_output": "GEL"},
                   env="staging", scope="training")  # fmt: skip
    env, _, _ = parse(raw)
    assert env.learning_scope == "none"


@pytest.mark.parametrize(
    ("raw_payload", "kind", "code"),
    [
        (
            {"text": "x", "corrected_output": "GEL", "email": "a@b.test"},
            "correction",
            "contact_data_field",
        ),
        ({"text": "x", "corrected_output": "not a code"}, "correction", "invalid_payload"),
        ({"text": "x"}, "correction", "invalid_payload"),
        (
            {"services": [{"service_code": "GEL", "service_name": "Gel", "customer_name": "x"}]},
            "catalog",
            "contact_data_field",
        ),
    ],
)
def test_invalid_or_contact_bearing_evidence_is_rejected(
    raw_payload: dict[str, object], kind: str, code: str
) -> None:
    with pytest.raises(EvidenceRejectedError) as exc:
        parse(envelope(uuid4(), kind, raw_payload))
    assert exc.value.code == code


def test_envelope_must_carry_scope_provenance_and_version() -> None:
    raw = envelope(uuid4(), "interaction", {"text": "hello"})
    del raw["provenance"]
    with pytest.raises(EvidenceRejectedError):
        parse(raw)
    raw = envelope(uuid4(), "interaction", {"text": "hello"})
    raw["schema_version"] = 2
    with pytest.raises(EvidenceRejectedError):
        parse(raw)
    catalog = {"services": [{"service_code": "A", "service_name": "A"}]}
    with pytest.raises(EvidenceRejectedError) as exc:
        parse(envelope(uuid4(), "catalog", catalog, scope="training"))
    assert exc.value.code == "catalog_is_knowledge_not_training"


def test_bootstrap_grants_public_schema_to_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    import psycopg

    from gorgona_ai import db as ai_db

    executed: list[str] = []

    class FakeCursor:
        def fetchone(self) -> tuple[int] | None:
            return (1,)

    class FakeConn:
        def __enter__(self) -> FakeConn:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, query: object, params: object = None) -> FakeCursor:
            if hasattr(query, "as_string"):
                executed.append(str(query.as_string()))
            else:
                executed.append(str(query))
            return FakeCursor()

    monkeypatch.setattr(psycopg, "connect", lambda *a, **kw: FakeConn())
    ai_db.bootstrap(
        "postgresql://admin:pw@localhost/postgres",
        "gorgona_ai",
        "owner-pw",
        "worker-pw",
    )
    assert any("grant usage, create on schema public to" in q.lower() for q in executed)
    assert any("create extension if not exists vector" in q.lower() for q in executed)


def test_cloudflare_embedder_matryoshka_256_and_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import http.client
    import json

    class FakeResp:
        status = 200

        def read(self) -> bytes:
            vec = [float(i + 1) for i in range(1024)]
            return json.dumps({"data": [{"embedding": vec}]}).encode("utf-8")

    class FakeConn:
        def __init__(self, host: str, port: int, timeout: float = 20.0) -> None:
            assert host == "api.cloudflare.com"

        def request(self, *args: object, **kwargs: object) -> None:
            return None

        def getresponse(self) -> FakeResp:
            return FakeResp()

        def close(self) -> None:
            return None

    monkeypatch.setattr(http.client, "HTTPSConnection", FakeConn)
    emb = CloudflareEmbedder("acc-123", "tok-abc")
    vec = emb.embed("мужская стрижка")
    assert len(vec) == DIMENSIONS
    assert abs(cosine(vec, vec) - 1.0) < 1e-6
    assert emb.embed("   ") == [0.0] * DIMENSIONS
    assert emb.version.startswith("cf-")

    monkeypatch.delenv("GAI_CF_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("GAI_CF_API_TOKEN", raising=False)
    assert isinstance(default_embedder(), HashingEmbedder)

    monkeypatch.setenv("GAI_CF_ACCOUNT_ID", "acc-123")
    monkeypatch.setenv("GAI_CF_API_TOKEN", "tok-abc")
    monkeypatch.delenv("GAI_EMBEDDER", raising=False)
    assert isinstance(default_embedder(), CloudflareEmbedder)

    monkeypatch.setenv("GAI_EMBEDDER", "hash")
    assert isinstance(default_embedder(), HashingEmbedder)
