# cht-obsidian 云端部署（已完成）

**状态：✅ 部署成功并已通过公网验证**

| 项 | 值 |
|---|---|
| 服务器 | 154.12.41.33（美国轻松云，SSH 端口 **3002**） |
| 部署目录 | `/opt/cht-obsidian` |
| 版本 | cht-obsidian V0.3（26 个 `cm_*` 工具） |
| 运行方式 | Docker（容器名 `cht-obsidian`，`restart: unless-stopped`） |
| 传输协议 | **SSE**（`http://154.12.41.33:8899/sse`） |
| 鉴权 | Bearer Token（已强制开启，未带 token 返回 401） |
| 数据持久化 | `/opt/cht-obsidian/data`（vault + index.sqlite） |
| 时区 | Asia/Shanghai |

---

## 一、客户端（Agent）连接配置

MCP 客户端里加一个 SSE 服务器：

```json
{
  "mcpServers": {
    "cht-obsidian": {
      "type": "sse",
      "url": "http://154.12.41.33:8899/sse",
      "headers": {
        "Authorization": "Bearer <你的token>"
      }
    }
  }
}
```

**token 在哪**：服务器 `/opt/cht-obsidian/.env`（权限 600）里 `MCP_AUTH_TOKEN=` 后面的值。
查看命令：`ssh -p 3002 root@154.12.41.33 "grep MCP_AUTH_TOKEN /opt/cht-obsidian/.env"`
（本地沙箱副本在 `/workspace/cht-obsidian-deploy/.deploy-token`）

## 二、日常运维（SSH 端口 3002）

```bash
ssh -p 3002 root@154.12.41.33

docker logs -f cht-obsidian          # 看日志
docker restart cht-obsidian          # 重启
cd /opt/cht-obsidian && docker compose down   # 停止
cd /opt/cht-obsidian && docker compose up -d  # 启动
ls /opt/cht-obsidian/data/cut-obsidian/vault/ # 看笔记数据
```

数据备份 = 打包 `/opt/cht-obsidian/data` 一个目录即可。

## 三、更新版本

1. 本地更新源码（`git pull` 上游仓库）
2. 重新执行 `python3 scripts/upload.py` 上传
3. 服务器上 `cd /opt/cht-obsidian && docker build -t cht-obsidian:0.3.0 . && docker compose up -d --force-recreate`

## 四、部署中踩掉的坑（备查）

| 坑 | 现象 | 已怎么解决 |
|---|---|---|
| 上游硬编码 stdio | `mcp.run(transport="stdio")` 无法远程调用 | 自写 `http_server.py` 启动器，不改上游代码 |
| 服务器连不上 pypi.org | 直连超时 | pip 改用清华/阿里镜像源 |
| **DNS rebinding 防护** | 公网 IP 访问返回 `421 Invalid Host header` | 启动器传入 `TransportSecuritySettings(enable_dns_rebinding_protection=False)`（有 Bearer 兜底） |
| MCP HTTP 无鉴权 | 裸奔公网任何人可读写 | 启动器内置 Bearer 校验中间件 |
| 22 端口握手被重置 | SSH 连不上 | 该机 SSH 实际端口是 **3002** |

## 五、安全须知

- token 已明文出现在本对话/日志中的**服务器密码**，建议在云平台控制台改掉
- `8899` 端口走的是明文 HTTP，token 会被链路中间看到；介意的话可后续加 Caddy 反代上 HTTPS
- `.env` 与数据目录都在 `/opt/cht-obsidian`，勿放 web 可访问路径
