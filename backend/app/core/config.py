import os


class Settings:
    SECRET_KEY: str = os.getenv("SECRET_KEY")
    if not SECRET_KEY:
        # 테스트 환경(pytest) 실행 시에는 임시 키 할당으로 런타임 에러 방지
        if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("PYTHONPATH"):
            SECRET_KEY = "test_secret_key_for_mirrai_project"
        else:
            raise RuntimeError(
                "보안을 위해 SECRET_KEY 환경변수가 반드시 설정되어야 합니다."
            )

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./mirrai.db")

    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", 5))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", 10))
    DB_ECHO: bool = os.getenv("DB_ECHO", "false").lower() == "true"

    TOKEN_EXPIRE_SECONDS: int = 3600
    TOKEN_ISSUER: str = "mirrai"
    TOKEN_AUDIENCE: str = "mirrai-client"
    CLOCK_SKEW: int = 5

    MAX_TOKEN_LENGTH: int = 2048
    MAX_PAYLOAD_LENGTH: int = 1024
    MAX_customer_id: int = 10**12
    MAX_CLAIMS: int = 16


settings = Settings()
