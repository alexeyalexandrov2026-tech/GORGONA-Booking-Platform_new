"""Shared real configuration commands for integration and browser fixtures."""

from uuid import UUID, uuid7

import httpx

from tests.integration.seed import FakeUser
from tests.support.fake_idp import FakeIdp


class Config:
    def __init__(self, client: httpx.AsyncClient, idp: FakeIdp) -> None:
        self.client, self.idp = client, idp

    def auth(self, user: FakeUser) -> dict[str, str]:
        return self.idp.bearer(user.subject, email=user.email)

    def headers(self, user: FakeUser, key: str | None = None) -> dict[str, str]:
        return {**self.auth(user), "Idempotency-Key": key or str(uuid7())}

    async def profile(
        self, user: FakeUser, business: UUID, revision: int, industries: list[int]
    ) -> None:
        response = await self.client.put(
            f"/v1/businesses/{business}/profile",
            json={"expected_revision": revision, "industry_ids": industries},
            headers=self.headers(user),
        )
        assert response.status_code == 200, response.text

    async def draft(
        self,
        user: FakeUser,
        business: UUID,
        expected_version: int,
        modules: list[str],
        *,
        profile_revision: int = 1,
        key: str | None = None,
    ) -> httpx.Response:
        return await self.client.put(
            f"/v1/businesses/{business}/configuration/draft",
            json={
                "expected_version": expected_version,
                "profile_revision": profile_revision,
                "module_ids": modules,
            },
            headers=self.headers(user, key),
        )

    async def step(
        self,
        user: FakeUser,
        business: UUID,
        version: int,
        step: str,
        revision: int,
        key: str | None = None,
    ) -> httpx.Response:
        return await self.client.post(
            f"/v1/businesses/{business}/configuration/versions/{version}/{step}",
            json={"expected_revision": revision},
            headers=self.headers(user, key),
        )

    async def get(self, user: FakeUser, business: UUID, suffix: str = "") -> httpx.Response:
        return await self.client.get(
            f"/v1/businesses/{business}/configuration{suffix}", headers=self.auth(user)
        )

    async def publish(
        self, user: FakeUser, business: UUID, expected_version: int, modules: list[str]
    ) -> dict[str, object]:
        """Draft, validate and publish; returns the published version."""
        drafted = await self.draft(user, business, expected_version, modules)
        assert drafted.status_code == 200, drafted.text
        version = drafted.json()["version"]
        validated = await self.step(user, business, version, "validate", 1)
        assert validated.status_code == 200, validated.text
        published = await self.step(user, business, version, "publish", 2)
        assert published.status_code == 200, published.text
        result: dict[str, object] = published.json()
        return result
