# 🪞 MirrAI (SKN22-Final-1Team-WEB)

AI 기반 퍼스널 헤어 스타일 분석 및 추천 솔루션, **MirrAI** 프로젝트 저장소입니다.  
고객의 페이스 라인 분석과 개인별 스타일 취향을 결합하여 최적의 헤어스타일을 제안하고, 디자이너와의 스마트한 상담 환경을 제공합니다.

현재 구조는 **Django (MVT)** 아키텍처를 중심으로 동작하며, 로컬 개발 환경에서는 **ChromaDB 기반 RAG**, **자동 트렌드 스케줄러**, **디자이너 챗봇**까지 함께 검증할 수 있습니다.

---

## 💡 서비스 개요

- **고객(Customer) 여정**: 서비스 시작 → 개인정보 동의 → 취향 설문 → 페이스 스캔 → AI 분석 리포트 및 추천 확인
- **파트너(Partner) 관리**: 실시간 고객 검색, 상세 분석 이력 관리, 매장 고객/상담 흐름 확인
- **디자이너(Designer) 업무 지원**: 디자이너 대시보드, 고객 상세 페이지, 상담 완료 페이지에서 챗봇 기반 상담 보조
- **트렌드/RAG 파이프라인**: 최신 헤어 트렌드 수집, 정제, 벡터화, ChromaDB 저장 및 최신 카드 피드 제공
- **디자인 컨셉**: 소프트 미니멀리즘 + 에디토리얼 레이아웃 기반의 반응형 웹(PC/Tablet/Mobile/Kiosk) 최적화

---

## 🧭 비즈니스 계층 및 세션 구조

MirrAI는 매장 중심의 B2B2C 서비스 구조를 채택합니다.

### 1. 계층 구조

- **파트너 (Partner / Store Owner)**: 매장 전체 운영을 총괄하는 관리자 계정
- **디자이너 (Designer / Staff)**: 실제 고객 상담과 시술을 담당하는 전문가 계정
- **고객 (Customer)**: 분석 및 추천 서비스를 이용하는 최종 사용자

### 2. 페이지별 독립 구동 모델

- **통합 대시보드**: `/partner/dashboard/`
  - 대상: 매장 관리자
  - 주요 기능: 디자이너 관리, 고객 목록 조회, 매장 단위 운영 화면
- **디자이너 대시보드**: `/partner/staff/`
  - 대상: 디자이너 PIN 인증 사용자
  - 주요 기능: 담당 고객 확인, 상담 보조 챗봇, 디자이너 전용 업무 화면

### 3. 인증 및 세션 흐름

1. **파트너 인증**: 관리자 연락처와 비밀번호로 매장 세션 활성화
2. **디자이너 인증**: 활성화된 매장 안에서 디자이너를 선택하고 4자리 PIN으로 2차 인증
3. **세션 분리**:
   - `/partner/dashboard/` 는 관리자 화면
   - `/partner/staff/` 는 디자이너 화면
4. **보안 흐름**:
   - 고객 세션과 파트너 세션은 분리
   - 디자이너 세션에서는 관리자 전용 화면 접근이 제한됨

---

## 🚀 핵심 기능

- **정교한 스타일 설문**: 길이, 분위기, 모발 상태, 컬러, 예산 기반 취향 수집
- **AI 페이스 분석**:
  - 프론트엔드: MediaPipe 기반 실시간 얼굴 분석과 촬영 품질 체크
  - 백엔드: OpenCV 기반 이미지 전처리 및 얼굴형 분석
- **최신 헤어 트렌드 피드**:
  - 최신 크롤링 결과 기반 헤어스타일/헤어컬러 기사 5건 선별
  - `/api/v1/analysis/trend/latest/` API 제공
  - 고객/매장 관리자/디자이너 모두 접근 가능
- **로컬 ChromaDB 기반 RAG**:
  - 트렌드 카드: `chromadb_trends`
  - 챗봇: `chromadb_chatbot`
- **디자이너 챗봇**:
  - 로컬 ChromaDB + 디자이너 지원 데이터셋 기반 응답
  - 디자이너 대시보드, 고객 상세, 상담 완료 페이지에서 사용 가능

---

## 🗂 프로젝트 구조

```text
.
├── app/                    # 비즈니스 로직, API(v1), 서비스, 테스트
├── mirrai_project/         # Django 프로젝트 설정
├── static/                 # 정적 자산
├── templates/              # HTML 템플릿
├── data/                   # 로컬 데이터셋 및 트렌드/Chroma 저장소
├── docs/                   # 문서
├── terraform/              # 인프라 코드
├── manage.py               # Django 관리 스크립트
├── requirements.txt        # 기본 파이썬 의존성
├── requirements-trends.txt # 트렌드/RAG 확장 의존성
└── run_server.bat          # Windows 로컬 실행 보조 스크립트
```

---

## 🛠 로컬 실행 및 초기 설정

### 1) 패키지 설치 및 DB 초기화

```bash
pip install -r requirements.txt
pip install -r requirements-trends.txt
python manage.py migrate
playwright install chromium
```

### 2) 환경 변수 설정

