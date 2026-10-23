"""⑤ Obsidian 桥梁模块（obsidian-mcp 式）：直接文件系统读写 vault。"""

from __future__ import annotations

from typing import Any

from ..config import VAULT_PATH
from ..storage import vault


def vault_init(path: str | None = None) -> dict[str, Any]:
    """初始化 vault 目录结构与索引（幂等）。"""
    return vault.init_vault(path)


def read(path: str) -> dict[str, Any]:
    """读取 vault 内 markdown（含 frontmatter 解析）。"""
    return vault.read_note(path)


def write(path: str, content: str, overwrite: bool = False) -> dict[str, Any]:
    """写入 vault 内 markdown（默认不覆盖，安全）。"""
    return vault.write_note(path, content, {"title": path.rsplit("/", 1)[-1].removesuffix(".md")}, overwrite=overwrite)


def vault_root() -> str:
    return str(VAULT_PATH)
