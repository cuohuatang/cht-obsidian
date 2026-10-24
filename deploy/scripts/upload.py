#!/usr/bin/env python3
"""把本地部署包 + 上游源码通过 SFTP 推到目标服务器。"""
import os, sys, tarfile, io, stat

HOST = os.environ.get("QYUN_HOST", "154.12.41.33")
PORT = int(os.environ.get("QYUN_PORT", "3002"))
USER = os.environ.get("QYUN_USER", "root")
PASS_FILE = os.environ.get("QYUN_PASS_FILE", "/root/.ssh/qyun.pass")
KEY_FILE = os.environ.get("QYUN_KEY_FILE", "/root/.ssh/qyun_server_key")
REMOTE_DIR = os.environ.get("REMOTE_DIR", "/opt/cht-obsidian")
LOCAL_DEPLOY = "/workspace/cht-obsidian-deploy"
LOCAL_REPO = "/tmp/cht-obsidian-src"

import paramiko

def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    pw = open(PASS_FILE).read().strip() if os.path.exists(PASS_FILE) else None
    try:
        if os.path.exists(KEY_FILE):
            c.connect(HOST, port=PORT, username=USER, key_filename=KEY_FILE,
                      look_for_keys=False, allow_agent=False, timeout=25, banner_timeout=25)
            return c
    except Exception:
        pass
    c.connect(HOST, port=PORT, username=USER, password=pw,
              look_for_keys=False, allow_agent=False, timeout=25, banner_timeout=25)
    return c

def main():
    if not os.path.isdir(LOCAL_REPO):
        print("[错误] 本地源码缺失:", LOCAL_REPO); sys.exit(1)
    c = connect()
    sftp = c.open_sftp()

    def mkdirs(p):
        parts, cur = p.split("/"), ""
        for part in parts:
            if not part: continue
            cur += "/" + part
            try: sftp.stat(cur)
            except IOError: sftp.mkdir(cur)

    mkdirs(REMOTE_DIR)
    mkdirs(REMOTE_DIR + "/repo")

    # 1) 上传部署文件
    for name in ("Dockerfile", "http_server.py", "docker-compose.yml", "setup_ui.html"):
        local = os.path.join(LOCAL_DEPLOY, name)
        if os.path.exists(local):
            sftp.put(local, REMOTE_DIR + "/" + name)
            print("[上传]", name)

    # 2) 上传源码（排除 .git / __pycache__）
    def put_tree(local_dir, remote_dir):
        n = 0
        for root, dirs, files in os.walk(local_dir):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", ".pytest_cache", "node_modules")]
            rel = os.path.relpath(root, local_dir)
            target = remote_dir if rel == "." else remote_dir + "/" + rel.replace(os.sep, "/")
            mkdirs(target)
            for f in files:
                if f.endswith((".pyc", ".pyo")): continue
                sftp.put(os.path.join(root, f), target + "/" + f)
                n += 1
        return n

    cnt = put_tree(LOCAL_REPO, REMOTE_DIR + "/repo")
    print(f"[上传] repo/ 共 {cnt} 个文件")

    # 3) 生成 .env（含随机 token），权限 600；已存在则保留原 token（不轮换）
    try:
        with sftp.open(REMOTE_DIR + "/.env") as f:
            existing = f.read().decode()
    except IOError:
        existing = None
    if existing and "MCP_AUTH_TOKEN=" in existing:
        # 远端已有 .env：完整沿用（token、transport 等用户配置都不动）
        print("[保留] 远端已有 .env，全部沿用不覆盖")
        token = [l for l in existing.splitlines() if l.startswith("MCP_AUTH_TOKEN=")][0].split("=", 1)[1]
    else:
        token = os.urandom(24).hex()
        env = (
            "HOST_MCP_PORT=8899\n"
            "MCP_TRANSPORT=streamable-http\n"
            f"MCP_AUTH_TOKEN={token}\n"
            "TZ=Asia/Shanghai\n"
            "CUT_OBSIDIAN_GITHUB_REPO=\n"
            "CUT_OBSIDIAN_GITHUB_BRANCH=main\n"
            "CUT_OBSIDIAN_GITHUB_TOKEN=\n"
        )
        remote_env = REMOTE_DIR + "/.env"
        with sftp.open(remote_env, "w") as f:
            f.write(env)
        sftp.chmod(remote_env, 0o600)
    open("/workspace/cht-obsidian-deploy/.deploy-token", "w").write(token)
    os.chmod("/workspace/cht-obsidian-deploy/.deploy-token", 0o600)
    print("[生成] .env (0600)，访问令牌已保存到本地 .deploy-token")

    sftp.close(); c.close()
    print("[完成] 全部文件上传至", REMOTE_DIR)

if __name__ == "__main__":
    main()
