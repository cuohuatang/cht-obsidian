#!/usr/bin/env bash
# Harness² 环境一键体检：检查 CLI、Python 版本、uv、.env
# 用法：bash harness2_doctor.sh [harness2 仓库目录，默认当前目录]
# 来源：cuohuatang/harness2（Apache-2.0），随 cht-obsidian 分发
set -u
WD="${1:-$PWD}"
cd "$WD" 2>/dev/null || { echo "[error] 无法进入目录: $WD"; exit 1; }

echo "Harness² 环境体检（目录: $WD）"
echo "========================================"

CMDS="harness2 harness2-demo harness2-setup harness2-check harness2-judge harness2-report"
MISSING=0
for c in $CMDS; do
  if p=$(command -v "$c"); then
    echo "  OK    $c -> $p"
  else
    echo "  缺失  $c"
    MISSING=1
  fi
done

PY=$(python3 --version 2>&1)
echo "  Python: $PY（要求 >=3.12,<3.14）"
case "$PY" in
  *" 3.1"[23]*) : ;;
  *) echo "  [warn] Python 版本可能不满足 Harness² 要求" ;;
esac

if command -v uv >/dev/null; then echo "  OK    uv -> $(command -v uv)";
else echo "  缺失  uv（https://docs.astral.sh/uv/）"; MISSING=1; fi

if [ -f .env ]; then echo "  .env: 存在";
else echo "  .env: 不存在（模型基准需要；demo 不需要）"; fi

if [ -d runs ]; then echo "  runs/: 存在（$(find runs -maxdepth 1 -mindepth 1 | wc -l) 个条目）"; fi

echo "========================================"
if [ "$MISSING" = "1" ]; then
  cat <<'EOF'
结论：未安装或不完整。安装步骤：
  git clone https://github.com/google-research/harness2.git
  cd harness2
  uv venv --python 3.12 .venv && source .venv/bin/activate
  uv pip install -e '.[render]'
  harness2-demo --output runs/demo --k 2   # 免密钥验证
EOF
  exit 1
fi
echo "结论：CLI 已就绪。建议先 harness2-demo 验证，再 harness2-setup <jb|lab|wb> 安装基准。"
