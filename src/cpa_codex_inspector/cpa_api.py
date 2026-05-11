from __future__ import annotations

from typing import Any

import httpx

from .models import AppConfig


class CpaApiError(RuntimeError):
    """CPA Management API 调用失败。"""


class CpaApiClient:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        timeout = httpx.Timeout(config.inspect.timeout_seconds)
        self._client = httpx.AsyncClient(
            base_url=f"{config.cpa.base_url}/v0/management",
            headers={"Authorization": f"Bearer {config.cpa.management_key}"},
            timeout=timeout,
        )

    async def __aenter__(self) -> "CpaApiClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(method, path, **kwargs)
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            body = error.response.text.strip()
            message = f"CPA API {method} {path} 返回 HTTP {error.response.status_code}"
            if body:
                message = f"{message}: {body}"
            raise CpaApiError(message) from error
        except httpx.RequestError as error:
            raise CpaApiError(f"CPA API {method} {path} 请求失败：{error}") from error
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as error:
            raise CpaApiError(f"CPA API {method} {path} 返回非 JSON 响应") from error

    async def list_auth_files(self) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/auth-files")
        files = payload.get("files") if isinstance(payload, dict) else []
        return [item for item in files if isinstance(item, dict)]

    async def api_call(
        self,
        *,
        auth_index: str,
        method: str,
        url: str,
        headers: dict[str, str],
        data: str = "",
    ) -> dict[str, Any]:
        payload = await self._request(
            "POST",
            "/api-call",
            json={
                "auth_index": auth_index,
                "method": method,
                "url": url,
                "header": headers,
                "data": data,
            },
        )
        if not isinstance(payload, dict):
            raise CpaApiError("CPA API /api-call 返回格式异常")
        return payload

    async def download_auth_file(self, name: str) -> bytes:
        try:
            response = await self._client.get("/auth-files/download", params={"name": name})
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise CpaApiError(f"下载认证文件 {name} 失败：HTTP {error.response.status_code}") from error
        except httpx.RequestError as error:
            raise CpaApiError(f"下载认证文件 {name} 请求失败：{error}") from error
        return bytes(response.content)

    async def delete_auth_files(self, names: list[str]) -> dict[str, Any]:
        payload = await self._request("DELETE", "/auth-files", json={"names": names})
        result = payload if isinstance(payload, dict) else {}
        failed = result.get("failed") or result.get("failures") or result.get("errors")
        if failed:
            raise CpaApiError(f"删除认证文件失败：{failed}")
        return result

    async def set_auth_file_disabled(self, name: str, disabled: bool) -> dict[str, Any]:
        payload = await self._request("PATCH", "/auth-files/status", json={"name": name, "disabled": disabled})
        return payload if isinstance(payload, dict) else {}
