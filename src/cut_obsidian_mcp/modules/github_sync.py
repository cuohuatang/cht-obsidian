"""⑧ GitHub 私有仓库实时同步模块（V0.3 核心：第二大脑云端镜像）。

流程：智能体工作时 cm_brain_finalize / cm_github_push 把 vault 增量实时推送到
GitHub 私有仓库；本地 Obsidian 开机后经 obsidian-git 插件自动 pull，实现双链拉取。

设计约束：
- token 只存本地 0600 config.json / 环境变量，绝不出现在返回、日志与 README；
- 所有 git 输出经 _redact 脱敏后才返回给调用方；
- 支持 file:// 与本地目录 remote（用于离线/测试，不注入 token）；
- 纯 subprocess 调系统 git：无额外依赖、免第三方库。
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .. import config

_TIMEOUT_SEC = 60


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=10, check=False)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _redact(text: str, cred: dict[str, str]) -> str:
    token = cred.get("token", "")
    if token:
        text = text.replace(token, "***")
    return text


def _vault_git_dir() -> Path:
    return config.VAULT_PATH / ".git"


def _ensure_repo() -> dict[str, Any]:
    """幂等：vault 根 git init + 兜底身份，返回 vault 路径。"""
    if not _git_available():
        raise RuntimeError("系统未安装 git，无法同步 GitHub。请先安装 git。")
    config.VAULT_PATH.mkdir(parents=True, exist_ok=True)
    if not _vault_git_dir().exists():
        _run(["git", "init"], cwd=config.VAULT_PATH)
    # 兜底身份（用户可自行覆盖）
    _run(["git", "config", "user.name", "cut-obsidian-bot"], cwd=config.VAULT_PATH, check=False)
    _run(["git", "config", "user.email", "bot@cut-obsidian.local"], cwd=config.VAULT_PATH, check=False)
    return {"vault_path": str(config.VAULT_PATH)}


def _run(args: list[str], cwd: Path, check: bool = True, cred: dict[str, str] | None = None) -> tuple[str, str]:
    """执行 git 命令；返回 (stdout, stderr)，均经 token 脱敏。"""
    try:
        proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=_TIMEOUT_SEC, check=False)
    except subprocess.SubprocessError as exc:  # timeout / OSError
        raise RuntimeError(f"git 执行失败：{exc}") from exc
    out = proc.stdout or ""
    err = proc.stderr or ""
    if cred:
        out = _redact(out, cred)
        err = _redact(err, cred)
    if check and proc.returncode != 0:
        raise RuntimeError(err.strip() or f"git 命令失败：{' '.join(args[:3])} …")
    return out, err


def _remote_url(cred: dict[str, str]) -> str:
    """构造 remote URL：私有仓库带 token；本地/file 仓库直接使用。"""
    repo = (cred.get("repo") or "").strip()
    if not repo:
        raise RuntimeError("未配置 GitHub 仓库。请先 cm_github_setup(repo, token, branch) 或设置环境变量。")
    if repo.startswith(("file://", "/", "./", "../")) or "://" not in repo:
        return repo
    token = (cred.get("token") or "").strip()
    if not token:
        raise RuntimeError("未配置 GitHub token。请先 cm_github_setup 填写私有仓库 token（不会外泄）。")
    return f"https://x-access-token:{token}@github.com/{repo}.git"


def setup(repo: str, token: str, branch: str = "main") -> dict[str, Any]:
    """配置 GitHub 私有仓库并绑定 remote（token 只写本地 0600 文件）。"""
    cred = config.save_credentials(repo=repo, token=token, branch=branch)
    _ensure_repo()
    url = _remote_url(cred)
    out, _ = _run(["git", "remote", "get-url", "origin"], cwd=config.VAULT_PATH, check=False)
    if out.strip():
        _run(["git", "remote", "set-url", "origin", url], cwd=config.VAULT_PATH, cred=cred)
    else:
        _run(["git", "remote", "add", "origin", url], cwd=config.VAULT_PATH, cred=cred)
    return {"repo": cred["repo"], "branch": cred["branch"], "remote": "origin", "note": "token 已存入本地 0600 配置，后续 push 无需再传。"}


def push(message: str = "") -> dict[str, Any]:
    """把 vault 全部增量 commit + push 到私有仓库（实时上传）。无变更则跳过。"""
    cred = config.load_credentials()
    _ensure_repo()
    url = _remote_url(cred)
    out, _ = _run(["git", "status", "--porcelain"], cwd=config.VAULT_PATH, cred=cred)
    if not out.strip():
        return {"pushed": False, "message": "无待提交变更", "changed_files": 0}
    changed = len([l for l in out.splitlines() if l.strip()])
    msg = (message or "cut-obsidian 第二大脑实时同步").strip()
    _run(["git", "add", "-A"], cwd=config.VAULT_PATH, cred=cred)
    _run(["git", "commit", "-m", msg], cwd=config.VAULT_PATH, cred=cred, check=False)
    branch = cred.get("branch", "main")
    push_args = ["git", "push", "origin", f"HEAD:{branch}"]
    out_p, _ = _run(push_args, cwd=config.VAULT_PATH, cred=cred)
    return {
        "pushed": True,
        "message": msg,
        "changed_files": changed,
        "branch": branch,
        "output": (out_p or "").strip()[:400],
    }


def pull() -> dict[str, Any]:
    """从私有仓库拉取并合并到本地 vault（Obsidian 开机可先由本工具拉，再打开即见）。"""
    cred = config.load_credentials()
    _ensure_repo()
    url = _remote_url(cred)
    branch = cred.get("branch", "main")
    out_p, err_p = _run(["git", "pull", "--rebase", "origin", branch], cwd=config.VAULT_PATH, cred=cred, check=False)
    if "CONFLICT" in (out_p + err_p):
        _run(["git", "rebase", "--abort"], cwd=config.VAULT_PATH, cred=cred, check=False)
        raise RuntimeError("拉取冲突（本地与云端同一文件有不同修改），已中止合并；建议先 cm_github_push 推送本地，再重试 pull。")
    return {"pulled": True, "output": (out_p + err_p).strip()[:400]}


def status() -> dict[str, Any]:
    """本地与远程差异概览（不含 token）。"""
    cred = config.load_credentials()
    has_repo = bool((cred.get("repo") or "").strip())
    _ensure_repo()
    out, _ = _run(["git", "status", "--porcelain"], cwd=config.VAULT_PATH, cred=cred, check=False)
    local_changes = len([l for l in out.splitlines() if l.strip()])
    branch = cred.get("branch", "main")
    ahead = behind = 0
    if has_repo:
        # behind：远端领先本地（HEAD..origin/branch 的数量）
        try:
            out_b, _ = _run(["git", "rev-list", "--count", f"HEAD..origin/{branch}"], cwd=config.VAULT_PATH, cred=cred, check=False)
            behind = int(out_b.strip()) if out_b.strip().isdigit() else 0
        except Exception:  # noqa: BLE001 —— 远端未建立时忽略
            behind = 0
        # ahead：本地领先远端（origin/branch..HEAD 的数量）
        try:
            out_a, _ = _run(["git", "rev-list", "--count", f"origin/{branch}..HEAD"], cwd=config.VAULT_PATH, cred=cred, check=False)
            ahead = int(out_a.strip()) if out_a.strip().isdigit() else 0
        except Exception:  # noqa: BLE001
            ahead = 0
    return {
        "repo": cred.get("repo", ""),
        "branch": branch,
        "local_changes": local_changes,
        "ahead_local": ahead,  # 本地领先远端（未推送）
        "behind_remote": behind,  # 远端领先本地（未拉取）
        "has_remote": has_repo,
    }
