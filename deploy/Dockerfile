# cht-obsidian（第二大脑 MCP）Docker 镜像
# 上游仓库：https://github.com/cuohuatang/cht-obsidian  V0.3（26 个 cm_* 工具）
FROM python:3.11-slim

# git 是硬依赖：V0.3 的 cm_github_push/pull 通过 subprocess 调系统 git。
# openssh-client 用于容器内用 SSH key 免 token 访问私有仓库。
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates openssh-client curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 源码随构建上下文提供（repo/），避免构建时依赖 GitHub 网络波动。
# 更新版本：本地 git pull 后重新执行部署脚本即可。
COPY repo/ /app/repo/

# 该服务器到 pypi.org 直连超时，改用清华镜像；--extra-index-url 兜底。
RUN pip install --no-cache-dir \
      -i https://pypi.tuna.tsinghua.edu.cn/simple \
      --extra-index-url https://mirrors.aliyun.com/pypi/simple \
      --trusted-host pypi.tuna.tsinghua.edu.cn --trusted-host mirrors.aliyun.com \
      /app/repo \
 && pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple uvicorn \
 && rm -rf /root/.cache/pip

# 启动器 + 配置中心 UI：支持 stdio / sse / streamable-http，并可开启 Bearer Token 鉴权
COPY http_server.py setup_ui.html /app/

# 数据与索引放 /data，需挂载宿主机目录持久化
ENV CUT_OBSIDIAN_HOME=/data/cut-obsidian \
    CUT_OBSIDIAN_VAULT_PATH=/data/cut-obsidian/vault \
    CUT_OBSIDIAN_INDEX_PATH=/data/cut-obsidian/index.sqlite \
    MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

# git 兜底身份（容器内 commit 需要；也可进容器自行改成你的邮箱）
RUN git config --global --add safe.directory '*' \
 && git config --global init.defaultBranch main \
 && git config --global user.email "cht-obsidian@local" \
 && git config --global user.name "cht-obsidian"

VOLUME ["/data"]
EXPOSE 8000

# 健康检查：HTTP 模式（sse / streamable-http）探测端口监听是否存活
# （SSE 端点是长连接流式响应，TCP 探测比 HTTP GET 更可靠）；stdio 模式跳过
HEALTHCHECK --interval=60s --timeout=10s --start-period=25s --retries=3 \
  CMD python -c "import os,socket,sys; \
sys.exit(0) if os.environ.get('MCP_TRANSPORT','stdio')=='stdio' else \
socket.create_connection(('127.0.0.1', int(os.environ.get('MCP_PORT','8000'))), timeout=5).close()" \
  || exit 1

CMD ["python", "/app/http_server.py"]
