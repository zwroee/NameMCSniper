import pytest
from aiohttp import web

from src.notifications.discord_notifier import DiscordNotifier


@pytest.mark.asyncio
async def test_context_manager_closes_session_without_sending():
    notifier = DiscordNotifier("https://discord.com/api/webhooks/fake/fake")
    async with notifier:
        assert notifier.session is not None
        assert not notifier.session.closed
    assert notifier.session is None


@pytest.mark.asyncio
async def test_webhook_payload_can_be_sent_to_loopback():
    payloads = []

    async def webhook(request):
        payloads.append(await request.json())
        return web.Response(status=204)

    app = web.Application()
    app.router.add_post("/webhook", webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        async with DiscordNotifier(f"http://127.0.0.1:{port}/webhook") as notifier:
            assert await notifier.notify_status_update("local test") is True
    finally:
        await runner.cleanup()
    assert payloads[0]["embeds"][0]["description"] == "local test"
