import socket
from urllib.parse import urlparse

import aiohttp
import ntplib
import pytest


@pytest.fixture(autouse=True)
def block_external_aiohttp(monkeypatch):
    """Fail tests immediately if aiohttp tries to reach a non-loopback host."""
    original = aiohttp.ClientSession._request

    async def guarded_request(self, method, url, *args, **kwargs):
        host = (urlparse(str(url)).hostname or "").lower()
        allowed = host == "localhost"
        if not allowed:
            try:
                allowed = ip_is_loopback(host)
            except ValueError:
                allowed = False
        if not allowed:
            raise AssertionError(f"External network access is forbidden in tests: {method} {url}")
        return await original(self, method, url, *args, **kwargs)

    monkeypatch.setattr(aiohttp.ClientSession, "_request", guarded_request)

    original_getaddrinfo = socket.getaddrinfo

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host not in {None, "localhost", "127.0.0.1", "::1"}:
            raise AssertionError(f"External DNS access is forbidden in tests: {host}")
        return original_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)

    def blocked_ntp(*args, **kwargs):
        raise AssertionError("External NTP access is forbidden in tests")

    monkeypatch.setattr(ntplib.NTPClient, "request", blocked_ntp)


def ip_is_loopback(host: str) -> bool:
    import ipaddress

    return ipaddress.ip_address(host).is_loopback
