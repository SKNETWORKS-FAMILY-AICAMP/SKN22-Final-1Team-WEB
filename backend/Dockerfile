# 빌드 단계: 파이썬 3.12 슬림 버전 사용
FROM python:3.12-slim

# 환경 변수 설정
# .pyc 파일을 생성하지 않도록 설정 (컨테이너 경량화)
ENV PYTHONDONTWRITEBYTECODE 1
# 로그가 버퍼링 없이 즉시 출력되도록 설정 (디버깅 용이)
ENV PYTHONUNBUFFERED 1

# ★ 수정 반영: 파이썬 모듈 검색 경로 설정
# 컨테이너 내의 /app 폴더를 파이썬 경로에 추가하여 
# mirrai_project나 app 폴더를 어디서든 인식할 수 있게 합니다.
ENV PYTHONPATH=/app

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 의존성 설치
# psycopg2(PostgreSQL) 및 기타 빌드 도구 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# 파이썬 라이브러리 설치
# 트렌드 크롤링/정제 파이프라인 의존성까지 함께 설치합니다.
COPY requirements.txt requirements-trends.txt ./
RUN pip install --no-cache-dir -r requirements-trends.txt

# 트렌드 크롤링용 Playwright 브라우저 설치
RUN python -m playwright install --with-deps chromium

# 프로젝트 소스 코드 복사
# 현재 로컬의 backend 폴더 내용을 컨테이너의 /app으로 모두 복사합니다.
COPY . .

RUN chmod +x /app/docker-entrypoint.sh

# 미디어 파일 및 AI 처리 결과를 저장할 디렉토리 생성
RUN mkdir -p storage/captures storage/processed storage/synthetic

# 컨테이너가 사용할 포트 번호 명시
EXPOSE 8000

# Gunicorn 서버 실행
# mirrai_project 패키지 및 app 모듈을 원활하게 찾기 위해 --pythonpath /app 옵션을 추가합니다.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--pythonpath", "/app", "mirrai_project.wsgi:application"]
# 스케줄러(선택)와 Gunicorn 서버 실행
# mirrai_project 폴더 안의 wsgi.py를 실행 파일로 지정합니다.
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "mirrai_project.wsgi:application"]
