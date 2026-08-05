"""从 Git 或本地目录安装插件。

安装流程在后台线程里跑，通过 job 日志推给前端：
克隆/复制 → 校验 plugin.yaml → 端口段提示 → pip install → 收尾。
任一步失败都回滚（删除已落盘的插件目录）。
"""
from __future__ import annotations

import re
import shutil
import sys
import threading
from pathlib import Path

from .jobs import job_done, job_log, job_new, stream_subprocess
from .paths import PLUGIN_ROOT, PORT_BANDS
from .yaml_io import dig, read_yaml

_GIT_URL_RE = re.compile(r"^(https?://|git@)[\w.@:/\-~]+$")


def install_plugin(body: dict) -> dict:
    """从 Git 或本地目录安装，返回 job_id 供前端轮询"""
    source = body.get("source")  # "git" | "local"
    if source == "git":
        url = (body.get("url") or "").strip()
        branch = (body.get("branch") or "main").strip() or "main"
        name = (body.get("name") or "").strip()
        if not _GIT_URL_RE.match(url):
            return {"ok": False, "error": "Git 地址格式不合法（需 http(s):// 或 git@ 开头）"}
        jid = job_new("install", name or url)
        threading.Thread(target=_install_git, args=(jid, url, branch, name),
                         daemon=True).start()
        return {"ok": True, "job": jid}
    if source == "local":
        path = (body.get("path") or "").strip()
        if not path:
            return {"ok": False, "error": "未填写本地目录"}
        jid = job_new("install", path)
        threading.Thread(target=_install_local, args=(jid, path), daemon=True).start()
        return {"ok": True, "job": jid}
    return {"ok": False, "error": f"未知安装来源：{source}"}


def _install_git(jid: str, url: str, branch: str, name: str) -> None:
    if not name:
        tail = url.rstrip("/").split("/")[-1]
        name = tail[:-4] if tail.endswith(".git") else tail
    dest = PLUGIN_ROOT / name
    if dest.exists():
        job_log(jid, f"[中止] 插件目录已存在：{name}（先卸载或换名）")
        job_done(jid, False, "目录已存在")
        return
    job_log(jid, f"[克隆] {url} (branch={branch}) → custom_plugin/{name}")
    PLUGIN_ROOT.mkdir(parents=True, exist_ok=True)
    rc = stream_subprocess(jid, ["git", "clone", "--depth", "1", "-b", branch, url, str(dest)])
    if rc != 0:
        job_log(jid, f"[中止] git clone 失败（退出码 {rc}）")
        shutil.rmtree(dest, ignore_errors=True)
        job_done(jid, False, "git clone 失败")
        return
    _finish_install(jid, dest)


def _install_local(jid: str, path: str) -> None:
    src = Path(path).expanduser()
    if not src.exists() or not src.is_dir():
        job_log(jid, f"[中止] 本地目录不存在：{src}")
        job_done(jid, False, "目录不存在")
        return
    if not (src / "plugin.yaml").exists():
        job_log(jid, f"[中止] {src} 下没有 plugin.yaml")
        job_done(jid, False, "缺少 plugin.yaml")
        return
    dest = PLUGIN_ROOT / src.name
    if dest.exists():
        job_log(jid, f"[中止] 插件目录已存在：{src.name}")
        job_done(jid, False, "目录已存在")
        return
    try:
        if src.resolve() == dest.resolve():
            raise ValueError("源目录就是目标目录")
        job_log(jid, f"[复制] {src} → custom_plugin/{src.name}")
        shutil.copytree(src, dest)
    except Exception as e:
        job_log(jid, f"[中止] 复制失败：{e}")
        job_done(jid, False, str(e))
        return
    _finish_install(jid, dest)


def _finish_install(jid: str, dest: Path) -> None:
    """安装收尾：校验 plugin.yaml、装依赖、端口段提示"""
    manifest = dest / "plugin.yaml"
    if not manifest.exists():
        job_log(jid, "[中止] 目录里没有 plugin.yaml，不是有效插件，已回滚")
        shutil.rmtree(dest, ignore_errors=True)
        job_done(jid, False, "缺少 plugin.yaml")
        return

    meta = read_yaml(manifest)
    ptype, port = meta.get("type", ""), dig(meta, "service.port")
    job_log(jid, f"[插件] {meta.get('name')} v{meta.get('version')} type={ptype} port={port}")

    if ptype in PORT_BANDS and isinstance(port, int):
        lo, hi = PORT_BANDS[ptype]
        if not (lo <= port <= hi):
            job_log(jid, f"[警告] 端口 {port} 不在 {ptype} 约定段 {lo}-{hi}，可能与其他模块冲突")

    reqs = dest / "requirements.txt"
    if reqs.exists():
        job_log(jid, f"[依赖] 安装 {reqs.name} 到项目 venv（{sys.executable}）")
        rc = stream_subprocess(jid, [sys.executable, "-m", "pip", "install", "-r", str(reqs)])
        if rc != 0:
            job_log(jid, f"[中止] 依赖安装失败（pip 退出码 {rc}），已回滚插件目录")
            shutil.rmtree(dest, ignore_errors=True)
            job_done(jid, False, "依赖安装失败")
            return
    else:
        job_log(jid, "[依赖] 无 requirements.txt")
        node_deps = meta.get("dependencies", [])
        if meta.get("type") == "agent" or (meta.get("service", {}).get("command") or [""])[0] == "node":
            job_log(jid, f"[提示] 这是 Node 插件，需手动在插件目录执行 npm/bun 安装：{node_deps}")

    job_log(jid, "[完成] 插件已安装。如需随后端自启，去对应模块把 mode/enabled 指向它。")
    job_done(jid, True, f"{meta.get('name')} 安装成功")