Windows CMD:

```bash
copy .env.example .env
```

PowerShell:

```powershell
Copy-Item .env.example .env
```

로컬 권장 설정:

- `ENABLE_TREND_SCHEDULER=true`
- `TREND_LATEST_REMOTE_ENABLED=false`
- `MIRRAI_MODEL_CHATBOT_PROVIDER=local`

### 3) 테스트 데이터 생성

```bash
python manage.py seed_test_accounts
```

추가 대량 테스트 데이터가 필요하면:

```bash
python seed_100_data.py
```

### 4) 서버 실행

```bash
python manage.py runserver
```

Windows에서는 아래 배치 파일로도 실행할 수 있습니다.

```bash
run_server.bat
```

### 5) 자동 스케줄러

현재는 `.env` 의 `ENABLE_TREND_SCHEDULER=true` 인 상태에서 Django 서버가 시작되면 트렌드 스케줄러도 함께 자동 시작됩니다.

- 시간대는 `.env` 의 `TREND_SCHEDULER_TIMEZONE` 을 사용
- 기본적으로 `TIME_ZONE` 과 같은 값으로 맞춰서 사용 가능
- `run_server.bat` 뿐 아니라 `python manage.py runserver` 실행 시에도 자동 시작

별도 프로세스로만 스케줄러를 보고 싶다면:

```bash
python manage.py run_trend_scheduler
```

---

## 🧪 바로 테스트하기

### 1. 관리자 로그인

`python manage.py seed_test_accounts` 실행 후 아래 계정으로 로그인할 수 있습니다.

- 로그인 페이지: `http://localhost:8000/partner/login/`
- 관리자 전화번호: `01080001000`
- 관리자 비밀번호: `1234`

### 2. 디자이너 세션 진입

디자이너 챗봇을 가장 빠르게 확인하는 방법입니다.

1. 관리자 계정으로 로그인
2. `http://localhost:8000/partner/designer-select/` 이동
3. 디자이너 선택
4. 아래 PIN 중 하나 입력
   - `2468`
   - `1357`
5. `http://localhost:8000/partner/staff/` 로 이동되면 챗봇 확인 가능

### 3. 챗봇이 보이는 페이지

- 디자이너 대시보드: `http://localhost:8000/partner/staff/`
- 파트너 고객 상세: `http://localhost:8000/partner/customer-detail/<client_id>/`
- 고객 상담 완료 페이지: `http://localhost:8000/customer/consultation/complete/`

예시 질문:

- `볼륨매직 후 관리 방법 알려줘`
- `허쉬컷 상담 문구 알려줘`

현재 챗봇 라우팅 순서:

- `local_chromadb`
- 원격 챗봇이 설정되어 있으면 remote fallback
- 둘 다 실패하면 dummy 응답

---

## 🔄 최신 트렌드 / RAG 동작

### 1. 최신 트렌드 카드

최신 트렌드 카드는 현재 로컬 우선 설정입니다.

- `TREND_LATEST_REMOTE_ENABLED=false`
- 조회 순서: `chromadb_trends -> refined_trends.json -> raw trend JSON`

페이지:

- `http://localhost:8000/customer/trend/`

API:

- `GET /api/v1/analysis/trend/latest/?limit=5`

### 2. 트렌드 전체 갱신

```bash
python manage.py refresh_trends
python manage.py refresh_trends --mode local --steps vectorize
python manage.py refresh_trends --mode runpod-pipeline
python manage.py refresh_trends --mode runpod-archive --build-local
```

기본 로컬 파이프라인 순서:

```text
crawl -> refine -> llm_refine -> vectorize -> rebuild_ncs -> rebuild_styles
```

### 3. 로컬 챗봇 코퍼스

디자이너 챗봇은 아래 파일과 저장소를 사용합니다.

- 데이터셋: `app/data/chatbot/designer_support_dataset_v5_final_revised_optimized.json`
- 프롬프트 템플릿: `app/data/chatbot/designer_instructor_persona.md`
- 로컬 Chroma 저장소: `data/rag/stores/chromadb_chatbot/`
- 응답 엔진: `app/services/chatbot_local_engine.py`
- 프롬프트 빌더: `app/services/chatbot_prompt_builder.py`

최근 정리 내용:

- 인사/감사/짧은 질문은 섹션 제목 없이 자연스럽게 응답합니다.
- 일반 시술 질문은 강사처럼 핵심 설명과 체크 포인트를 나눠서 안내합니다.
- RAG 랭킹은 질문 토큰 정규화, 조사 제거, 주제별 보너스/패널티, 노이즈 문서 필터를 함께 사용합니다.
- 예를 들어 `염색 전 주의사항` 질문은 가발 자료보다 패치 테스트, 알레르기, 두피 상태 관련 문서를 우선 참조합니다.

위 Chroma 저장소와 manifest 파일은 로컬 생성물이므로 Git에서는 무시합니다.

---

## 🧪 자주 쓰는 테스트 명령

핵심 테스트:

