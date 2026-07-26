"""sidecar 事件常量与归一化

与 custom_plugin/AGENT_pi/src/types.ts 的 StreamLine 类型对齐。
所有 sidecar 事件字面量集中在此，防止版本漂移时散落各处。
"""

# ── NDJSON 行类型（sidecar → 后端） ──
EVENT_DELTA = "delta"
EVENT_THINKING = "thinking"
EVENT_TOOL = "tool"
EVENT_DONE = "done"
EVENT_ERROR = "error"

KNOWN_EVENTS = {EVENT_DELTA, EVENT_THINKING, EVENT_TOOL, EVENT_DONE, EVENT_ERROR}

# ── 工具事件 phase ──
TOOL_PHASE_START = "start"
TOOL_PHASE_END = "end"


def normalize_event(line: dict) -> dict:
    """
    归一化 sidecar 事件行（当前直接透传，未知类型标记）。

    保留此函数作为版本兼容层：sidecar 事件结构变化时只改这里。
    """
    if line.get("type") not in KNOWN_EVENTS:
        return {"type": "unknown", "raw": line}
    return line
