"""路径与配置：全部可通过环境变量覆盖，默认纯本地、免 key。"""

from __future__ import annotations

import json
import os
from pathlib import Path

APP_DIR = Path(os.environ.get("CUT_OBSIDIAN_HOME", Path.home() / ".cut-obsidian"))

# vault：markdown 唯一真相源，Obsidian 可直接打开
VAULT_PATH = Path(os.environ.get("CUT_OBSIDIAN_VAULT_PATH", APP_DIR / "vault"))

# 检索索引（SQLite FTS5，可重建）
INDEX_PATH = Path(os.environ.get("CUT_OBSIDIAN_INDEX_PATH", APP_DIR / "index.sqlite"))

# vault 子目录（固定命名，Obsidian 友好）
VAULT_DIRS = {
    "memory": "01-流水账",
    "lessons": "02-踩坑本",
    "corrections": "03-纠错台账",
    "summaries": "04-经验总结",
    "handoffs": "05-交接",
    "brain": "06-第二大脑",
}

# ---------- V0.3：GitHub 私有仓库同步（第二大脑云端镜像） ----------
# 也可通过 cm_github_setup 写入 ~/.cut-obsidian/config.json（0600，token 只存本地）
GITHUB_REPO = os.environ.get("CUT_OBSIDIAN_GITHUB_REPO", "")  # 如 cuohuatang/cut-obsidian-brain
GITHUB_BRANCH = os.environ.get("CUT_OBSIDIAN_GITHUB_BRANCH", "main")
_GITHUB_TOKEN_ENV = os.environ.get("CUT_OBSIDIAN_GITHUB_TOKEN", "")

CONFIG_FILE = APP_DIR / "config.json"


def load_credentials() -> dict[str, str]:
    """读取本地凭证（repo/branch/token）。token 仅存在于本地 0600 文件，绝不外泄。"""
    if CONFIG_FILE.is_file():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {"repo": GITHUB_REPO, "branch": GITHUB_BRANCH, "token": _GITHUB_TOKEN_ENV}


def save_credentials(repo: str | None = None, token: str | None = None, branch: str | None = None, **extra: str) -> dict[str, str]:
    """写入本地凭证文件（0600）。返回值永不包含 token 明文。extra 可携带 auth_mode 等扩展字段。"""
    cred = load_credentials()
    if repo:
        cred["repo"] = repo
    if token:
        cred["token"] = token
    if branch:
        cred["branch"] = branch
    cred.update(extra)
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cred, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:  # 非 POSIX 环境（如 Windows）不强制
        pass
    return {"repo": cred.get("repo", ""), "branch": cred.get("branch", "main"), "has_token": bool(cred.get("token"))}
