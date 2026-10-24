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

    # ── 多用户体系（V0.5）：GitHub OAuth 登录 + 每用户隔离 + 即焚 + 管理总览 ──
    import hashlib as _hashlib
    import hmac as _hmac
    import secrets as _secrets
    import time as _time
    import urllib.parse as _up
    import urllib.request as _ur

    from starlette.responses import RedirectResponse as _Redirect

    USERS_ROOT = _Path("/data/users")
    SECRET = token or "cht-obsidian-default-secret"
    OAUTH_CID = os.environ.get("GITHUB_OAUTH_CLIENT_ID", "").strip()
    OAUTH_SEC = os.environ.get("GITHUB_OAUTH_CLIENT_SECRET", "").strip()
    SESSION_TTL = int(os.environ.get("SESSION_TTL", "86400"))
    IDLE_WIPE = int(os.environ.get("IDLE_WIPE_SEC", "1800"))  # 闲置 30 分钟即焚
    _last_seen: dict[str, float] = {}

    def _sign(payload: str) -> str:
        return _hmac.new(SECRET.encode(), payload.encode(), _hashlib.sha256).hexdigest()

    def _make_cookie(login: str) -> str:
        exp = str(int(_time.time()) + SESSION_TTL)
        return f"{login}.{exp}.{_sign(login + '.' + exp)}"

    def _read_cookie(request) -> str | None:
        raw = request.cookies.get("cm_session", "")
        try:
            login, exp, sig = raw.split(".", 2)
        except ValueError:
            return None
        if int(exp) < _time.time() or not _hmac.compare_digest(sig, _sign(login + "." + exp)):
            return None
        if "/" in login or ".." in login or not login:
            return None
        return login

    def _user_dir(login: str) -> _Path:
        return USERS_ROOT / login

    def _user_cfg_file(login: str) -> _Path:
        return _user_dir(login) / "config.json"

    def _load_user_cfg(login: str) -> dict:
        f = _user_cfg_file(login)
        if f.is_file():
            try:
                return _json.loads(f.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return {}
        return {}

    def _save_user_cfg(login: str, cfg: dict) -> None:
        d = _user_dir(login)
        d.mkdir(parents=True, exist_ok=True)
        f = _user_cfg_file(login)
        f.write_text(_json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            f.chmod(0o600)
        except OSError:
            pass

    def _wipe_vault(login: str) -> None:
        """即焚：删除该用户 vault 内全部内容（含索引与本地 git）。"""
        import shutil as _sh
        v = _user_dir(login) / "vault"
        if v.exists():
            _sh.rmtree(v, ignore_errors=True)

    def _idle_sweeper() -> None:
        """后台清扫：闲置超 IDLE_WIPE 的用户 vault 即焚。"""
        import threading as _th
        def loop():
            while True:
                _time.sleep(60)
                now = _time.time()
                for d in USERS_ROOT.glob("*"):
                    if not d.is_dir():
                        continue
                    if now - _last_seen.get(d.name, 0) > IDLE_WIPE:
                        _wipe_vault(d.name)
        _th.Thread(target=loop, daemon=True).start()

    class _UserCtx:
        """把全局 vault/config 指向某用户；请求结束恢复（单请求串行，低并发安全）。"""

        def __init__(self, login: str):
            self.login = login
            self.saved: tuple = ()

        def __enter__(self):
            v = _user_dir(self.login) / "vault"
            idx = _user_dir(self.login) / "index.sqlite"
            v.mkdir(parents=True, exist_ok=True)
            from cut_obsidian_mcp import config as _c
            from cut_obsidian_mcp.storage import vault as _v
            self.saved = (_v.VAULT_PATH, _v.INDEX_PATH, _c.VAULT_PATH, _c.INDEX_PATH, _c.CONFIG_FILE)
            _v.VAULT_PATH = v
            _v.INDEX_PATH = idx
            _c.VAULT_PATH = v
            _c.INDEX_PATH = idx
            _c.CONFIG_FILE = _user_cfg_file(self.login)
            vault.init_vault()
            return self

        def __exit__(self, *a):
            from cut_obsidian_mcp import config as _c
            from cut_obsidian_mcp.storage import vault as _v
            _v.VAULT_PATH, _v.INDEX_PATH, _c.VAULT_PATH, _c.INDEX_PATH, _c.CONFIG_FILE = self.saved

    # ── OAuth 路由 ──
    async def _auth_login(request):
        if not OAUTH_CID:
            return _JSON({"error": "服务端未配置 GitHub OAuth（GITHUB_OAUTH_CLIENT_ID）。管理员：见部署文档注册 OAuth App 后写入 .env。"}, status_code=503)
        state = _secrets.token_urlsafe(16)
        cb = str(request.url_for("auth_cb"))
        url = ("https://github.com/login/oauth/authorize?client_id=" + _up.quote(OAUTH_CID)
               + "&redirect_uri=" + _up.quote(cb, safe="")
               + "&scope=repo&state=" + state)
        resp = _Redirect(url)
        resp.set_cookie("cm_oauth_state", state, max_age=600, httponly=True, samesite="lax")
        return resp

    async def _auth_cb(request):
        q = request.query_params
        if q.get("state") != request.cookies.get("cm_oauth_state", ""):
            return _JSON({"error": "state 校验失败，请重新登录"}, status_code=400)
        code = q.get("code", "")
        if not code:
            return _JSON({"error": "GitHub 未返回授权码"}, status_code=400)
        data = _up.urlencode({
            "client_id": OAUTH_CID, "client_secret": OAUTH_SEC, "code": code,
            "redirect_uri": str(request.url_for("auth_cb")),
        }).encode()
        req = _ur.Request("https://github.com/login/oauth/access_token", data=data,
                          headers={"Accept": "application/json"})
        tok = _json.loads(_ur.urlopen(req, timeout=20).read())["access_token"]
        req2 = _ur.Request("https://api.github.com/user",
                           headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"})
        me = _json.loads(_ur.urlopen(req2, timeout=20).read())
        login = me["login"]
        cfg = _load_user_cfg(login)
        cfg.setdefault("repo", "")
        cfg.setdefault("branch", "main")
        cfg["token"] = tok  # OAuth 授权即得推送凭证，无需用户另填
        cfg["auth_mode"] = "oauth"
        _save_user_cfg(login, cfg)
        resp = _Redirect("/app")
        resp.set_cookie("cm_session", _make_cookie(login), max_age=SESSION_TTL,
                        httponly=True, samesite="lax")
        resp.delete_cookie("cm_oauth_state")
        return resp

    async def _auth_logout(request):
        login = _read_cookie(request)
        resp = _Redirect("/")
        if login:
            _wipe_vault(login)  # 登出即焚
        resp.delete_cookie("cm_session")
        return resp

    # ── 用户控制台 API ──
    async def _app_me(request):
        login = _read_cookie(request)
        if not login:
            return _JSON({"error": "未登录"}, status_code=401)
        _last_seen[login] = _time.time()
        cfg = _load_user_cfg(login)
        return _JSON({
            "login": login,
            "repo": cfg.get("repo", ""),
            "branch": cfg.get("branch", "main"),
            "configured": bool(cfg.get("repo")),
            "oauth": True,
            "ephemeral": True,
            "idle_wipe_min": IDLE_WIPE // 60,
        })

    async def _app_save(request):
        login = _read_cookie(request)
        if not login:
            return _JSON({"error": "未登录"}, status_code=401)
        _last_seen[login] = _time.time()
        body = _json.loads(await request.body() or b"{}")
        cfg = _load_user_cfg(login)
        if not cfg.get("repo"):
            return _JSON({"error": "请先在控制台绑定你的 GitHub 仓库（用户名/仓库名）"}, status_code=400)
        from cut_obsidian_mcp.modules import memory as _memory
        with _UserCtx(login):
            r = _memory.save(
                body.get("content", ""),
                title=body.get("title"),
                tags=body.get("tags"),
                agent="web",
            )
            # 保存后立即推送到该用户自己的仓库（最快上云）
            from cut_obsidian_mcp.modules import github_sync as _gh2
            pushed = _gh2.push(message=body.get("message") or f"web save by {login}")
        return _JSON({"ok": True, "note": r, "pushed": pushed})

    async def _app_bind(request):
        login = _read_cookie(request)
        if not login:
            return _JSON({"error": "未登录"}, status_code=401)
        body = _json.loads(await request.body() or b"{}")
        repo = (body.get("repo") or "").strip()
        if not repo or "/" not in repo:
            return _JSON({"error": "仓库格式应为 用户名/仓库名"}, status_code=400)
        cfg = _load_user_cfg(login)
        cfg["repo"] = repo
        cfg["branch"] = (body.get("branch") or "main").strip() or "main"
        _save_user_cfg(login, cfg)
        return _JSON({"ok": True, "repo": repo, "branch": cfg["branch"]})

    async def _app_push(request):
        login = _read_cookie(request)
        if not login:
            return _JSON({"error": "未登录"}, status_code=401)
        _last_seen[login] = _time.time()
        from cut_obsidian_mcp.modules import github_sync as _gh2
        with _UserCtx(login):
            d = _gh2.push()
        return _JSON({"ok": True, **d})

    # ── 管理总览（管理员口令） ──
    async def _admin_page(request):
        return FileResponse(_Path(__file__).parent / "admin.html", media_type="text/html")

    async def _admin_users(request):
        if request.headers.get("authorization", "") != f"Bearer {token}":
            return _JSON({"error": "unauthorized"}, status_code=401)
        import shutil as _sh
        users = []
        for d in sorted(USERS_ROOT.glob("*")):
            if not d.is_dir():
                continue
            cfg = _load_user_cfg(d.name)
            vault = d / "vault"
            size = sum(f.stat().st_size for f in vault.rglob("*") if f.is_file()) if vault.exists() else 0
            users.append({
                "login": d.name,
                "repo": cfg.get("repo", ""),
                "branch": cfg.get("branch", "main"),
                "auth": cfg.get("auth_mode", "?"),
                "has_token": bool(cfg.get("token")),
                "vault_bytes": size,
                "last_seen_min": round((_time.time() - _last_seen.get(d.name, 0)) / 60, 1) if d.name in _last_seen else None,
            })
        return _JSON({"users": users, "idle_wipe_min": IDLE_WIPE // 60})

    multiuser_routes = [
        Route("/auth/login", _auth_login, methods=["GET"]),
        Route("/auth/callback", _auth_cb, methods=["GET"], name="auth_cb"),
        Route("/auth/logout", _auth_logout, methods=["GET"]),
        Route("/app", lambda r: FileResponse(_Path(__file__).parent / "multiuser.html", media_type="text/html"), methods=["GET"]),
        Route("/api/app/me", _app_me, methods=["GET"]),
        Route("/api/app/bind", _app_bind, methods=["POST"]),
        Route("/api/app/save", _app_save, methods=["POST"]),
        Route("/api/app/push", _app_push, methods=["POST"]),
        Route("/admin", _admin_page, methods=["GET"]),
        Route("/api/admin/users", _admin_users, methods=["GET"]),
    ]
    if USERS_ROOT.exists() or True:
        USERS_ROOT.mkdir(parents=True, exist_ok=True)
    _idle_sweeper()

    # 把 MCP 应用挂到子路径，API 路由优先匹配
    from starlette.applications import Starlette as _Starlette
    app = _Starlette(routes=multiuser_routes + api_routes + [Mount("/", app=app)])

    if token:
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.responses import JSONResponse
        from starlette.types import Receive, Scope, Send

        class BearerAuth(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                # 放行健康检查、配置页、多用户登录/控制台（它们走会话或自带校验）
                if (request.url.path in ("/healthz", "/health", "/", "/app", "/admin")
                        or request.url.path.startswith(("/auth/", "/api/app/"))):
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
