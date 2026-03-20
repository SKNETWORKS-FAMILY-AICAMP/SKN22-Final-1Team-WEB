import hmac, hashlib, time, json, base64, logging
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app import models

logger = logging.getLogger(__name__)
router = APIRouter()

security = HTTPBearer()


class TokenProvider:
    """순수 파이썬 구현 JWT 엔진 (PyJWT 대체 가능 구조)"""

    @staticmethod
    def _b64_encode(data: str) -> str:
        return base64.urlsafe_b64encode(data.encode()).decode().rstrip("=")

    @staticmethod
    def _b64_decode(data: str) -> str:
        padding = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode((data + padding).encode()).decode()

    def encode(self, customer_id: int) -> str:
        now = int(time.time())
        payload = {
            "customer_id": customer_id,
            "exp": now + settings.TOKEN_EXPIRE_SECONDS,
            "iat": now,
            "nbf": now,
            "iss": settings.TOKEN_ISSUER,
            "aud": settings.TOKEN_AUDIENCE,
        }
        payload_b64 = self._b64_encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True)
        )
        sig = hmac.new(
            settings.SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256
        ).hexdigest()
        return f"{payload_b64}.{sig}"

    def decode(self, token: str) -> int:
        try:
            payload_b64, sep, signature = token.rpartition(".")
            if not sep:
                raise ValueError("Invalid token format")

            expected = hmac.new(
                settings.SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("Signature mismatch")

            payload = json.loads(self._b64_decode(payload_b64))
            if payload.get("exp", 0) < int(time.time()):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
                )

            return payload["customer_id"]
        except Exception as e:
            logger.warning(f"Auth failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            )


token_provider = TokenProvider()


def get_current_user(
    auth: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> models.User:
    """인증된 유저 객체를 반환하는 의존성 주입용 함수"""
    customer_id = token_provider.decode(auth.credentials)
    user = db.query(models.User).filter(models.User.id == customer_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )
    return user


from app.schemas.customer import LoginRequest

@router.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """전화번호 기반 간편 로그인"""
    clean_phone = request.phone.replace("-", "").strip()
    user = db.query(models.User).filter(models.User.phone == clean_phone).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    return {"access_token": token_provider.encode(user.id), "token_type": "bearer"}
