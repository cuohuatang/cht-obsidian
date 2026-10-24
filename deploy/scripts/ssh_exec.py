#!/usr/bin/env python3
"""轻量 SSH 执行器：凭证一律从 0600 文件读取，绝不出现在命令行或输出中。

用法：
  python3 ssh_exec.py "<远程命令>"
  IDLE_TIMEOUT=1200 python3 ssh_exec.py "<耗时命令>"   # 实时流式输出
"""
import sys, os, time

HOST = os.environ.get("QYUN_HOST", "154.12.41.33")
PORT = int(os.environ.get("QYUN_PORT", "3002"))
USER = os.environ.get("QYUN_USER", "root")
PASS_FILE = os.environ.get("QYUN_PASS_FILE", "/root/.ssh/qyun.pass")
KEY_FILE = os.environ.get("QYUN_KEY_FILE", "/root/.ssh/qyun_server_key")


def load_pass():
    if os.path.exists(PASS_FILE):
        with open(PASS_FILE) as f:
            return f.read().strip()
    return None


def connect():
    import paramiko
    pw = load_pass()

    if os.path.exists(KEY_FILE):
        try:
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(HOST, port=PORT, username=USER, key_filename=KEY_FILE,
                      look_for_keys=False, allow_agent=False, timeout=25, banner_timeout=25)
            return c
        except Exception:
            pass

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=pw,
              look_for_keys=False, allow_agent=False, timeout=25, banner_timeout=25)
    return c


def stream_run(c, cmd, idle_timeout):
    """实时输出，避免长命令被 read timeout 打断。"""
    stdin, stdout, stderr = c.exec_command(cmd, timeout=None)
    chan = stdout.channel
    chan.settimeout(0.5)
    last = time.time()
    buf = b""

    while True:
        if chan.recv_ready():
            data = chan.recv(8192)
            if not data:
                break
            buf += data
            last = time.time()
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                print(line.decode("utf-8", "replace"), flush=True)
        elif chan.recv_stderr_ready():
            data = chan.recv_stderr(8192)
            if data:
                last = time.time()
                print(data.decode("utf-8", "replace"), end="", flush=True)
        elif chan.exit_status_ready():
            while chan.recv_ready():
                buf += chan.recv(8192)
            while chan.recv_stderr_ready():
                print(chan.recv_stderr(8192).decode("utf-8", "replace"), end="", flush=True)
            break
        else:
            if idle_timeout and time.time() - last > idle_timeout:
                print(f"[超时] {idle_timeout}s 无输出，已中断", file=sys.stderr)
                chan.close()
                return -1
            time.sleep(0.2)

    if buf.strip():
        print(buf.decode("utf-8", "replace"), flush=True)
    return chan.recv_exit_status()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "echo ok"
    idle = int(os.environ.get("IDLE_TIMEOUT", "900"))
    c = connect()
    print(f"[ssh] 已连接 {USER}@{HOST}:{PORT}", flush=True)
    rc = stream_run(c, cmd, idle)
    print(f"[exit] {rc}")
    c.close()
    sys.exit(0 if rc == 0 else rc)


if __name__ == "__main__":
    main()
