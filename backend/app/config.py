import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    database_url: str
    upload_dir: Path
    cookie_secure: bool = False
    session_minutes: int = 30
    demo_mode: bool = False
    demo_password: str = "Demo@2026"
    max_upload_bytes: int = 5 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(BACKEND_ROOT / ".env", override=False)
        data_dir = BACKEND_ROOT / ".data"
        url = os.getenv("DATABASE_URL", f"sqlite:///{(data_dir / 'retake.sqlite3').as_posix()}")
        if not url.startswith(("sqlite:///", "mysql+pymysql://")):
            raise ValueError("DATABASE_URL must use sqlite:/// or mysql+pymysql://")
        minutes = int(os.getenv("SESSION_MINUTES", "30"))
        if not 1 <= minutes <= 1440:
            raise ValueError("SESSION_MINUTES must be between 1 and 1440")
        return cls(
            database_url=url,
            upload_dir=Path(os.getenv("UPLOAD_DIR", str(BACKEND_ROOT / ".uploads"))).resolve(),
            cookie_secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
            session_minutes=minutes,
            demo_mode=os.getenv("DEMO_MODE", "false").lower() == "true",
            demo_password=os.getenv("DEMO_PASSWORD", "Demo@2026"),
        )