```bash
python manage.py test app.tests.test_chatbot_prompt_builder
python manage.py test app.tests.test_chatbot_local_engine
python manage.py test app.tests.test_chatbot_service
python manage.py test app.tests.test_latest_feed
python manage.py test app.tests.test_vectorize_chromadb
python manage.py test app.tests.test_ai_facade
```

한 번에 실행:

```bash
python manage.py test ^
  app.tests.test_chatbot_prompt_builder ^
  app.tests.test_chatbot_local_engine ^
  app.tests.test_chatbot_service ^
  app.tests.test_latest_feed ^
  app.tests.test_vectorize_chromadb ^
  app.tests.test_ai_facade
```

---

## 🌐 주요 접속 경로

로컬 개발 환경 기준: `http://localhost:8000`

### 1. 고객 서비스

- 서비스 시작/로그인: `/customer/`
- 최신 헤어 트렌드 페이지: `/customer/trend/`
- 스타일 취향 설문: `/customer/survey/`
- 페이스 촬영: `/customer/camera/`
- AI 분석 결과 및 추천: `/customer/recommendations/`

### 2. 파트너 센터

- 파트너 로그인: `/partner/`
- 디자이너 선택: `/partner/designer-select/`
- 통합 관리자 대시보드: `/partner/dashboard/`
- 디자이너 대시보드: `/partner/staff/`

---

## ⚙️ 환경 설정

### 스케줄러

- `ENABLE_TREND_SCHEDULER`
- `TREND_SCHEDULER_TIMEZONE`
- `TREND_SCHEDULER_WEEKLY_DAY`
- `TREND_SCHEDULER_WEEKLY_HOUR`
- `TREND_SCHEDULER_WEEKLY_MINUTE`
- `TREND_SCHEDULER_STEPS`

### 최신 트렌드 카드

- `TREND_LATEST_REMOTE_ENABLED`
- `TREND_LATEST_RUNPOD_TIMEOUT`
- `TREND_LATEST_RUNPOD_POLL_INTERVAL`

### 챗봇

- `MIRRAI_MODEL_CHATBOT_PROVIDER`
- `MIRRAI_MODEL_CHATBOT_URL`
- `MIRRAI_MODEL_CHATBOT_API_KEY`
- `MIRRAI_MODEL_CHATBOT_TIMEOUT`
- `MIRRAI_MODEL_CHATBOT_INCLUDE_SYSTEM_PROMPT`
- `MIRRAI_MODEL_CHATBOT_LOCAL_TOP_K`
- `MIRRAI_MODEL_CHATBOT_LOCAL_CHUNK_SIZE`
- `MIRRAI_MODEL_CHATBOT_LOCAL_CHUNK_OVERLAP`
- `MIRRAI_MODEL_CHATBOT_LOCAL_EMBED_DIM`

---

## ☁️ DevOps & 클라우드 아키텍처

본 프로젝트는 운영 관점에서 AWS 기반 구성을 염두에 두고 있습니다.

### 인프라 구성 요소

- **Orchestration**: AWS Elastic Beanstalk
- **Container Registry**: Amazon ECR
- **Storage**: Amazon S3
- **Database**: Supabase (Cloud PostgreSQL) + 로컬 SQLite
- **Infrastructure as Code**: Terraform

### 보안 가이드

- 민감한 값은 `.env` 및 외부 시크릿 저장소를 통해 관리
- 정적 파일은 WhiteNoise 기반 서빙
- 로컬 생성물과 런타임 산출물은 `.gitignore`, `.dockerignore` 로 분리

---

## 🔁 CI/CD 파이프라인

기본 흐름:

1. `main` 브랜치 push
2. Docker 이미지 빌드
3. ECR 업로드
4. 배포 설정 갱신
5. Elastic Beanstalk 반영

---

## 🧭 헤더 네비게이션 로직

세션 상태에 따라 헤더와 진입 흐름이 달라집니다.

- 로그아웃 상태에서 분석 시작 시 파트너 로그인 흐름으로 이동 가능
- 관리자 세션 활성화 후 디자이너 선택 페이지로 진입 가능
- 디자이너 세션에서는 디자이너 대시보드 우선
- 고객/파트너 세션은 목적에 따라 분리 유지

최신 트렌드 페이지(`/customer/trend/`)는 고객/매장 관리자/디자이너 세션 모두 접근 가능합니다.

---

## 🧰 기술 스택

- **Framework**: Django 5.x, DRF
- **Frontend**: Vanilla JS, Responsive CSS, Chart.js, MediaPipe
- **Database**: Supabase (PostgreSQL), SQLite (Local), ChromaDB
- **Infra**: AWS Elastic Beanstalk, ECR, S3, GitHub Actions, Terraform

---

## 🧹 저장소 정리 기준

아래 항목들은 로컬 전용 산출물로 취급합니다.

- `.env`
- `backend/`
- `__pycache__/`
- 로컬 SQLite 파일
- `data/rag/`
- 로컬 로그 및 생성 스토리지

즉, 로컬 Chroma 저장소, raw trend 캐시, manifest, 임시 실행 산출물은 Git에 올라가지 않고, 실제 소스/문서/테스트 파일은 계속 관리 대상입니다.
