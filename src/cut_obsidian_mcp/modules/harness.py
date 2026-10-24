"""⑩ Harness² 嫁接模块（V0.6）：把 Google Research 的 Harness² 递归优化框架接入第二大脑。

Harness²（Apache-2.0，https://github.com/google-research/harness2）是一个
"递归 Agent Harness 优化框架"：不改模型权重，通过任务级 Propose–Probe–Compose
（提出→同任务实测对比→合并）递归优化环绕模型的 8 类外壳组件（系统提示词、护栏、
记忆、工具指导、子智能体、Skills、脚本、插件）。它本体是独立 CLI，本模块把它的
6 个 CLI 入口包装成 cm_harness2_* 工具，让 Agent 在第二大脑里直接驱动外壳优化；
优化产出的"被采纳外壳 + 有证据的经验"又可经 cm_memory_save / cm_lesson_add
沉淀回第二大脑——记忆库 × 优化器闭环。

移植来源：cuohuatang/harness2 的 harness2-mcp（Apache-2.0），见
THIRD_PARTY_NOTICES.md。本模块只转发 CLI，不重新实现 Harness² 逻辑。

设计约束（继承上游，铁律）：
- 成本闸门：先 dry_run 预览，再 max_tasks=1 小跑，最后才放大；judge/report 参数必须与
  sweep 完全一致；
- 保密铁律：凭证只从环境变量 / .env 读取，禁止在输出、日志、文件中回显或外传；
- 优雅降级：CLI 缺失时返回安装指引（字符串），不抛异常打断会话；
- 输出截断：单次返回超过 MAX_OUTPUT 字符时保留尾部。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .. import __version__
from .. import config

# ---------------------------------------------------------------- 常量

# CLI 入口名 → 环境变量覆盖键（HARNESS2_CMD_<KEY> 可逐个指定可执行文件路径）
_COMMANDS = {
    "run": "harness2",
    "demo": "harness2-demo",
    "setup": "harness2-setup",
    "check": "harness2-check",
    "judge": "harness2-judge",
    "report": "harness2-report",
}

MAX_OUTPUT = 20000  # 工具返回的最大字符数，超出截断保留尾部
DEFAULT_TIMEOUT = 900  # 单次 CLI 调用默认超时（秒）；真实 sweep 很慢，按需调大

INSTALL_HINT = (
    "未在 PATH 中找到 Harness² CLI。请先安装（Linux + Python 3.12 + uv）：\n"
    "  git clone https://github.com/google-research/harness2.git\n"
    "  cd harness2 && uv venv --python 3.12 .venv && source .venv/bin/activate\n"
    "  uv pip install -e '.[render]'\n"
    "然后用 HARNESS2_CMD_<KEY> 环境变量或 PATH 让本服务能找到这些命令。\n"
    "提示：云端多用户版默认不安装 Harness²（每用户需自带模型凭证），\n"
    "完整功能请在本地以 stdio 模式运行 cht-obsidian 并使用。"
)

# 常驻指令：随 MCP instructions 送达客户端（initialize 时），每次会话都生效
STANDING_ORDERS = """\
【Harness² 常驻指令 STANDING ORDERS —— 每次会话都生效】
1. 触发时机：每完成一个用户任务后，如该任务涉及 Agent 行为、提示词、工具、
   流程或代码产出，主动运行一次优化循环，无需用户再次提醒：
   cm_harness2_doctor（确认就绪）→ cm_harness2_run（先 dry_run=true）→
   cm_harness2_run（max_tasks=1 小跑）→ cm_harness2_judge → cm_harness2_report。
2. 成本闸门：严禁跳过 dry-run 直接全量跑；严禁擅自放大 --k 或去掉
   --max-tasks；确需放大前先向用户报告预估成本并取得同意。
3. 一致性：judge/report 的 bench/subset/substrate/k/mode/seed 必须与
   run 完全一致，否则拒绝评分。
4. 故障处理：doctor/check 报告 CLI 缺失或 .env 未配置时，向用户输出安装/
   配置指引后停止重试，不要空转。
5. 闭环沉淀：每轮 report 产出后，把"被采纳的外壳改动 + 有证据的经验"用
   cm_memory_save 或 cm_lesson_add 写回第二大脑，指导下一次任务。
6. 保密铁律：所有凭证（API key、ADC、.env 内容）只从环境变量/文件读取，
   禁止在任何输出、日志、文件中回显或外传。
