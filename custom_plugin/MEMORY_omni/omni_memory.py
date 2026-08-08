"""OmniMemoryOrchestrator 的文本基线移植。

插件只处理已经送入生活记忆域的标准文本；后端不依赖本模块的内部对象。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_ROLE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_NS_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_SENTENCE_RE = re.compile(r"(?<=[。！？!?；;\n])\s*|(?<=[.!?])\s+(?=[A-Z0-9\u4e00-\u9fff])")
_COLOR_WORDS = {"红色", "橙色", "黄色", "绿色", "蓝色", "紫色", "黑色", "白色", "粉色", "blue", "red", "yellow", "green", "purple", "black", "white", "pink"}
_CURRENT_MARKERS = ("现在", "目前", "如今", "改成", "改为", "更喜欢", "now", "currently", "changed to")
_PAST_MARKERS = ("以前", "过去", "曾经", "原来", "之前", "过去喜欢", "used to", "formerly", "previously")
_UNCERTAIN_MARKERS = ("可能", "也许", "好像", "不确定", "大概", "maybe", "perhaps", "not sure")
_DATE_RE = re.compile(r"(20\d{2}[./-]\d{1,2}[./-]\d{1,2})")


class InvalidMemoryScope(ValueError):
    pass


@dataclass(slots=True)
class MultimodalAtomicUnit:
    """与 Omni-SimpleMem MAU 对齐的最小文本单元。"""

    id: str
    timestamp: str
    modality_type: str
    summary: str
    raw_pointer: str
    metadata: dict[str, Any]
    schema_version: str = "companionheart.memory.mau.v1"
    status: str = "ACTIVE"
    storage_tier: str = "HOT"
    fact_key: str | None = None
    fact_state: str = "current"
    confidence: float = 0.8

    @property
    def fact_label(self) -> str:
        return {
            "current": "[现在事实]",
            "past": "[过去事实]",
            "uncertain": "[待确认事实]",
        }.get(self.fact_state, "[事实]")


def validate_scope(role_name_en: str, user_namespace: str) -> tuple[str, str]:
    if not isinstance(role_name_en, str) or not _ROLE_RE.fullmatch(role_name_en):
        raise InvalidMemoryScope("非法 role_name_en")
    if not isinstance(user_namespace, str) or not _NS_RE.fullmatch(user_namespace):
        raise InvalidMemoryScope("非法 user_namespace")
    return role_name_en, user_namespace


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_date(text: str) -> str | None:
    match = _DATE_RE.search(text or "")
    if not match:
        return None
    raw = match.group(1).replace("/", "-").replace(".", "-")
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _tokens(text: str) -> set[str]:
    # 中文按连续字符片段参与检索，英文按词参与检索；这是无模型基线。
    return {token.casefold() for token in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text)}


def _fact_analysis(text: str, context: str = "") -> dict[str, Any]:
    """提取基础事实键和值，并进行可解释的时态/歧义判断。

    这是插件内的无模型基线。后续接入上游 LLM 时仍保持本结果作为安全兜底。
    """
    key: str | None = None
    value: str | None = None
    # 日期必须来自当前事实陈述；上下文中的旧日期不能污染新版本的生效时间。
    effective_at = _extract_date(text)
    matches: list[tuple[int, str]] = []
    for match in re.finditer(r"喜欢的(?:颜色|色彩)\s*(?:是|为|：|:)\s*([^，。！？!?;；\s]+)", text, re.I):
        matches.append((match.start(), match.group(1).strip()))
    for match in re.finditer(r"(?:favorite\s+color\s+is|like)\s+([A-Za-z]+)", text, re.I):
        if match.group(1).casefold() in _COLOR_WORDS:
            matches.append((match.start(), match.group(1).strip()))
    for match in re.finditer(r"(?:我|本人)?喜欢\s*([^，。！？!?;；\s]+)", text):
        if match.group(1).casefold() in _COLOR_WORDS:
            matches.append((match.start(), match.group(1).strip()))
    if matches:
        _, value = max(matches, key=lambda item: item[0])
        key = "preference:color"

    # 事实所在文本的时态优先。上下文不会覆盖用户当前句，避免历史上下文
    # 中的“以前”误把新的明确陈述降为过去事实。
    marker_text = text.casefold()
    marker_positions: list[tuple[int, str, float]] = []
    for markers, marker_state, marker_confidence in (
        (_PAST_MARKERS, "past", 0.9),
        (_CURRENT_MARKERS, "current", 0.95),
        (_UNCERTAIN_MARKERS, "uncertain", 0.55),
    ):
        for marker in markers:
            position = marker_text.rfind(marker.casefold())
            if position >= 0:
                marker_positions.append((position, marker_state, marker_confidence))
    state, confidence = (max(marker_positions, key=lambda item: item[0])[1:]
                         if marker_positions else ("current", 0.8))
    if matches:
        fact_start = max(matches, key=lambda item: item[0])[0]
        uncertain_positions = [
            marker_text.rfind(marker.casefold())
            for marker in _UNCERTAIN_MARKERS
            if marker.casefold() in marker_text
        ]
        if uncertain_positions and max(uncertain_positions) >= max(0, fact_start - 30):
            state, confidence = "uncertain", 0.55
    return {
        "fact_key": key,
        "fact_value": value,
        "fact_state": state,
        "confidence": confidence,
        "effective_at": effective_at,
    }


class OmniMemoryOrchestrator:
    """单 namespace 的文本长期记忆编排器。

    每个实例只绑定一个 role/user 目录，避免依靠标签实现隔离。规范 JSONL 是唯一
    持久化真源，检索索引在进程内重建；因此 data_memory 中不生成插件私有数据库。
    """

    def __init__(self, data_root: Path, role_name_en: str, user_namespace: str) -> None:
        self.role_name_en, self.user_namespace = validate_scope(role_name_en, user_namespace)
        root = Path(data_root).resolve()
        self.scope_root = (root / self.role_name_en / "life" / self.user_namespace).resolve()
        if root not in self.scope_root.parents:
            raise InvalidMemoryScope("记忆路径越出固定数据根")
        self.text_dir = self.scope_root / "text"
        self.file = self.text_dir / "memories.jsonl"
        self._lock = threading.RLock()
        self._records: dict[str, MultimodalAtomicUnit] = {}
        self._idempotency: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.file.exists():
            return
        with self.file.open("r", encoding="utf-8") as stream:
            for line in stream:
                try:
                    raw = json.loads(line)
                    unit = MultimodalAtomicUnit(**raw)
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                # 兼容早期没有事实字段的 JSONL 记录；只在内存中补齐，下一次
                # 正常写入/修订时由插件统一落盘，不在后端维护迁移逻辑。
                if not unit.fact_key:
                    legacy_analysis = _fact_analysis(unit.summary)
                    if legacy_analysis["fact_key"]:
                        unit.fact_key = legacy_analysis["fact_key"]
                        unit.fact_state = legacy_analysis["fact_state"]
                        unit.confidence = legacy_analysis["confidence"]
                        unit.metadata.setdefault("fact_value", legacy_analysis["fact_value"])
                self._records[unit.id] = unit
                key = unit.metadata.get("idempotency_key")
                if key:
                    self._idempotency[str(key)] = unit.id

    def _append(self, unit: MultimodalAtomicUnit) -> None:
        self.text_dir.mkdir(parents=True, exist_ok=True)
        with self.file.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(asdict(unit), ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def add_text(
        self,
        text: str,
        *,
        source: str = "conversation",
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
        context: str = "",
    ) -> list[MultimodalAtomicUnit]:
        normalized = " ".join(str(text or "").split())
        if not normalized:
            return []
        supplied_meta = dict(metadata or {})
        if idempotency_key and idempotency_key in self._idempotency:
            existing = self._records.get(self._idempotency[idempotency_key])
            return [existing] if existing else []

        parts = [part.strip() for part in _SENTENCE_RE.split(normalized) if part.strip()]
        if not parts:
            parts = [normalized]
        created: list[MultimodalAtomicUnit] = []
        with self._lock:
            for index, part in enumerate(parts):
                key = idempotency_key if len(parts) == 1 else f"{idempotency_key}:{index}" if idempotency_key else None
                if key and key in self._idempotency:
                    continue
                digest = hashlib.sha256(f"{self.role_name_en}\0{self.user_namespace}\0{part}".encode()).hexdigest()[:24]
                unit_id = digest
                # 同一 scope 的相同规范文本直接复用已有原子单元；不同内容才生成新 ID。
                if unit_id in self._records:
                    existing = self._records[unit_id]
                    if existing.summary == part and existing.status != "DELETED":
                        if key:
                            self._idempotency[key] = existing.id
                        created.append(existing)
                        continue
                    unit_id = uuid.uuid4().hex
                unit_meta = {**supplied_meta, "source": source}
                if key:
                    unit_meta["idempotency_key"] = key
                analysis = _fact_analysis(part, context)
                fact_key = analysis["fact_key"]
                fact_state = analysis["fact_state"]
                effective_at = supplied_meta.get("effective_at") or analysis["effective_at"]
                confidence = min(
                    float(supplied_meta.get("confidence", analysis["confidence"])),
                    float(analysis["confidence"]),
                )
                conflict = None
                if fact_key and analysis["fact_value"]:
                    for candidate in self._records.values():
                        if (
                            candidate.fact_key == fact_key
                            and candidate.fact_state == "current"
                            and candidate.status == "ACTIVE"
                            and candidate.metadata.get("fact_value")
                            and candidate.metadata.get("fact_value") != analysis["fact_value"]
                        ):
                            conflict = candidate
                            break
                if conflict and fact_state == "past":
                    # 明确的历史陈述只追加历史证据，不覆盖现在事实。
                    conflict = None
                elif conflict and confidence < 0.7:
                    fact_state = "uncertain"
                elif conflict:
                    conflict.fact_state = "past"
                    conflict.status = "SUPERSEDED"
                    conflict.metadata["fact_state"] = "past"
                    conflict.metadata["valid_to"] = effective_at or _now()
                unit_meta["fact_value"] = analysis["fact_value"]
                unit_meta["fact_state"] = fact_state
                unit_meta["confidence"] = confidence
                if effective_at:
                    unit_meta["effective_at"] = effective_at
                unit_meta.setdefault("valid_from", unit_meta.get("effective_at"))
                unit = MultimodalAtomicUnit(
                    id=unit_id,
                    timestamp=_now(),
                    modality_type="text",
                    summary=part,
                    raw_pointer=f"{self.file.name}#{unit_id}",
                    metadata=unit_meta,
                    fact_key=fact_key,
                    fact_state=fact_state,
                    confidence=confidence,
                )
                self._records[unit.id] = unit
                if key:
                    self._idempotency[key] = unit.id
                if conflict:
                    self._rewrite()
                else:
                    self._append(unit)
                created.append(unit)
            if idempotency_key and created:
                # 保留调用方原始幂等键，便于整批重试直接命中。
                self._idempotency[idempotency_key] = created[0].id
        return created

    def query(
        self,
        text: str,
        *,
        top_k: int = 5,
        fact_states: tuple[str, ...] | list[str] = (),
    ) -> list[tuple[MultimodalAtomicUnit, float]]:
        query_tokens = _tokens(text)
        if not query_tokens:
            return []
        scored: list[tuple[MultimodalAtomicUnit, float]] = []
        with self._lock:
            for unit in self._records.values():
                if unit.status not in {"ACTIVE", "SUPERSEDED"}:
                    continue
                if fact_states and unit.fact_state not in set(fact_states):
                    continue
                overlap = len(query_tokens & _tokens(unit.summary))
                if overlap:
                    score = overlap / max(len(query_tokens), 1)
                    if unit.fact_state == "current":
                        score += 0.05
                    scored.append((unit, round(score, 6)))
        scored.sort(key=lambda item: (item[1], item[0].timestamp), reverse=True)
        return scored[: max(1, min(int(top_k), 50))]

    def get(self, memory_id: str) -> MultimodalAtomicUnit | None:
        return self._records.get(memory_id)

    def revise(
        self,
        memory_id: str,
        text: str,
        *,
        reason: str = "",
        idempotency_key: str | None = None,
    ) -> MultimodalAtomicUnit | None:
        normalized = " ".join(str(text or "").split())
        if not normalized:
            return None
        with self._lock:
            if idempotency_key and idempotency_key in self._idempotency:
                existing = self._records.get(self._idempotency[idempotency_key])
                return existing
            old = self._records.get(memory_id)
            if old is None:
                return None
            old.status = "SUPERSEDED"
            if old.fact_key:
                old.fact_state = "past"
                old.metadata["fact_state"] = "past"
            old.metadata["valid_to"] = _now()
            analysis = _fact_analysis(normalized, old.metadata.get("context", ""))
            fact_key = analysis["fact_key"] or old.fact_key
            fact_state = analysis["fact_state"] if analysis["fact_key"] else old.fact_state
            confidence = analysis["confidence"]
            metadata = {
                **old.metadata,
                "revision_reason": reason,
                "supersedes": memory_id,
                "fact_value": analysis["fact_value"] or old.metadata.get("fact_value"),
                "fact_state": fact_state,
                "confidence": confidence,
            }
            if analysis["effective_at"]:
                metadata["effective_at"] = analysis["effective_at"]
            replacement = MultimodalAtomicUnit(
                id=uuid.uuid4().hex[:24],
                timestamp=_now(),
                modality_type="text",
                summary=normalized,
                raw_pointer=f"{self.file.name}#{memory_id}",
                metadata=metadata,
                fact_key=fact_key,
                fact_state=fact_state,
                confidence=confidence,
            )
            self._records[replacement.id] = replacement
            if idempotency_key:
                replacement.metadata["idempotency_key"] = idempotency_key
                self._idempotency[idempotency_key] = replacement.id
            self._append(old)
            self._append(replacement)
            return replacement

    def delete(self, memory_id: str) -> bool:
        with self._lock:
            unit = self._records.get(memory_id)
            if unit is None:
                return False
            unit.status = "DELETED"
            self._rewrite()
            return True

    def delete_scope(self) -> int:
        """遗忘当前 namespace 的全部标准记忆。"""
        with self._lock:
            # receipt 统计可见 ACTIVE 记录；历史 SUPERSEDED 记录也会被写成墓碑，
            # 但不重复计入用户看到的删除数量。
            count = sum(unit.status == "ACTIVE" for unit in self._records.values())
            for unit in self._records.values():
                unit.status = "DELETED"
            if self._records:
                self._rewrite()
            return count

    def _rewrite(self) -> None:
        self.text_dir.mkdir(parents=True, exist_ok=True)
        temp = self.file.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8") as stream:
            for unit in self._records.values():
                stream.write(json.dumps(asdict(unit), ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(self.file)

    def status(self) -> dict[str, Any]:
        active = sum(unit.status == "ACTIVE" for unit in self._records.values())
        return {"records": active, "total_records": len(self._records), "data_file": str(self.file)}
