import pytest

from src.network.proxy_manager import ProxyManager, normalize_proxy_url, redact_proxy_url


def test_proxy_normalization_and_redaction():
    assert normalize_proxy_url("host.test:8080") == "http://host.test:8080"
    assert redact_proxy_url("http://user:password@host.test:8080") == "http://***:***@host.test:8080"


def test_socks_proxy_is_rejected():
    with pytest.raises(ValueError, match="SOCKS"):
        normalize_proxy_url("socks5://host.test:1080")


@pytest.mark.asyncio
async def test_rotation_and_failure_threshold():
    manager = ProxyManager(["one.test:80", "two.test:81"], max_retries=2)
    first = await manager.get_proxy()
    second = await manager.get_proxy()
    assert first != second
    manager.mark_proxy_failure(first)
    manager.mark_proxy_failure(first)
    assert first in manager.bad_proxies
    assert await manager.get_proxy() == second
    await manager.mark_proxy_good(first, 0.1)
    assert manager.proxies[first].is_healthy
    assert first not in manager.bad_proxies
