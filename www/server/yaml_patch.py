"""
保留注释的 YAML 标量写入器

背景：原实现用 yaml.safe_load → dict → yaml.dump 往返写配置，
会把 config.yaml 里的所有注释、空行、缩进风格全部抹掉
（app/configs/llm/config.yaml 的注释已经这样丢失过一次）。

本模块不做往返：只按行定位目标标量所在的那一行，
原地替换 ": " 之后的值，其余字节原样保留。
因此注释、空行、引号风格、行内注释全部不受影响。

只支持标量赋值（str / int / float / bool / None）——
这正是设置界面需要的全部能力；新增 key、删除 key、改列表不在范围内。
多行值（含换行符）返回 False 让调用方走 _rebuild_write（yaml.dump 正确处理多行串）。
"""
from __future__ import annotations

import re
from pathlib import Path

# 行首缩进 + key + 冒号，捕获缩进与 key
_KEY_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<key>[^\s#:][^:]*?)\s*:(?P<rest>.*)$")


def _strip_quotes(key: str) -> str:
    """YAML key 可能被引号包裹，比较时统一去掉"""
    k = key.strip()
    if len(k) >= 2 and k[0] == k[-1] and k[0] in "\"'":
        return k[1:-1]
    return k


def _split_inline_comment(rest: str) -> tuple[str, str]:
    """
    把 `: ` 之后的部分拆成 (值, 行尾注释)。

    需要感知引号，否则 `api_key: "sk-a#b"` 会被 `#` 切断。
    只有前面是空白的 `#` 才算注释起点（YAML 规则）。
    """
    in_single = in_double = False
    for i, ch in enumerate(rest):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if i == 0 or rest[i - 1] in " \t":
                return rest[:i], rest[i:]
    return rest, ""


def _format_scalar(value, old_value: str) -> str:
    """
    把 Python 值格式化成 YAML 标量，尽量沿用该行原有的引号风格。

    old_value 是这一行原来的值（已去掉行尾注释），用来判断原本有没有加引号。
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)

    s = str(value)
    old = old_value.strip()
    was_quoted = len(old) >= 2 and old[0] == old[-1] and old[0] in "\"'"

    # 这些情况必须加引号，否则重新解析会变成别的类型或语法错误
    must_quote = (
        s == ""
        or s.strip() != s
        or s[0] in "#&*!|>%@`{}[],\"'"
        or ":" in s
        or s.lower() in ("true", "false", "null", "yes", "no", "on", "off", "~")
        or _looks_numeric(s)
    )

    if must_quote or was_quoted:
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return s


def _looks_numeric(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def set_scalar(path: Path, dotted_key: str, value) -> bool:
    """
    就地修改 path 中 dotted_key 对应的标量值，保留全部注释与格式。

    dotted_key 形如 "openai.default_params.temperature"（不含模块前缀）。
    返回 True 表示改写成功；False 表示没找到这个 key（调用方应回退到重建写入）。

    注意：多行值（含换行符）直接返回 False，由调用方走 yaml.dump 路径。
    """
    if not path.exists():
        return False

    # 多行值无法用单行替换表达，退回重建写入
    if isinstance(value, str) and "\n" in value:
        return False

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    parts = dotted_key.split(".")

    # 逐层下钻：找到每一层 key 所在行，并把搜索范围收缩到它的子块内
    start, end = 0, len(lines)
    parent_indent = -1
    target_line = -1

    for depth, part in enumerate(parts):
        found = -1
        block_indent = None

        for i in range(start, end):
            raw = lines[i]
            stripped = raw.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("-"):
                continue

            m = _KEY_RE.match(raw.rstrip("\n"))
            if not m:
                continue

            indent = len(m.group("indent").expandtabs(4))
            if indent <= parent_indent:
                # 已经退回到父级或更外层，说明当前块结束了
                break
            if block_indent is None:
                block_indent = indent
            if indent != block_indent:
                continue  # 更深层级的 key，跳过

            if _strip_quotes(m.group("key")) == part:
                found = i
                break

        if found < 0:
            return False

        if depth == len(parts) - 1:
            target_line = found
            break

        # 不是最后一层：把范围收缩到这个 key 的子块
        m = _KEY_RE.match(lines[found].rstrip("\n"))
        parent_indent = len(m.group("indent").expandtabs(4))
        start = found + 1
        # 子块在下一个同级或更外层 key 处结束
        new_end = end
        for j in range(found + 1, end):
            raw = lines[j]
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            m2 = _KEY_RE.match(raw.rstrip("\n"))
            if m2 and len(m2.group("indent").expandtabs(4)) <= parent_indent:
                new_end = j
                break
        end = new_end

    if target_line < 0:
        return False

    raw = lines[target_line]
    newline = "\n" if raw.endswith("\n") else ""
    m = _KEY_RE.match(raw.rstrip("\n"))
    old_val, comment = _split_inline_comment(m.group("rest"))

    # 目标行下面还有缩进更深的内容 → 这是个映射节点，不是标量，拒绝改写
    if old_val.strip() == "":
        node_indent = len(m.group("indent").expandtabs(4))
        for j in range(target_line + 1, len(lines)):
            s = lines[j].strip()
            if not s or s.startswith("#"):
                continue
            child = _KEY_RE.match(lines[j].rstrip("\n"))
            child_indent = len(child.group("indent").expandtabs(4)) if child else node_indent
            if child_indent > node_indent:
                return False
            break

    new_val = _format_scalar(value, old_val)
    key_part = raw[: raw.index(":", len(m.group("indent"))) + 1]

    if new_val:
        rebuilt = f"{key_part} {new_val}"
    else:
        rebuilt = f"{key_part}"

    if comment:
        rebuilt = f"{rebuilt} {comment.lstrip()}" if new_val else f"{rebuilt} {comment.lstrip()}"

    lines[target_line] = rebuilt + newline
    path.write_text("".join(lines), encoding="utf-8")
    return True
