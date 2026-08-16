from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT_DIR / "web"

SYSTEM_PROMPT_VI = (
    "bạn là một chatbot mini, luôn trả lời ngắn gọn và dễ thương. "
    "chỉ trả lời thôi không phải giải thích gì thêm. "
    "Không trả lời bằng emoji, chỉ dùng chữ"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8080

    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2"
    ollama_keep_alive: str = "-1"
    ollama_num_predict: int = 80

    stt_engine: str = "phowhisper"
    phowhisper_model: str = "vinai/PhoWhisper-small"
    stt_device: str = "auto"
    whisper_model: str = "small"

    tts_engine: str = "gtts"
    gtts_lang: str = "vi"
    gtts_tld: str = "com.vn"


settings = Settings()
