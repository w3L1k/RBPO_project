from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret: str
    seed_password: str
    access_token_minutes: int


def get_settings() -> Settings:
    jwt_secret = os.getenv("JWT_SECRET")
    seed_password = os.getenv("SEED_PASSWORD")

    if not jwt_secret:
        raise RuntimeError("JWT_SECRET must be set")
    if len(jwt_secret) < 32:
        raise RuntimeError("JWT_SECRET must contain at least 32 characters")
    if not seed_password:
        raise RuntimeError("SEED_PASSWORD must be set")
    if len(seed_password) < 10:
        raise RuntimeError("SEED_PASSWORD must contain at least 10 characters")

    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./campus_helpdesk.db"),
        jwt_secret=jwt_secret,
        seed_password=seed_password,
        access_token_minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "30")),
    )
