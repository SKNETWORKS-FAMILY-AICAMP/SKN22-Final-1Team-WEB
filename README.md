# MirrAI

MirrAI는 고객 촬영 이미지와 설문 데이터를 바탕으로 얼굴 분석, 헤어스타일 추천, 상담 연계를 제공하는 Django 기반 살롱 추천 플랫폼입니다. 고객 화면, 파트너/디자이너 운영 화면, 최신 트렌드 피드, 챗봇 보조 기능까지 하나의 저장소 안에서 함께 운영합니다.

---

## 서비스 개요

- 고객(Customer) 여정
  서비스 시작, 고객 정보 입력, 설문 응답, 촬영, AI 분석 결과 확인, 추천 스타일 선택, 상담 요청
- 파트너(Partner) 운영
  매장 단위 고객 조회, 디자이너 선택, 고객 상세 이력 확인, 상담 상태 관리
- 디자이너(Designer) 지원
  디자이너 전용 화면, 고객 상세 페이지, 상담 완료 페이지, 챗봇 기반 상담 보조
- 최신 트렌드 피드
  최신 헤어 트렌드 기사/스타일 카드 제공, 최신 5선 노출, 매체명 표시
- 트렌드/RAG 파이프라인
  크롤링, 정제, 벡터화, 카드 재구성, 챗봇 검색용 로컬 벡터 스토어 운영

---

## 비즈니스 계정 및 세션 구조

MirrAI는 매장 중심 B2B2C 구조를 기준으로 동작합니다.

- 파트너 계정
  매장 전체 운영을 관리하는 관리자 계정
- 디자이너 계정
  실제 상담과 시술을 담당하는 실무 계정
- 고객 계정
  촬영/분석/추천 서비스를 이용하는 최종 사용자

페이지 구분:

- 파트너 대시보드: `/partner/dashboard/`
- 디자이너 화면: `/partner/staff/`
- 고객 흐름: `/customer/` 이하

세션 흐름:

1. 파트너가 로그인하여 매장 세션을 생성합니다.
2. 디자이너를 선택하고 PIN으로 디자이너 세션을 확정합니다.
3. 고객은 별도 세션으로 설문, 촬영, 결과 확인을 진행합니다.
4. 파트너/디자이너 세션과 고객 세션은 목적에 따라 분리되어 동작합니다.

---

## 핵심 기능

### 1. 고객 설문 및 촬영

- 길이, 분위기, 두피 상태, 컬러, 예산 등 선호도 수집
- 프론트 검증 + 백엔드 검증을 통한 촬영 품질 확인
- 필요 시 캡처 이미지 저장, 비식별화 이미지 저장, 스토리지 정책 기록

### 2. 얼굴 분석 및 추천

- 촬영 업로드 후 얼굴 분석 비동기 실행
- 설문 + 얼굴 분석 결과를 조합해 Top-5 추천 생성
- 추천 선택 후 상담 요청 또는 바로 상담 요청 가능

### 3. 추천 결과 페이지 동작

최근 변경 사항:

- 결과 페이지는 이제 실제 추천 이미지가 준비되기 전까지 로딩 상태를 유지합니다.
- 샘플 스타일 이미지는 최종 추천 완료 상태로 간주하지 않습니다.
- 최신 추천 배치가 처리 중이면 결과 페이지가 계속 폴링하며 기다립니다.
- 추천 이미지 준비 안내 문구에 예상 시간(보통 1~2분)을 표시합니다.
- `styles/...` 자산이 누락된 경우에도 플레이스홀더 이미지로 안전하게 대체합니다.
- 로딩 중 **단계별 진행 표시**(이미지 저장 → 얼굴 분석 → 스타일 추천 → 이미지 합성)가 노출됩니다.
- 다중 링 스피너 애니메이션이 로딩 중 화면에서 올바르게 작동합니다.

### 4. 최신 트렌드 피드

- 최신 헤어 트렌드 5선 카드 제공
- 카드에 잡지사/매체명 노출
- `source_name` 기준으로 보기 좋은 출처명 표시

### 5. 디자이너 챗봇

- 로컬 ChromaDB + 디자이너 지원 데이터셋 기반 응답
- 고객 상세/상담 완료 페이지에서 상담 보조
- 프롬프트 우회, 역할 변경 요청 등 보안상 민감한 입력은 차단 대상

---

## 저장소 구조

```text
app/                    Django 앱, API, 서비스 로직
mirrai_project/         Django 프로젝트 설정 및 URL
templates/              고객/관리자/공용 템플릿
static/                 정적 자산
data/                   트렌드 및 벡터 스토어 입력 데이터
terraform/              인프라 코드
requirements.txt        로컬 개발용 전체 의존성
requirements-deploy.txt 배포용 최소 런타임 의존성
requirements-trends.txt 배포용 + 트렌드 파이프라인 확장 의존성
```

---

