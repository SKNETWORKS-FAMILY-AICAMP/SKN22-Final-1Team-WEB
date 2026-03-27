# 1. 빌드 단계: 파이썬 3.12 슬림 버전 사용 (경량화 및 최신 환경)
FROM python:3.12-slim

# 2. 환경 변수 설정
# .pyc 파일을 생성하지 않도록 설정
ENV PYTHONDONTWRITEBYTECODE=1
# 로그가 버퍼링 없이 즉시 출력되도록 설정
ENV PYTHONUNBUFFERED=1
# 파이썬 모듈 검색 경로 설정 (경로 에러 해결의 핵심)
ENV PYTHONPATH=/app

# 3. 작업 디렉토리 설정
WORKDIR /app

# 4. 시스템 의존성 설치 (PostgreSQL 및 빌드 도구)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# 5. 파이썬 라이브러리 설치
# 캐싱 효율을 위해 소스 코드 복사 전에 requirements.txt를 먼저 처리합니다.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. 프로젝트 소스 코드 복사
# 현재 폴더의 모든 내용을 컨테이너의 /app으로 복사합니다.
COPY . .

# 7. 필요한 디렉토리 생성 (AI 처리 및 미디어 저장용)
RUN mkdir -p storage/captures storage/processed storage/synthetic

# 8. 컨테이너 개방 포트
EXPOSE 8000

# 9. Gunicorn 서버 실행
# --pythonpath 옵션을 통해 프로젝트 루트를 명확히 지정하여 실행합니다.
CMD ["sh", "-c", "python manage.py collectstatic --noinput && python manage.py migrate --noinput && gunicorn --bind 0.0.0.0:8000 --pythonpath /app mirrai_project.wsgi:application"]
