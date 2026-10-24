#!/usr/bin/env bash
# cht-obsidian 一键部署脚本（在目标服务器上执行）
#   chmod +x deploy.sh && ./deploy.sh
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/cht-obsidian}"
COMPOSE=""

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
err() { printf '\n\033[1;31m[错误] %s\033[0m\n' "$*" >&2; }

# ---------- 1. Docker ----------
log "检查 Docker"
if command -v docker >/dev/null 2>&1; then
  echo "已安装: $(docker --version)"
else
  echo "未安装，开始安装..."
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg
    install -m0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    . /etc/os-release
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable --now docker
  else
    err "非 Debian 系系统，请自行安装 Docker 后重跑本脚本"; exit 1
  fi
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  err "找不到 docker compose"; exit 1
fi
echo "compose: ${COMPOSE}"

# ---------- 2. 准备目录与配置 ----------
log "准备部署目录 ${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
# 把本脚本旁边的部署文件拷过去（若脚本就在该目录则跳过）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "${SCRIPT_DIR}" != "${INSTALL_DIR}" ]; then
  cp -f "${SCRIPT_DIR}/Dockerfile" "${SCRIPT_DIR}/http_server.py" \
        "${SCRIPT_DIR}/docker-compose.yml" "${INSTALL_DIR}/"
  [ -f "${SCRIPT_DIR}/.env" ] && cp -f "${SCRIPT_DIR}/.env" "${INSTALL_DIR}/" || true
fi
cd "${INSTALL_DIR}"

if [ ! -f .env ]; then
  cp -f "${SCRIPT_DIR}/.env.example" .env 2>/dev/null || true
  echo "已生成 .env（请按需填写 GitHub 同步配置）"
fi
mkdir -p data
chmod 700 data

# ---------- 3. 构建并启动 ----------
log "构建镜像并启动容器"
$COMPOSE up -d --build

# ---------- 4. 验证 ----------
log "等待服务就绪"
for i in $(seq 1 30); do
  if curl -fsS -m 3 -o /dev/null http://127.0.0.1:8000/mcp 2>/dev/null; then
    echo "HTTP 端点已响应"; break
  fi
  # streamable-http 对裸 GET 可能返回非 2xx，退化为端口探测
  if (echo > /dev/tcp/127.0.0.1/8000) 2>/dev/null; then
    echo "端口 8000 已监听"; break
  fi
  sleep 2
  [ "$i" = 30 ] && { err "服务未就绪，查看日志: cd ${INSTALL_DIR} && $COMPOSE logs -f"; exit 1; }
done

log "运行状态"
$COMPOSE ps
echo
echo "容器日志（最近 15 行）:"
$COMPOSE logs --tail 15

cat <<EOF

------------------------------------------------------------------
部署完成。

  数据目录: ${INSTALL_DIR}/data   （vault markdown + 索引，务必定期备份）
  本机端点: http://127.0.0.1:8000/mcp
  公网访问: 默认未开放（安全）。需要时用 SSH 隧道：
            ssh -L 8000:127.0.0.1:8000 用户名@服务器IP
            然后本机连 http://127.0.0.1:8000/mcp

  停止: cd ${INSTALL_DIR} && $COMPOSE down
  重启: cd ${INSTALL_DIR} && $COMPOSE restart
  日志: cd ${INSTALL_DIR} && $COMPOSE logs -f
------------------------------------------------------------------
EOF
