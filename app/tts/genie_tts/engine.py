"""Genie-TTS 语音合成引擎（本地 ONNX 推理）

基于 GPT-SoVITS 的轻量推理引擎 Genie-TTS，使用 ONNX 进行 CPU 推理。
支持语音克隆（参考音频）和多角色管理。

支持流式推理: 使用 genie_tts.tts_async 逐 chunk 实时产生音频数据。

依赖:
    pip install genie-tts

使用前需设置环境变量:
    $env:GENIE_DATA_DIR = "path/to/GenieData"

文档:
    https://github.com/High-Logic/Genie-TTS
    tests/参考文档/API Server Tutorial.py  — API 接口参考
"""

import os
from pathlib import Path
from typing import AsyncIterator, Optional

from ..base import TTSBase


class GenieTTS(TTSBase):
    """Genie-TTS 语音合成引擎（本地 ONNX 推理）"""

    def __init__(
        self,
        data_dir: str = "",
        model_base_dir: str = "",
        output_dir: Optional[Path] = None,
        characters: Optional[dict[str, dict]] = None,
        default_params: Optional[dict] = None,
    ):
        """
        初始化 Genie-TTS 引擎。

        Args:
            data_dir: GenieData 目录路径（绝对或相对路径）。
            model_base_dir: 模型根目录。
            output_dir: 音频输出目录。
            characters: 角色配置字典。
            default_params: 默认合成参数。
        """
        # ── 路径解析：相对路径基于项目根目录（app/ 所在目录） ──
        _project_root = Path(__file__).parents[3].resolve()

        if data_dir:
            p = Path(data_dir)
            if not p.is_absolute():
                p = _project_root / p
            resolved = str(p.resolve())
            os.environ["GENIE_DATA_DIR"] = resolved
            self._data_dir = p.resolve()
        else:
            self._data_dir = None

        if model_base_dir:
            p = Path(model_base_dir)
            if not p.is_absolute():
                p = _project_root / p
            self._model_base_dir = p.resolve()
        else:
            self._model_base_dir = None

        self._output_dir = Path(output_dir) if output_dir else None
        self._characters = characters or {}
        self._default_params = default_params or {
            "split_sentence": False,
            "play": False,
        }

        # 延迟导入（引擎实例化时才导入 genie_tts）
        self._genie = None

    # ── 属性 ──

    @property
    def data_dir(self) -> Optional[Path]:
        return self._data_dir

    @property
    def model_base_dir(self) -> Optional[Path]:
        return self._model_base_dir

    @property
    def characters(self) -> dict[str, dict]:
        """获取当前支持的角色列表"""
        return dict(self._characters)

    # ── 内部方法 ──

    def _ensure_import(self):
        """确保 genie_tts 已导入"""
        if self._genie is None:
            import genie_tts as genie
            self._genie = genie

    def _resolve_model_path(self, character_name: str) -> Path:
        """解析角色的模型路径（指向 tts_models 子目录）"""
        if self._model_base_dir:
            return self._model_base_dir / character_name / "tts_models"
        return Path(character_name) / "tts_models" if character_name else Path(character_name)

    def _resolve_prompt_wav_path(self, character_name: str, prompt_wav: str) -> Path:
        """解析角色的参考音频路径"""
        if self._model_base_dir:
            return self._model_base_dir / character_name / "prompt_wav" / prompt_wav
        return Path(character_name) / "prompt_wav" / prompt_wav if character_name else Path(prompt_wav)

    # ── 核心方法 ──

    async def synthesize(
        self,
        text: str,
        output_path: Optional[Path] = None,
        *,
        character_name: Optional[str] = None,
        split_sentence: Optional[bool] = None,
        **kwargs,
    ) -> bytes:
        """
        将文本合成为 WAV 音频（同步调用，包装为 async）。

        Args:
            text: 要合成的文本。
            output_path: 保存路径，不提供则保存到 output_dir 下。
            character_name: 角色名称（对应配置中的 characters key）。
            split_sentence: 是否按分句合成。
            **kwargs: 其他 genie_tts.tts 参数。

        Returns:
            WAV 音频数据的字节流。
        """
        self._ensure_import()

        # 确定输出路径
        save_path = output_path
        if save_path is None and self._output_dir is not None:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            safe_name = _sanitize_filename(text[:30])
            save_path = self._output_dir / f"{safe_name}.wav"

        # 确定角色
        char_name = character_name
        if char_name is None and self._characters:
            char_name = next(iter(self._characters))

        # 自动加载角色和参考音频（如果配置了角色信息）
        if char_name and char_name in self._characters:
            char_info = self._characters[char_name]
            language = char_info.get("language", "jp")
            # 加载模型（genie_tts.load_character(name, onnx_model_dir, language)）
            model_path = self._resolve_model_path(char_name)
            if model_path.exists():
                self._genie.load_character(char_name, str(model_path), language)
            # 设置参考音频
            prompt_wav = char_info.get("prompt_wav", "")
            prompt_text = char_info.get("prompt_text", "")
            wav_path = self._resolve_prompt_wav_path(char_name, prompt_wav)
            if wav_path.exists():
                self._genie.set_reference_audio(char_name, str(wav_path), prompt_text, language)

        # 确定分句参数
        do_split = split_sentence if split_sentence is not None else self._default_params.get("split_sentence", False)

        # 调用 genie_tts.tts（同步）
        audio_data = self._genie.tts(
            character_name=char_name,
            text=text,
            play=False,
            save_path=str(save_path) if save_path else None,
            split_sentence=do_split,
        )

        if save_path and save_path.exists():
            return save_path.read_bytes()
        if audio_data is not None:
            return audio_data
        return b""

    async def stream(
        self,
        text: str,
        *,
        character_name: Optional[str] = None,
        split_sentence: Optional[bool] = None,
        **kwargs,
    ) -> AsyncIterator[bytes]:
        """
        流式合成语音，使用 genie_tts.tts_async 逐 chunk 产生 WAV 音频数据。

        Args:
            text: 要合成的文本。
            character_name: 角色名称。
            split_sentence: 是否按分句合成。
            **kwargs: 其他参数。

        Yields:
            WAV 音频数据块。
        """
        self._ensure_import()

        char_name = character_name
        if char_name is None and self._characters:
            char_name = next(iter(self._characters))

        do_split = split_sentence if split_sentence is not None else self._default_params.get("split_sentence", False)

        async for chunk in self._genie.tts_async(
            character_name=char_name,
            text=text,
            play=False,
            split_sentence=do_split,
        ):
            yield chunk

    async def get_voices(self) -> list[dict]:
        """
        获取预配置的角色语音列表。

        返回角色名称、语言和描述信息。
        """
        return [
            {
                "voice": name,
                "language": info.get("language", ""),
                "description": info.get("description", name),
            }
            for name, info in self._characters.items()
        ]

    async def validate_config(self) -> bool:
        """验证 Genie-TTS 配置：检查 GenieData 路径和 genie_tts 可导入"""
        try:
            import genie_tts
        except ImportError:
            return False

        # 检查 GenieData 目录
        data_dir = os.environ.get("GENIE_DATA_DIR") or (str(self._data_dir) if self._data_dir else "")
        if not data_dir:
            return False
        data_path = Path(data_dir)
        if not data_path.exists():
            return False
        # 检查关键文件
        required = ["speaker_encoder.onnx", "chinese-hubert-base", "G2P"]
        for item in required:
            if not (data_path / item).exists():
                return False
        return True

    async def load_character(self, character_name: str, language: str = "jp") -> bool:
        """
        从本地 ONNX 目录加载角色。

        Args:
            character_name: 角色名称。
            language: 语言代码（如 "jp", "zh", "en"）。

        Returns:
            True 表示加载成功。
        """
        self._ensure_import()
        try:
            model_path = self._resolve_model_path(character_name)
            self._genie.load_character(character_name, str(model_path), language)
            return True
        except Exception:
            return False

    async def set_reference_audio(
        self,
        character_name: str,
        prompt_wav: str,
        prompt_text: str,
        language: str = "jp",
    ) -> bool:
        """
        设置角色的参考音频（用于语音克隆）。

        Args:
            character_name: 角色名称。
            prompt_wav: 参考音频文件名（如 "zh_vo_Main_Linaxita_2_1_10_26.wav"）。
            prompt_text: 参考音频的文本内容。
            language: 语言代码。

        Returns:
            True 表示设置成功。
        """
        self._ensure_import()
        try:
            wav_path = self._resolve_prompt_wav_path(character_name, prompt_wav)
            self._genie.set_reference_audio(
                character_name,
                str(wav_path),
                prompt_text,
                language,
            )
            return True
        except Exception:
            return False

    async def unload_character(self, character_name: str) -> bool:
        """卸载角色释放资源"""
        self._ensure_import()
        try:
            self._genie.unload_character(character_name)
            return True
        except Exception:
            return False

    async def clear_cache(self) -> bool:
        """清空参考音频缓存"""
        self._ensure_import()
        try:
            self._genie.clear_reference_audio_cache()
            return True
        except Exception:
            return False

    async def stop(self) -> bool:
        """停止当前合成任务"""
        self._ensure_import()
        try:
            self._genie.stop()
            return True
        except Exception:
            return False


# ── 辅助函数 ──

def _sanitize_filename(text: str, max_len: int = 50) -> str:
    """将文本转为安全的文件名片段"""
    import re

    safe = re.sub(r"[^\w\-_ ]", "", text, flags=re.UNICODE)
    safe = safe.strip().replace(" ", "_")
    if len(safe) > max_len:
        safe = safe[:max_len]
    if not safe:
        safe = "tts_output"
    return safe
