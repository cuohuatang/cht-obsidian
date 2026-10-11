"""路径与配置：全部可通过环境变量覆盖，默认纯本地、免 key。"""

from __future__ import annotations

import os
from pathlib import Path

APP_DIR = Path(os.environ.get("CUT_BICUO_ZJFLOW_HOME", Path.home() / ".cut-bicuo-zjflow"))

# vault：markdown 唯一真相源，Obsidian 可直接打开
VAULT_PATH = Path(os.environ.get("CUT_BICUO_ZJFLOW_VAULT_PATH", APP_DIR / "vault"))

# 检索索引（SQLite FTS5，可重建）
INDEX_PATH = Path(os.environ.get("CUT_BICUO_ZJFLOW_INDEX_PATH", APP_DIR / "index.sqlite"))

# vault 子目录（固定命名，Obsidian 友好）
VAULT_DIRS = {
    "memory": "01-流水账",
    "lessons": "02-踩坑本",
    "corrections": "03-纠错台账",
    "summaries": "04-经验总结",
    "handoffs": "05-交接",
}