"""


# ---------------------------------------------------------------- CLI 包装（移植自 harness2-mcp）


def _workdir(workdir: str | None) -> str | None:
    """工具参数优先，其次 HARNESS2_CWD，最后继承服务进程目录。"""
    return workdir or os.environ.get("HARNESS2_CWD") or None


def _resolve(key: str) -> str | None:
    override = os.environ.get("HARNESS2_CMD_" + key.upper())
    if override:
        return override
    return shutil.which(_COMMANDS[key])


def _run(key: str, args: list, timeout: int, workdir: str | None) -> str:
    exe = _resolve(key)
    if not exe:
        return "[error] " + INSTALL_HINT
    cmd = [exe] + [str(a) for a in args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=_workdir(workdir),
        )
    except subprocess.TimeoutExpired:
        return (
            f"[error] 命令超过 {timeout}s 未结束：{' '.join(cmd)}\n"
            "真实 sweep 成本高且耗时长，请先用 --dry-run / --max-tasks 1 验证，"
            "或调大 timeout 参数。"
        )
    except OSError as exc:
        return f"[error] 无法执行 {exe}: {exc}"
    out = proc.stdout or ""
    if proc.stderr:
        out += ("\n" if out else "") + "--- stderr ---\n" + proc.stderr
    out = out.strip()
    if len(out) > MAX_OUTPUT:
        out = "...(输出过长已截断，保留尾部)...\n" + out[-MAX_OUTPUT:]
    return f"exit={proc.returncode}\n{out}" if out else f"exit={proc.returncode}"


def _flag(args: list, name: str, value: Any) -> None:
    """把非空参数追加为 CLI flag；None / 空串 / False 一律跳过。"""
    if value is None or value is False or value == "":
        return
    args.append(name)
    if value is not True:
        args.append(value)


# ---------------------------------------------------------------- 7 个 Harness² 工具的实现


def doctor(workdir: str | None = None) -> str:
    """环境体检：检查 Harness² 是否已安装、Python/uv 版本、.env 是否配置。"""
    lines = ["Harness² 环境体检", "=" * 40]
    for key, name in _COMMANDS.items():
        path = _resolve(key)
        lines.append(f"  {'OK ' if path else '缺失'} {name:<18} {path or ''}")
    wd = _workdir(workdir) or os.getcwd()
    lines.append(f"  工作目录: {wd}")
    py = subprocess.run(
        [sys.executable, "--version"], capture_output=True, text=True
    ).stdout.strip()
    lines.append(f"  Python: {py}（Harness² 要求 >=3.12,<3.14）")
    uv = shutil.which("uv")
    lines.append(f"  uv: {'OK ' + uv if uv else '缺失（https://docs.astral.sh/uv/）'}")
    env_file = Path(wd) / ".env"
    lines.append(f"  .env: {'存在' if env_file.is_file() else '不存在（模型基准需要，demo 不需要）'}")
    missing = [n for k, n in _COMMANDS.items() if not _resolve(k)]
    if missing:
        lines.append("\n结论：未安装或不完整。\n" + INSTALL_HINT)
    else:
        lines.append("\n结论：CLI 已就绪。可先跑 cm_harness2_demo（无需密钥）验证，再跑基准。")
    return "\n".join(lines)


def demo(output: str = "runs/demo", k: int = 2, mode: str = "both", timeout: int = DEFAULT_TIMEOUT, workdir: str | None = None) -> str:
    """运行本地演示（确定性编辑器 + 真实 Python 执行，无需任何模型密钥）。"""
    return _run("demo", ["--output", output, "--k", k, "--mode", mode], timeout, workdir)


def setup(benchmark: str, substrate: str = "oc", dry_run: bool = False, timeout: int = DEFAULT_TIMEOUT, workdir: str | None = None) -> str:
    """安装某个基准的数据与环境。benchmark: jb(JobBench) | lab(LAB) | wb(WorkBuddy-Bench)。"""
    args = [benchmark, "--substrate", substrate]
    _flag(args, "--dry-run", dry_run)
    return _run("setup", args, timeout, workdir)


def check(bench: str, subset: str | None = None, substrate: str = "oc", timeout: int = DEFAULT_TIMEOUT, workdir: str | None = None) -> str:
    """跑基准前的环境检查（judge 是否就绪、任务是否可加载）。bench: jb | lab | wb。"""
    args = ["--bench", bench]
    _flag(args, "--subset", subset)
    args += ["--substrate", substrate]
    return _run("check", args, timeout, workdir)


def run(
    bench: str,
    k: int = 1,
    mode: str = "parallel",
    substrate: str = "oc",
    subset: str | None = None,
    only_domains: str = "",
    max_tasks: int | None = None,
    split: str = "all",
    workers: int = 1,
    seed: int | None = None,
    dry_run: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    workdir: str | None = None,
) -> str:
    """执行一次递归优化 sweep（核心入口，会调用模型、产生费用）。"""
    args = ["--bench", bench, "--k", k, "--mode", mode, "--substrate", substrate]
    _flag(args, "--subset", subset)
    _flag(args, "--only-domains", only_domains)
    _flag(args, "--max-tasks", max_tasks)
    _flag(args, "--split", split)
    _flag(args, "--workers", workers)
    _flag(args, "--seed", seed)
    _flag(args, "--dry-run", dry_run)
    return _run("run", args, timeout, workdir)


def judge(
    bench: str,
    k: int = 1,
    mode: str = "parallel",
    substrate: str = "oc",
    subset: str | None = None,
    seed: int | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    workdir: str | None = None,
) -> str:
    """对已完成的 sweep 评分（judging）。参数必须与 cm_harness2_run 完全一致。"""
    args = ["--bench", bench, "--k", k, "--mode", mode, "--substrate", substrate]
    _flag(args, "--subset", subset)
    _flag(args, "--seed", seed)
    return _run("judge", args, timeout, workdir)


def report(
    bench: str,
    k: str = "1",
    mode: str = "parallel",
    substrate: str = "oc",
    subset: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    workdir: str | None = None,
) -> str:
    """汇总评分结果并生成报告。k 接受逗号列表，如 "1,2,3"（对应多次 sweep）。"""
    args = ["--bench", bench, "--k", k, "--mode", mode, "--substrate", substrate]
    _flag(args, "--subset", subset)
    return _run("report", args, timeout, workdir)


def usage_text() -> str:
    """Harness² 完整使用手册（安装 / demo / 基准 / 参数 / 成本与安全注意事项）。"""
    path = Path(__file__).resolve().parent.parent / "references" / "harness2-usage.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return "references/harness2-usage.md 缺失，请查阅 https://github.com/google-research/harness2"


# ---------------------------------------------------------------- cht-obsidian 自体检（V0.6 新增）


def self_doctor() -> dict[str, Any]:
    """cht-obsidian 自身环境一键体检：vault 可写 / config 权限 / git / 索引 / 同步配置 / 版本。

    返回分级报告 {level: ok|warn|error, checks: [{name, ok, detail}], version}。
    error = 有功能不可用；warn = 可用但有隐患；ok = 全部就绪。
    """
    checks: list[dict[str, Any]] = []

    def _add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    # 1) 版本
    _add("version", True, __version__)

    # 2) vault 目录可写
    try:
        config.VAULT_PATH.mkdir(parents=True, exist_ok=True)
        probe = config.VAULT_PATH / ".doctor-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        _add("vault_writable", True, str(config.VAULT_PATH))
    except OSError as exc:
        _add("vault_writable", False, f"{config.VAULT_PATH} 不可写：{exc}")

    # 3) config.json 存在且 0600（凭证文件）
    cfg_file = config.CONFIG_FILE
    if cfg_file.is_file():
        mode = oct(cfg_file.stat().st_mode & 0o777)
        _add("config_perm", mode == "0o600", f"{cfg_file} 权限 {mode}" + ("" if mode == "0o600" else "（应为 600）"))
    else:
        _add("config_perm", True, "尚未配置凭证文件（GitHub 同步/钥匙用时自动创建）")

    # 4) git 可用
    git_path = shutil.which("git")
    _add("git", bool(git_path), git_path or "未安装 git，GitHub 同步不可用")

    # 5) 索引文件
    idx = config.INDEX_PATH
    _add("index", idx.is_file(), f"{idx}" + ("" if idx.is_file() else "（首次保存时自动创建）"))

    # 6) GitHub 同步配置
    try:
        cred = config.load_credentials() or {}
    except Exception:  # noqa: BLE001 —— 损坏的 config 不应压垮体检
        cred = {}
    repo = (cred.get("repo") or "").strip()
    has_token = bool((cred.get("token") or "").strip())
    has_ssh = bool((cred.get("ssh_key") or "").strip())
    if repo and (has_token or has_ssh):
        _add("github_sync", True, f"{repo}（凭证：{'token' if has_token else 'ssh'}）")
    elif repo:
        _add("github_sync", False, f"已绑定仓库 {repo} 但无推送凭证（token/ssh_key 均未配置）")
    else:
        _add("github_sync", False, "未配置 GitHub 仓库（cm_github_setup 或 Web 控制台绑定）")

    # 7) Harness² CLI（可选能力）
    h2_ready = all(_resolve(k) for k in _COMMANDS)
    _add("harness2_cli", h2_ready, "6 个 CLI 就绪" if h2_ready else "未安装（可选；cm_harness2_* 工具会返回安装指引）")

    errors = [c for c in checks if not c["ok"] and c["name"] in ("vault_writable", "config_perm", "git")]
    warns = [c for c in checks if not c["ok"] and c not in errors]
    level = "error" if errors else ("warn" if warns else "ok")
    advice = []
    if not errors and warns:
        for c in warns:
            if c["name"] == "github_sync":
                advice.append("需要云端镜像：cm_github_setup(repo, token, branch) 或在 Web 控制台「出库」页绑定。")
            elif c["name"] == "harness2_cli":
                advice.append("需要外壳优化：按 INSTALL_HINT 安装 Harness² CLI（本地 stdio 模式使用最佳）。")
    return {
        "level": level,
        "version": __version__,
        "checks": checks,
        "advice": advice,
        "summary": f"{len([c for c in checks if c['ok']])}/{len(checks)} 项就绪",
    }
