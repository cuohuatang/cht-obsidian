"""cht-obsidian 启动器：按环境变量选择传输方式（不改动上游源码）。

上游 server.py 硬编码 mcp.run(transport="stdio")，无法远程调用。
本启动器复用同一个 mcp 实例，按 MCP_TRANSPORT 决定怎么跑：

  stdio            本地进程通信（默认，与原版一致）
  streamable-http  HTTP，端点 http://HOST:PORT/mcp   （推荐，新协议）
  sse               HTTP，端点 http://HOST:PORT/sse   （旧协议，兼容老客户端）

两处容易踩的坑：
  1. 容器里 MCP_HOST 必须是 0.0.0.0，默认 127.0.0.1 会导致外部连不上。
  2. MCP 的 HTTP 模式本身不带任何鉴权。设置 MCP_AUTH_TOKEN 后，本启动器
     会强制校验 Authorization: Bearer <token>，避免笔记库裸奔在公网上。
     不设该变量则不做校验（仅建议用于 127.0.0.1 或内网环境）。
"""

from __future__ import annotations

import os
import sys

from cut_obsidian_mcp.server import mcp


def _build_app(transport: str, path: str):
    """把 MCP 应用包一层可选的 Bearer Token 校验，并挂载配置中心 UI。"""
    token = os.environ.get("MCP_AUTH_TOKEN", "").strip()

    # MCP SDK 默认开启 DNS rebinding 防护，只放行 localhost 的 Host 头，
    # 公网 IP 直连会得到 421 Invalid Host header。有 Bearer 鉴权兜底时
    # 可以安全关闭；纯内网部署也可通过 MCP_ALLOW_ANY_HOST=0 恢复默认防护。
    allow_any = os.environ.get("MCP_ALLOW_ANY_HOST", "1") == "1"
    ts = None
    if allow_any:
        from mcp.server.transport_security import TransportSecuritySettings
        ts = TransportSecuritySettings(enable_dns_rebinding_protection=False)

    if transport == "streamable-http":
        app = mcp.streamable_http_app(transport_security=ts)
    else:  # sse
        app = mcp.sse_app(transport_security=ts)

    # ── 配置中心 API + UI（V0.4）────────────────────────────────
    from pathlib import Path as _Path

    import json as _json

    from starlette.responses import FileResponse, JSONResponse as _JSON
    from starlette.routing import Mount, Route

    from cut_obsidian_mcp import config as _config
    from cut_obsidian_mcp.modules import github_sync as _gh

    UI_FILE = _Path(__file__).parent / "setup_ui.html"

    async def _ui(request):
        if UI_FILE.exists():
            return FileResponse(UI_FILE, media_type="text/html")
        return _JSON({"error": "setup_ui.html 未随镜像部署"}, status_code=404)

    def _mask(t: str) -> str:
        return (t[:7] + "…" + t[-4:]) if len(t) > 12 else ("已设置" if t else "")

    async def _status(request):
        cred = _config.load_credentials() or {}
        return _JSON({
            "vault_path": str(_config.VAULT_PATH),
            "configured": bool(cred.get("repo")),
            "repo": cred.get("repo", ""),
            "branch": cred.get("branch", "main"),
            "auth_mode": "ssh" if cred.get("auth_mode") == "ssh" else "token",
            "token_masked": _mask(cred.get("token", "")),
            "git_ok": _gh._git_available(),
        })

    async def _save(request):
        try:
            body = _json.loads(await request.body() or b"{}")
            repo = (body.get("repo") or "").strip()
            branch = (body.get("branch") or "main").strip() or "main"
            if not repo or "/" not in repo:
                return _JSON({"error": "仓库地址格式应为 用户名/仓库名"}, status_code=400)

            if body.get("mode") == "ssh":
                key = (body.get("ssh_key") or "").strip()
                if "PRIVATE KEY" not in key:
                    return _JSON({"error": "SSH 私钥格式不正确"}, status_code=400)
                keyfile = _config.VAULT_PATH.parent / "gitkey"
                keyfile.write_text(key + "\n", encoding="utf-8")
                keyfile.chmod(0o600)
                url = f"git@github.com:{repo}.git"
                cred = _config.save_credentials(repo=repo, token="", branch=branch, auth_mode="ssh")
            else:
                old = _config.load_credentials() or {}
                tok = (body.get("token") or "").strip() or old.get("token", "")
                if not tok:
                    return _JSON({"error": "首次配置必须填写 GitHub 令牌"}, status_code=400)
                _config.save_credentials(repo=repo, token=tok, branch=branch, auth_mode="token")
                cred = _config.load_credentials()  # 重新读取：save 返回值是脱敏的，不含 token
                url = _gh._remote_url(cred)

            _gh._ensure_repo()
            out, _ = _gh._run(["git", "remote", "get-url", "origin"], cwd=_config.VAULT_PATH, check=False)
            args = (["git", "remote", "set-url", "origin", url] if out.strip()
                    else ["git", "remote", "add", "origin", url])
            if body.get("mode") == "ssh":
                kf = str(_config.VAULT_PATH.parent / "gitkey")
                _gh._run(["git", "config", "core.sshCommand",
                          f"ssh -i {kf} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no"],
                         cwd=_config.VAULT_PATH, check=False)
            _gh._run(args, cwd=_config.VAULT_PATH, cred=cred)
            return _JSON({"ok": True, "repo": repo, "branch": branch})
        except Exception as exc:  # noqa: BLE001
            return _JSON({"error": str(exc)}, status_code=500)

    async def _test(request):
        try:
            cred = _config.load_credentials() or {}
            if not cred.get("repo"):
                return _JSON({"error": "尚未配置仓库，请先保存配置"}, status_code=400)
            _gh._ensure_repo()
            out, err = _gh._run(["git", "ls-remote", "--heads", "origin"],
                                cwd=_config.VAULT_PATH, cred=cred)
            head = out.splitlines()[0].split("\t")[0] if out.strip() else ""
            return _JSON({"ok": True, "head": head, "stderr": err[:200]})
        except Exception as exc:  # noqa: BLE001
            return _JSON({"error": str(exc)}, status_code=500)

    async def _push(request):
        try:
            d = _gh.push()
            return _JSON({"ok": True, **d})
        except Exception as exc:  # noqa: BLE001
            return _JSON({"error": str(exc)}, status_code=500)

    async def _pull(request):
        try:
            d = _gh.pull()
            return _JSON({"ok": True, **d})
        except Exception as exc:  # noqa: BLE001
            return _JSON({"error": str(exc)}, status_code=500)

    api_routes = [
        Route("/", _ui, methods=["GET"]),
        Route("/api/setup/status", _status, methods=["GET"]),
        Route("/api/setup/save", _save, methods=["POST"]),
        Route("/api/setup/test", _test, methods=["POST"]),
        Route("/api/setup/push", _push, methods=["POST"]),
        Route("/api/setup/pull", _pull, methods=["POST"]),
    ]

    # 把 MCP 应用挂到子路径，API 路由优先匹配
    from starlette.applications import Starlette as _Starlette
    app = _Starlette(routes=api_routes + [Mount("/", app=app)])

    if token:
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.responses import JSONResponse
        from starlette.types import Receive, Scope, Send

        class BearerAuth(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                # 放行健康检查与配置中心页面本身（页面公开，操作走 API 鉴权）
                if request.url.path in ("/healthz", "/health", "/"):
                    return await call_next(request)
                auth = request.headers.get("authorization", "")
                if not auth.startswith("Bearer ") or auth[7:].strip() != token:
                    return JSONResponse({"error": "unauthorized"}, status_code=401)
                return await call_next(request)

        app.add_middleware(BearerAuth)
        print("[cht-obsidian] 鉴权已开启：需携带 Authorization: Bearer <token>", file=sys.stderr)
    else:
        print(
            "[cht-obsidian] 警告：未设置 MCP_AUTH_TOKEN，任何能访问该端口的人都可读写笔记库",
            file=sys.stderr,
        )

    return app


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio").strip().lower()
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8000"))
    path = os.environ.get("MCP_PATH", "")

    if transport == "stdio":
        print("[cht-obsidian] transport=stdio", file=sys.stderr)
        mcp.run(transport="stdio")
        return

    if transport not in ("streamable-http", "sse"):
        raise ValueError(f"未知的 MCP_TRANSPORT: {transport}（可选 stdio / streamable-http / sse）")

    default_path = "/mcp" if transport == "streamable-http" else "/sse"
    endpoint = path if path else default_path
    if path and not path.startswith("/"):
        endpoint = f"/{path}"

    import uvicorn

    app = _build_app(transport, endpoint)
    print(f"[cht-obsidian] transport={transport} http://{host}:{port}{endpoint}", file=sys.stderr)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
