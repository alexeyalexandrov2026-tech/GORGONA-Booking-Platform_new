"""The live test server keeps pooled connections usable for the length of a test.

Playwright 1.63's request client (`page.request`, `route.fetch`) pools sockets in a Node
`http.Agent({keepAlive: true})` with no idle limit of its own. uvicorn closes a connection
that stays idle for `timeout_keep_alive` seconds (5 by default). When the client reuses a
pooled socket at the moment the server closes it, the request fails with "read ECONNRESET"
(seen in N8 full-4: `apiRequestContext.post: read ECONNRESET` at workforce.spec.ts:35).
"""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from tests.integration.live_server import free_port, live_server

WEB = Path(__file__).resolve().parents[3] / "web"
UVICORN_DEFAULT_IDLE_MS = 5000

# The bare agent is built exactly as Playwright's APIRequestContext._ensureAgent builds it.
# The event loop is kept busy across the server's default idle limit, as a loaded test
# worker is, so the server's close has not been seen when the next request takes the socket.
BARE_AGENT = """
const http = require("http");
const [url, idle] = [process.argv[2], Number(process.argv[3])];
const agent = new http.Agent({ keepAlive: true });
const send = (done) => http.request(url, { agent, method: "POST" }, (res) => {
  res.resume(); res.on("end", () => done({ code: res.statusCode }));
}).on("error", (e) => done({ error: e.code || e.message })).end();
send((first) => {
  if (first.error) { console.log(JSON.stringify(first)); return; }
  setTimeout(() => {
    const until = Date.now() + 700;
    while (Date.now() < until);
    send((second) => console.log(JSON.stringify(second)));
  }, idle - 300);
});
"""

# The real client: one request context per idle gap, the gaps spread across the edge.
PLAYWRIGHT = """
const { request } = require(process.argv[4]);
const [url, edge] = [process.argv[2], Number(process.argv[3])];
const [from, to] = [edge - 150, edge + 100];
(async () => {
  const contexts = await Promise.all(Array.from({ length: 200 }, () => request.newContext()));
  await Promise.all(contexts.map((c) => c.post(url)));
  const failed = await Promise.all(contexts.map(async (c, i) => {
    await new Promise((r) => setTimeout(r, from + ((to - from) * i) / 199));
    try { await c.post(url, { data: { i } }); return null; }
    catch (e) { return String(e.message).split("\\n")[0]; }
  }));
  await Promise.all(contexts.map((c) => c.dispose()));
  console.log(JSON.stringify({ failed: failed.filter(Boolean) }));
})();
"""


def _node() -> str:
    if os.environ.get("GBA_REQUIRE_BROWSER") != "1":
        pytest.skip("BLOCKED: the keep-alive check runs Node; set GBA_REQUIRE_BROWSER=1")
    node = shutil.which("node")
    assert node is not None, "Node is required"
    return node


def _app() -> FastAPI:
    app = FastAPI()

    @app.post("/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "yes"}

    return app


def _probe(tmp_path: Path, script: str, *args: str) -> dict[str, object]:
    probe = tmp_path / "probe.cjs"
    probe.write_text(script, encoding="utf-8")
    with live_server(_app(), free_port()) as base:
        done = subprocess.run(  # noqa: S603 - local node and a script written by this test
            [_node(), str(probe), f"{base}/ping", *args],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    assert done.returncode == 0, done.stderr
    return dict(json.loads(done.stdout.strip().splitlines()[-1]))


def test_a_pooled_socket_reused_after_the_default_idle_limit_is_answered(tmp_path: Path) -> None:
    assert _probe(tmp_path, BARE_AGENT, str(UVICORN_DEFAULT_IDLE_MS)) == {"code": 200}


def test_playwright_requests_across_the_default_idle_edge_are_answered(tmp_path: Path) -> None:
    core = WEB / "node_modules" / "playwright-core"
    assert core.is_dir(), "install web dependencies first"
    result = _probe(tmp_path, PLAYWRIGHT, str(UVICORN_DEFAULT_IDLE_MS), str(core))
    assert result == {"failed": []}


def test_the_server_stops_promptly_while_a_pooled_connection_is_idle() -> None:
    with httpx.Client() as client:
        with live_server(_app(), free_port()) as base:  # leaving asserts the thread ended
            assert client.post(f"{base}/ping").status_code == 200
            began = time.monotonic()
        assert time.monotonic() - began < 5
        with pytest.raises(httpx.TransportError):
            client.post(f"{base}/ping")
