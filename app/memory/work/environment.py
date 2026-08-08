"""不读取环境变量的工作环境白名单采集器。"""

from __future__ import annotations

import locale
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable

from .long_term import LongTermWorkMemoryStore
from .models import WorkMemoryKind, WorkMemoryRecord


@dataclass(frozen=True, slots=True)
class EnvironmentFact:
    key: str
    value: str


CommandRunner = Callable[[list[str]], str | None]


def _run_version(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = (result.stdout or result.stderr).strip().splitlines()
    if result.returncode != 0 or not output:
        return None
    return output[0][:256]


class WorkEnvironmentCollector:
    """只采集明确白名单事实；绝不读取 os.environ。"""

    TOOL_COMMANDS = {
        "tool.git.version": ["git", "--version"],
        "tool.node.version": ["node", "--version"],
        "tool.pnpm.version": ["pnpm", "--version"],
    }

    def __init__(self, *, command_runner: CommandRunner = _run_version) -> None:
        self.command_runner = command_runner

    def collect(self) -> list[EnvironmentFact]:
        language, encoding = locale.getlocale()
        facts = [
            EnvironmentFact("system.os", platform.system() or "unknown"),
            EnvironmentFact("system.os_release", platform.release() or "unknown"),
            EnvironmentFact("system.architecture", platform.machine() or "unknown"),
            EnvironmentFact("runtime.python.version", platform.python_version()),
            EnvironmentFact("runtime.python.implementation", platform.python_implementation()),
            EnvironmentFact("runtime.python.major_minor", f"{sys.version_info.major}.{sys.version_info.minor}"),
            EnvironmentFact("locale.language", language or "unknown"),
            EnvironmentFact("locale.encoding", encoding or "unknown"),
            EnvironmentFact("locale.timezone", time.tzname[0] if time.tzname else "unknown"),
        ]
        for key, command in self.TOOL_COMMANDS.items():
            value = self.command_runner(list(command))
            facts.append(EnvironmentFact(key, value or "unavailable"))
        return facts

    def store(
        self,
        memory: LongTermWorkMemoryStore,
        *,
        capture_id: str,
    ) -> list[WorkMemoryRecord]:
        return [
            memory.upsert(
                WorkMemoryKind.ENVIRONMENT_FACT,
                fact.key,
                fact.value,
                source="environment_probe",
                confidence=1.0,
                idempotency_key=f"environment:{capture_id}:{fact.key}",
            )
            for fact in self.collect()
        ]
