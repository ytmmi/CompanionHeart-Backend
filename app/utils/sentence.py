"""增量分句器 — 把流式文本增量切分为完整句子

用于 agent/LLM 流式输出接 TTS 的句子级合成：
    每收到一个文本增量喂给 feed()，凑满完整句子立即产出；
    流结束时调用 flush() 取出残留文本。

分句规则:
    - 终止标点: 。！？；!?;… 以及换行
    - 最小句长阈值（MIN_SENTENCE_CHARS）防止"嗯。"之类碎句单独成句
    - 首句阈值（first_min_chars）可单独放小，让桌宠尽快开口
"""

from typing import Iterator, Optional

# 句子终止标点（中英文）
SENTENCE_DELIMITERS = frozenset("。！？；!?;…\n")
# 非首句最小长度：短于该长度的"句子"与后文合并
MIN_SENTENCE_CHARS = 6
# 首句最小长度：放小以降低首句 TTS 延迟（桌宠尽快开口）
FIRST_MIN_SENTENCE_CHARS = 2


class SentenceSplitter:
    """增量分句器（有状态，单流单实例）"""

    def __init__(
        self,
        min_chars: int = MIN_SENTENCE_CHARS,
        first_min_chars: int = FIRST_MIN_SENTENCE_CHARS,
    ):
        self._buffer = ""
        self._min_chars = min_chars
        self._first_min_chars = first_min_chars
        self._emitted_first = False

    def _threshold(self) -> int:
        return self._min_chars if self._emitted_first else self._first_min_chars

    def feed(self, delta: str) -> Iterator[str]:
        """喂入一个文本增量，产出所有新凑满的句子"""
        self._buffer += delta
        while True:
            sentence = self._extract_one()
            if sentence is None:
                return
            self._emitted_first = True
            yield sentence

    def _extract_one(self) -> Optional[str]:
        """从缓冲区提取一个满足长度阈值的完整句子；不满足返回 None"""
        threshold = self._threshold()
        for i, ch in enumerate(self._buffer):
            if ch not in SENTENCE_DELIMITERS:
                continue
            candidate = self._buffer[: i + 1].strip()
            # 碎句与后文合并：跳过该标点继续找下一个
            if len(candidate) < threshold:
                continue
            self._buffer = self._buffer[i + 1:]
            return candidate
        return None

    def flush(self) -> Optional[str]:
        """流结束时取出残留文本（无论长短）"""
        rest = self._buffer.strip()
        self._buffer = ""
        return rest or None
