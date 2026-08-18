from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT_DIR / "web"

SYSTEM_PROMPT_VI = (
    "bạn là một chatbot mini, luôn trả lời ngắn gọn và dễ thương. "
    "chỉ trả lời thôi không phải giải thích gì thêm. "
    "Không trả lời bằng emoji, chỉ dùng chữ. "
    "Luôn trả lời bằng tiếng Việt có dấu đầy đủ, không viết không dấu."
)

COMPOSE_SYSTEM_PROMPT_VI = (
    "Bạn là Mèo Bot. Dựa vào câu hỏi và thông tin đã tìm được, "
    "viết một câu trả lời hoàn chỉnh, dễ thương, bằng tiếng Việt có dấu. "
    "Chỉ dùng thông tin đã cho. Không bịa. Không emoji. Không nêu URL. "
    "Chỉ nói câu trả lời."
)

# Last instruction on every Cursor CLI call — models copy ASCII Vietnamese otherwise.
CURSOR_VI_DIACRITICS_RULE = (
    "Quy tắc bắt buộc: luôn trả lời tiếng Việt có dấu đầy đủ (Unicode). "
    "Cấm tiếng Việt không dấu. "
    "Đúng: \"Mình khỏe, cảm ơn bạn nha.\" "
    "Sai: \"Minh khoe, cam on ban nha.\""
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8080
    listen_ms: int = Field(default=5000, ge=1000, le=60000)

    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2"
    ollama_compose_model: str = "llama3.2"
    ollama_keep_alive: str = "-1"
    ollama_num_predict: int = 80
    ollama_num_predict_tools: int = 240

    cursor_cli_enabled: bool = True
    cursor_cli_bin: str = ""
    cursor_cli_model: str = "auto"
    cursor_cli_mode: str = "ask"
    cursor_cli_timeout_s: float = Field(default=60.0, ge=8.0, le=180.0)
    cursor_api_key: str = ""

    weather_city: str = "Ha Noi"
    google_api_key: str = ""
    google_cse_id: str = ""
    music_max_seconds: int = 90

    stt_engine: str = "phowhisper"
    phowhisper_model: str = "vinai/PhoWhisper-small"
    stt_device: str = "auto"
    stt_compute_type: str = "auto"
    stt_cpu_threads: int = 0
    whisper_model: str = "small"
    stt_language: str = "vi"
    elevenlabs_api_key: str = ""
    elevenlabs_stt_model: str = "scribe_v2"

    tts_engine: str = "gtts"
    gtts_lang: str = "vi"
    gtts_tld: str = "com.vn"

    web_search_enabled: bool = True
    web_search_max_results: int = 5
    web_search_region: str = "vn-vi"

    db_path: str = str(ROOT_DIR / "backend" / "data" / "katbot.sqlite")


settings = Settings()
