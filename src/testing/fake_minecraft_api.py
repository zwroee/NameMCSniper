"""A loopback-only Minecraft API simulator for integration tests and development."""

from typing import Iterable, List

from aiohttp import web


class FakeMinecraftAPI:
    def __init__(self, statuses: Iterable[int] = (400, 400, 200), *, profile_status: int = 200):
        self.statuses: List[int] = list(statuses)
        if not self.statuses:
            raise ValueError("At least one response status is required")
        self.profile_status = profile_status
        self.requests = []
        self.profile_requests = 0
        self._runner = None
        self._site = None
        self.base_url = ""

    async def __aenter__(self) -> "FakeMinecraftAPI":
        app = web.Application()
        app.router.add_put("/minecraft/profile/name/{username}", self._claim)
        app.router.add_get("/minecraft/profile", self._profile)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await self._site.start()
        port = self._site._server.sockets[0].getsockname()[1]
        self.base_url = f"http://127.0.0.1:{port}"
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._runner:
            await self._runner.cleanup()

    async def _profile(self, request: web.Request) -> web.Response:
        self.profile_requests += 1
        if self.profile_status == 200:
            return web.json_response({"id": "0" * 32, "name": "SimulatedAccount"})
        return web.json_response({"error": "simulated profile failure"}, status=self.profile_status)

    async def _claim(self, request: web.Request) -> web.Response:
        self.requests.append(
            {
                "username": request.match_info["username"],
                "authorization": request.headers.get("Authorization", ""),
            }
        )
        index = min(len(self.requests) - 1, len(self.statuses) - 1)
        status = self.statuses[index]
        headers = {"Retry-After": "0.001"} if status == 429 else None
        return web.json_response({"simulated": True, "status": status}, status=status, headers=headers)