## 의존성 파일 구성

최근 변경 사항:

- `requirements-deploy.txt`
  배포 웹 컨테이너에서 필요한 최소 런타임 의존성
- `requirements-trends.txt`
  배포 기본 의존성 위에 트렌드 파이프라인 관련 패키지를 추가한 파일
- `requirements.txt`
  로컬 개발용 전체 의존성 파일. 현재 `requirements-trends.txt`를 포함하고 Playwright 같은 로컬 도구를 추가합니다.

설치:

```bash
pip install -r requirements.txt
```

---

## 로컬 실행 및 초기 설정

### 1. 환경 변수 파일 준비

```powershell
Copy-Item .env.example .env
```

주요 설정 패턴:

- 로컬 SQLite 사용:
  `LOCAL_DATABASE_URL=sqlite:///db.sqlite3`
- 로컬 Postgres 사용:
  `LOCAL_DATABASE_URL=postgres://user:pass@localhost:5432/mirrai_db`
- 공유/배포 Postgres 사용:
  `SUPABASE_USE_REMOTE_DB=True`
  `SUPABASE_DB_URL=postgresql://...`
- Redis 캐시/세션 사용:
  `REDIS_URL=redis://127.0.0.1:6379/1`

최근 변경 사항:

- 설정은 이제 `DATABASE_URL`과 `LOCAL_DATABASE_URL`을 모두 인식합니다.
- Docker Compose, 로컬 셸, 배포 환경에서 같은 규칙을 조금 더 안전하게 쓸 수 있습니다.

### 2. 마이그레이션 및 서버 실행

```bash
python manage.py migrate
python manage.py runserver
```

### 3. 자주 쓰는 점검 명령

```bash
python manage.py check
python manage.py test
```

### 4. 브라우저 기반 테스트 도구 설치

```bash
playwright install chromium
```

---

## Docker Compose

`docker-compose.yml` 제공 서비스:

- `web`
  Django 앱 컨테이너
- `db`
  Postgres
- `redis`
  Redis
- `scheduler`
  트렌드 스케줄러 전용 컨테이너

실행:

```bash
docker compose up --build
```

최근 변경 사항:

- `scheduler`는 `INSTALL_TRENDS_DEPS=1`로 빌드됩니다.
- 스케줄러 실행 명령은 `python manage.py run_trend_scheduler`로 정리했습니다.
- Compose 환경에서도 `DATABASE_URL`과 `LOCAL_DATABASE_URL`을 함께 넣어 로컬/배포 규칙 차이를 줄였습니다.

---

## 추천 결과 파이프라인

고객 추천 흐름:

1. 고객이 촬영 이미지를 업로드합니다.
2. 촬영 이미지를 검증하고 설정에 따라 저장합니다.
3. 얼굴 분석이 비동기로 실행됩니다.
4. 설문과 얼굴 분석이 준비되면 헤어스타일 추천 생성이 시작됩니다.
5. 결과 페이지는 실제 추천 이미지가 준비될 때까지 로딩을 유지합니다.

현재 동작 기준:

- 최신 캡처/분석이 아직 처리 중이면 `processing` 상태를 반환합니다.
- 현재 분석 기준 배치가 있어도 샘플 이미지뿐이면 `ready`로 처리하지 않습니다.
- 최신 분석 기준의 실제 시뮬레이션 이미지가 준비된 경우에만 최종 결과를 보여줍니다.

---

## 최신 트렌드 / RAG / 챗봇

### 최신 트렌드 피드

- 페이지: `/customer/trend/`
- API: `GET /api/v1/analysis/trend/latest/?limit=5`
- 최신 5선 카드에서 잡지사/매체명 표시

### 트렌드 전체 갱신

```bash
python manage.py refresh_trends
python manage.py refresh_trends --mode local --steps vectorize
python manage.py refresh_trends --mode runpod-pipeline
python manage.py run_trend_scheduler
```

### 로컬 챗봇/RAG 구성

- 데이터셋: `app/data/chatbot/designer_support_dataset_v5_final_revised_optimized.json`
- 페르소나 프롬프트: `app/data/chatbot/designer_instructor_persona.md`
- 로컬 벡터 스토어 루트: `data/rag/stores/`
- 챗봇 서비스: `app/services/chatbot/service.py`
- RAG 로직: `app/services/chatbot/rag.py`
- 프롬프트 빌더: `app/services/chatbot/prompt_builder.py`

---

## 주요 접속 경로

로컬 기준: `http://localhost:8000`

### 고객 화면

- 시작/로그인: `/customer/`
- 설문: `/customer/survey/`
- 촬영: `/customer/camera/`
- 추천 결과: `/customer/recommendations/`
- 최신 트렌드: `/customer/trend/`

### 파트너/디자이너 화면

- 파트너 로그인: `/partner/`
- 디자이너 선택: `/partner/designer-select/`
- 파트너 대시보드: `/partner/dashboard/`
- 디자이너 화면: `/partner/staff/`

