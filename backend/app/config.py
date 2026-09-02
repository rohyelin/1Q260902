from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    openai_text_model: str = ""
    openai_vision_model: str = ""
    # 핵심정리(summary) 전용 모델. 교정본이 이미 깨끗해 요약은 저가 모델로 충분.
    openai_summary_model: str = "gpt-4o-mini"
    # 가독성(문어체 변환) 전용 모델. 가벼운 작업이라 저가 모델로. 배치 1회 호출.
    openai_readability_model: str = "gpt-4o-mini"

    job_storage_dir: str = "./storage/jobs"
    max_pdf_size_mb: int = 100
    # 쉼표 구분. Vercel 도메인은 allow_origin_regex로 추가 허용
    cors_origins: str = (
        "http://localhost:3000,http://localhost:3010,"
        "http://127.0.0.1:3000,http://127.0.0.1:3010"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def storage_path(self) -> Path:
        return Path(self.job_storage_dir).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
