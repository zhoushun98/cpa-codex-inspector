from __future__ import annotations

import httpx
import pytest
import respx

from cpa_codex_inspector.cpa_api import CpaApiClient, CpaApiError
from cpa_codex_inspector.models import AppConfig, CpaConfig


def _config() -> AppConfig:
    return AppConfig(cpa=CpaConfig(base_url="http://cpa.local", management_key="secret"))


@pytest.mark.asyncio
@respx.mock
async def test_list_auth_files_uses_management_bearer_token() -> None:
    route = respx.get("http://cpa.local/v0/management/auth-files").mock(
        return_value=httpx.Response(200, json={"files": [{"name": "a.json"}, "bad"]})
    )

    async with CpaApiClient(_config()) as client:
        files = await client.list_auth_files()

    assert files == [{"name": "a.json"}]
    assert route.calls[0].request.headers["authorization"] == "Bearer secret"


@pytest.mark.asyncio
@respx.mock
async def test_api_call_sends_proxy_probe_payload() -> None:
    route = respx.post("http://cpa.local/v0/management/api-call").mock(
        return_value=httpx.Response(200, json={"status_code": 200, "body": "{}"})
    )

    async with CpaApiClient(_config()) as client:
        result = await client.api_call(
            auth_index="3",
            method="GET",
            url="https://chatgpt.com/backend-api/wham/usage",
            headers={"Authorization": "Bearer $TOKEN$"},
        )

    assert result["status_code"] == 200
    assert route.calls[0].request.read()
    assert route.calls[0].request.headers["authorization"] == "Bearer secret"


@pytest.mark.asyncio
@respx.mock
async def test_delete_auth_files_raises_on_partial_failure_payload() -> None:
    respx.delete("http://cpa.local/v0/management/auth-files").mock(
        return_value=httpx.Response(207, json={"failed": [{"name": "bad.json", "error": "not found"}]})
    )

    async with CpaApiClient(_config()) as client:
        with pytest.raises(CpaApiError, match="删除认证文件失败"):
            await client.delete_auth_files(["bad.json"])
