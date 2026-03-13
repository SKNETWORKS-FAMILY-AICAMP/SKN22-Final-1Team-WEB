# [Step 1] Build Context
FROM python:3.11-slim as builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# [Step 2] Production Image
FROM python:3.11-slim

# non-root 사용자 생성 (보안 강화)
RUN useradd -m appuser

WORKDIR /app

# builder에서 설치된 패키지 복사
COPY --from=builder /root/.local /home/appuser/.local

# Python PATH 설정
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 애플리케이션 코드 복사
COPY . .

# 권한 변경 및 사용자 전환
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# uvicorn 실행
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