---

## 주요 환경 변수 그룹

### 데이터베이스 / 캐시

- `DATABASE_URL`
- `LOCAL_DATABASE_URL`
- `SUPABASE_USE_REMOTE_DB`
- `SUPABASE_DB_URL`
- `REDIS_URL`
- `REDIS_USE_FOR_SESSIONS`

### 추천 파이프라인

- `RUNPOD_API_KEY`
- `RUNPOD_ENDPOINT_ID`
- `MIRRAI_AI_PROVIDER` — `runpod` (기본값) 또는 `local`
- `MIRRAI_LOCAL_MOCK_RESULTS`
- `MIRRAI_PERSIST_CAPTURE_IMAGES` — `True`로 설정 시 분석 이미지를 로컬/Supabase에 저장합니다. 파이프라인 정상 동작에 필요합니다.

### 트렌드 스케줄러

- `ENABLE_TREND_SCHEDULER`
- `TREND_SCHEDULER_TIMEZONE`
- `TREND_SCHEDULER_STEPS`
- `GEMINI_API_KEY`

### 최신 트렌드 피드

- `TREND_LATEST_REMOTE_ENABLED`
- `TREND_LATEST_RUNPOD_TIMEOUT`
- `TREND_LATEST_RUNPOD_POLL_INTERVAL`

### 챗봇

- `MIRRAI_MODEL_CHATBOT_PROVIDER`
- `MIRRAI_MODEL_CHATBOT_API_KEY`
- `MIRRAI_MODEL_CHATBOT_OPENAI_MODEL`

---

## DevOps / 인프라 구조

- 오케스트레이션: AWS Elastic Beanstalk
- 이미지 저장소: Amazon ECR
- 정적/파일 저장: Supabase Storage 및 로컬 스토리지
- 데이터베이스: Supabase Postgres 또는 로컬 SQLite
- 캐시: Redis
- 인프라 코드: Terraform

운영 시 권장 사항:

- `.env`는 버전 관리에 포함하지 않습니다.
- 공유 환경에서는 Redis를 붙여 세션/캐시를 안정적으로 운영하는 것을 권장합니다.
- 운영 웹 이미지는 `requirements-deploy.txt`, 트렌드 작업 컨테이너는 `requirements-trends.txt`, 로컬 개발은 `requirements.txt`를 기준으로 사용합니다.

---

## CI/CD

GitHub Actions는 `.github/workflows/deploy.yml` 기준으로 `main` 브랜치 푸시 시 배포를 수행합니다.

배포 흐름:

1. Docker 이미지 빌드
2. Amazon ECR 푸시
3. `Dockerrun.aws.json`에 이미지 URI 반영
4. Elastic Beanstalk 애플리케이션 버전 생성
5. Elastic Beanstalk 환경 업데이트

트렌드 파이프라인 의존성이 필요한 이미지를 별도로 만들 때:

```bash
docker build --build-arg INSTALL_TRENDS_DEPS=1 -t mirrai .
```

---

## 테스트 명령

집중 테스트:

```bash
python manage.py test app.tests.test_recommendation_diagnostics --verbosity 2
python manage.py test app.tests.test_storage_service --verbosity 2
```

전체 점검:

```bash
python manage.py check
python manage.py test
```

---

## 운영 메모

- 현재 추천 결과 페이지는 최신 배치를 기준으로만 결과를 열어주도록 강화되었습니다.
- 샘플 이미지 fallback과 실제 생성 이미지의 구분이 더 명확해졌습니다.
- README와 `.env.example`은 최근 변경된 로컬/배포 설정 흐름에 맞춰 다시 정리되었습니다.

### 파이프라인 연결 문제 (트러블슈팅)

**증상**: 추천 이미지가 생성되지 않거나 로딩 화면에서 멈춥니다.

**원인 및 해결**:

1. **Supabase 키 오류** — `SUPABASE_SECRET_KEY`(publishable key)는 스토리지 권한이 없습니다.  
   → `SUPABASE_SERVICE_ROLE_KEY`에 service_role 키를 설정하세요.

2. **이미지 저장 실패** — Supabase 버킷이 없거나 업로드 실패 시 `analysis_image_url`이 비어 헤어스타일 파이프라인이 스킵됩니다.  
   → `MIRRAI_PERSIST_CAPTURE_IMAGES=True` + Supabase service_role 키 설정으로 해결됩니다.  
   → Supabase 실패 시 로컬 저장(`storage/analysis-inputs/`)으로 자동 폴백됩니다.

3. **로딩 스피너 미작동** — `base.css` 캐시로 인해 `@keyframes spin`이 없는 구버전이 로드될 수 있습니다.  
   → CSS 버전 파라미터 업데이트 또는 강제 새로고침(Ctrl+Shift+R)으로 해결됩니다.

