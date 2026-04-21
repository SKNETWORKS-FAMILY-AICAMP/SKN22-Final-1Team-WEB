# Elastic Beanstalk Deploy Checklist

MirrAI 백엔드를 Elastic Beanstalk에 올릴 때 확인할 항목 정리.

## 1. 필수 환경 변수

아래 값이 없으면 앱이 정상 기동하지 않거나 주요 기능이 꺼진다.

### Django / core

- `SECRET_KEY`
- `DEBUG=False`
- `ALLOWED_HOSTS`
- `TIME_ZONE=Asia/Seoul`

### Database

- `SUPABASE_DB_URL`

권장:

- `SUPABASE_USE_REMOTE_DB=True`

참고:

- 현재 코드는 `SUPABASE_DB_URL`이 있으면 우선 사용한다.
- `DATABASE_URL`은 레거시 호환용 fallback으로만 본다.

### Chatbot

- `MIRRAI_MODEL_CHATBOT_API_KEY` 또는 `OPENAI_API_KEY`
- `MIRRAI_MODEL_CHATBOT_OPENAI_MODEL`

권장:

- `MIRRAI_MODEL_CHATBOT_FALLBACK_OPENAI_MODEL`
- `MIRRAI_MODEL_CHATBOT_TIMEOUT=20`
- `MIRRAI_MODEL_CHATBOT_MAX_OUTPUT_TOKENS=2048`
- `MIRRAI_MODEL_CHATBOT_STORE=true`
- `MIRRAI_MODEL_CHATBOT_REASONING_EFFORT=medium`
- `MIRRAI_MODEL_CHATBOT_REASONING_SUMMARY=auto`
- `MIRRAI_MODEL_CHATBOT_VERBOSITY=medium`

## 2. 권장 환경 변수

### Redis / cache / session

- `REDIS_URL`
- `REDIS_USE_FOR_SESSIONS=True`
- `REDIS_KEY_PREFIX=mirrai`
- `CACHE_DEFAULT_TIMEOUT=300`
- `PARTNER_DASHBOARD_CACHE_SECONDS=30`
- `PARTNER_LIST_CACHE_SECONDS=60`
- `PARTNER_DETAIL_CACHE_SECONDS=45`
- `PARTNER_HISTORY_CACHE_SECONDS=30`
- `PARTNER_LOOKUP_CACHE_SECONDS=45`
- `PARTNER_REPORT_CACHE_SECONDS=90`

### AI health / RunPod

- `MIRRAI_AI_PROVIDER=runpod`
- `RUNPOD_BASE_URL`
- `RUNPOD_API_KEY`
- `RUNPOD_ENDPOINT_ID`
- `MIRRAI_AI_HEALTH_TIMEOUT=5`
- `MIRRAI_AI_HEALTH_CACHE_SECONDS=15`

### Storage

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_BUCKET=mirrai-assets`
- `SUPABASE_USE_REMOTE_STORAGE=False|True`
- `S3_BUCKET_NAME` (S3 우선 사용 시)
- `S3_REGION=ap-northeast-2`

## 3. 트렌드 / 스케줄러

필요 시 설정:

- `ENABLE_TREND_SCHEDULER`
- `TREND_SCHEDULER_TIMEZONE`
- `TREND_SCHEDULER_WEEKLY_DAY`
- `TREND_SCHEDULER_WEEKLY_HOUR`
- `TREND_SCHEDULER_WEEKLY_MINUTE`
- `TREND_SCHEDULER_STEPS`
- `TREND_SCHEDULER_TIMEOUT`
- `TREND_SCHEDULER_POLL_INTERVAL`
- `TREND_SCHEDULER_SLEEP_INTERVAL`
- `BOOTSTRAP_RAG_ASSETS=1`
- `TREND_REFINER_MODEL`
- `TREND_LATEST_REMOTE_ENABLED`

## 4. NCS PDF / EFS

NCS PDF를 EFS에서 읽을 때 확인:

- `NCS_PDF_SYNC_SOURCE_DIR=/mnt/mirrai-ncs-pdfs`
- `NCS_PDF_SYNC_OVERWRITE=0`
- `NCS_PDF_SYNC_STRICT=1`
- `NCS_PACKAGED_EXAMPLE_PDF_BOOTSTRAP=1`
- `NCS_EFS_FILE_SYSTEM_ID`
- `NCS_EFS_REGION=ap-northeast-2`
- `NCS_EFS_ACCESS_POINT_ID` (선택)
- `NCS_EFS_MOUNT_POINT=/mnt/mirrai-ncs-pdfs`
- `NCS_EFS_MOUNT_TIMEOUT_SECONDS=45`

인프라 쪽 확인:

- EB 인스턴스와 EFS가 같은 VPC/subnet 접근 경로에 있는지
- EFS security group이 NFS `2049` 허용하는지
- EB 인스턴스 security group에서 EFS로 나가는 경로가 열려 있는지

## 5. EB 헬스 체크 확인 포인트

현재 앱 동작 기준:

- container port: `8000`
- host port: `80`
- health 응답 경로: `/`, `/health/`
- startup chain:
  - `collectstatic`
  - `verify_static_manifest`
  - `migrate`
  - `gunicorn`

헬스가 깨질 때 우선 확인:

1. `SUPABASE_DB_URL` 값 존재
2. 컨테이너 기동 실패 로그
3. migration 실패 여부
4. static manifest 검증 실패 여부
5. EFS mount warning/timeout 여부

## 6. 다른 배포 repo에 업로드할 파일

### A. 별도 repo가 이미지를 직접 빌드하는 경우

아래를 같이 올린다.

- `app/**`
- `mirrai_project/**`
- `templates/**`
- `static/**`
- `data/**`
- `Dockerfile`
- `.dockerignore`
- `docker-entrypoint.sh`
- `manage.py`
- `requirements.txt`
- `requirements-deploy.txt`
- `requirements-trends.txt`
- `Dockerrun.aws.json`
- `.platform/**`
- `.github/workflows/deploy.yml` 또는 해당 repo 전용 workflow

### B. 별도 repo가 prebuilt ECR 이미지만 배포하는 경우

최소 파일:

- `Dockerrun.aws.json`
- `.platform/bin/mount_ncs_efs.sh`
- `.platform/hooks/predeploy/10_mount_ncs_efs.sh`
- `.platform/confighooks/predeploy/10_mount_ncs_efs.sh`

추가 작업:

- `Dockerrun.aws.json`의 `Image.Name`을 실제 ECR 이미지 URI로 바꾸기
- EB 환경 변수는 배포 repo가 아니라 EB 환경 설정에 넣기

## 7. 빠른 로그 명령

```bash
eb logs
eb ssh
sudo docker ps -a
sudo docker logs <container_id>
sudo tail -n 200 /var/log/eb-engine.log
```
