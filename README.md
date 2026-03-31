# 🪞 MirrAI (SKN22-Final-1Team-WEB)

AI 기반 퍼스널 헤어 스타일 분석 및 추천 솔루션, **MirrAI** 프로젝트 저장소입니다.
고객의 페이스 라인 분석과 개인별 스타일 취향을 결합하여 최적의 헤어스타일을 제안하며, 디자이너와의 스마트한 상담 환경을 제공합니다.

현재 구조는 **Django (MVT)** 아키텍처로 완전 통합되어 있으며, **AWS Elastic Beanstalk**을 통해 무중단 배포됩니다.

---

## 🌟 서비스 개요

- **고객(Customer) 여정**: 서비스 시작 ➡️ 개인정보 동의 ➡️ 취향 설문 ➡️ 페이스 스캔 ➡️ AI 분석 리포트 및 상담 예약
- **파트너(Partner) 관리**: 실시간 고객 검색, 상세 분석 이력 관리, 매장 트렌드 시각화 리포트 제공
- **시스템 관리(Admin)**: 데이터베이스 및 서비스 핵심 설정 제어 (Django Custom UI)
- **디자인 컨셉**: 소프트 미니멀리즘 + 에디토리얼 레이아웃 기반의 **반응형 웹(PC/Mobile)** 최적화

---

## ✨ 핵심 기능

- **정교한 스타일 설문**: 5가지 카테고리(길이, 분위기, 모발 상태, 컬러, 예산) 기반 취향 수집 및 벡터화
- **AI 페이스 분석**: 
  - **프론트엔드**: MediaPipe Face Landmarker를 활용한 실시간 얼굴 분석 및 **실시간 품질 체크리스트**, **3초 스마트 자동 촬영(Auto-capture)** 기능 제공
  - **백엔드**: OpenCV 기반 이미지 전처리 및 AI 엔진 연동을 통한 정밀 얼굴형 매칭 시스템- **데이터 보안 및 정책**:
  - 개인정보 수집 및 이용 동의 프로세스 강화 (#111)
  - 분석 결과 이미지 워터마크 및 캡처 방지 가이드 UI 적용
- **데이터 시각화**: Chart.js를 활용한 매장 내 인기 스타일 및 방문자 통계 분석 (#81)
- **통합 데모**: 모든 페이지 기능을 한눈에 확인하고 테스트할 수 있는 쇼케이스 제공

---

## 🏗️ 프로젝트 구조

```text
.
├── backend/                # Django 통합 서버 (핵심 아키텍처)
│   ├── app/                # 비즈니스 로직, API(v1), 뷰 및 데이터 모델
│   ├── mirrai_project/     # Django 프로젝트 설정 (WhiteNoise, 배포 설정)
│   ├── static/             # 정적 자산 (shared/, customer/, admin/ - Responsive CSS/JS)
│   ├── templates/          # HTML 템플릿 (MVT 통합 레이아웃)
│   ├── manage.py           # Django 관리 스크립트
│   └── requirements.txt    # 최적화된 파이썬 패키지 (WhiteNoise, Boto3 등)
├── docs/                   # DevOps 가이드 및 기술 문서
├── terraform/              # AWS 인프라 자동화 코드 (IaC)
├── .github/workflows/      # CI/CD 자동화 파이프라인 (GitHub Actions)
└── Dockerrun.aws.json      # Elastic Beanstalk Docker 배포 정의
```

---

## 🚀 로컬 실행 및 초기 설정

### 1) 패키지 설치 및 DB 초기화

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
```

트렌드 크롤링/정제/LLM 정제/ChromaDB 생성까지 로컬에서 같이 돌릴 경우:

```bash
cd backend
pip install -r requirements-trends.txt
playwright install chromium
```

### 2) 테스트 데이터 생성 (선택 사항)

로컬 테스트를 위한 관리자 및 고객 데이터를 자동으로 생성합니다.

```bash
python seed_test_data.py
```

### 3) 서버 실행

```bash
python manage.py runserver
# 또는 run_server.bat 실행
```

### 4) 주간 트렌드 최신화 실행

금요일 08:00 스케줄러에서는 Django management command만 호출하면 됩니다.

```bash
cd backend
python manage.py refresh_trends --mode runpod-pipeline
python manage.py refresh_trends --mode runpod-archive --build-local
python manage.py refresh_trends --mode runpod-archive --build-local --dry-run
```

`runpod-archive --build-local`은 로컬에서
`crawl -> refine -> llm_refine -> vectorize -> rebuild_styles`
를 먼저 수행한 뒤 ChromaDB 디렉터리를 tar.gz로 묶어 RunPod에 전달합니다.

프로젝트 내부 스케줄러를 별도 프로세스로 띄우려면:

```bash
cd backend
python manage.py run_trend_scheduler
```

오늘 한 번만 테스트하려면:

```bash
cd backend
python manage.py run_trend_scheduler --test-at "2026-03-27 11:30" --exit-after-test
```

기본 스케줄은 `매주 금요일 08:00 Asia/Seoul`이며, 기본 작업은
`crawl -> refine -> llm_refine -> vectorize -> runpod archive upload`입니다.
같은 이미지에서 웹 서버와 함께 실행하려면 `.env`에 `ENABLE_TREND_SCHEDULER=true`를 넣으면 됩니다.
운영 환경에 앱 인스턴스가 여러 대면 스케줄러는 한 인스턴스에만 켜야 중복 실행되지 않습니다.

---

## 🔗 주요 접속 경로 (Local Access Paths)

로컬 개발 환경(`http://localhost:8000`) 기준의 전체 페이지 맵입니다.

### **1. 고객 서비스 (Customer Journey)**
사용자가 개인화된 헤어 스타일 추천을 받는 여정입니다.
- **서비스 시작/로그인**: [http://localhost:8000/customer/](http://localhost:8000/customer/)
- **스타일 취향 설문**: [http://localhost:8000/customer/survey/](http://localhost:8000/customer/survey/)
- **페이스 정밀 스캔 (카메라)**: [http://localhost:8000/customer/camera/](http://localhost:8000/customer/camera/)
- **AI 분석 결과 및 추천**: [http://localhost:8000/customer/recommendations/](http://localhost:8000/customer/recommendations/)
- **로그아웃**: [http://localhost:8000/customer/logout/](http://localhost:8000/customer/logout/)

### **2. 파트너 센터 (Partner & Designer)**
샵 관리자와 디자이너가 고객 데이터를 관리하고 상담을 진행하는 영역입니다.
- **파트너 로그인/인증**: [http://localhost:8000/partner/login/](http://localhost:8000/partner/login/)
- **파트너 회원가입**: [http://localhost:8000/partner/signup/](http://localhost:8000/partner/signup/)
- **통합 관리 대시보드**: [http://localhost:8000/partner/dashboard/](http://localhost:8000/partner/dashboard/)

### **3. 시스템 및 데모 (Dev & Demo)**
- **통합 기능 쇼케이스**: [http://localhost:8000/demo/discovery/](http://localhost:8000/demo/discovery/)
- **장고 표준 관리자 (DB 제어)**: [http://localhost:8000/admin/](http://localhost:8000/admin/)
- **Interactive API 문서 (Swagger)**: [http://localhost:8000/docs/](http://localhost:8000/docs/)
- **시스템 상태 체크**: [http://localhost:8000/health/](http://localhost:8000/health/)

---

## 🔐 환경 설정 (Environment Variables)

배포 및 실행을 위해 다음 변수들이 설정되어야 합니다. (EB 콘솔 또는 `.env` 파일)

| 변수명                        | 설명              | 비고                       |
| :---------------------------- | :---------------- | :------------------------- |
| `DEBUG`                     | 디버그 모드 여부  | 운영 환경 반드시 `False` |
| `ALLOWED_HOSTS`             | 접속 허용 호스트  | `*` 또는 도메인          |
| `SUPABASE_URL`              | API 주소          | Supabase 연동 필수         |
| `SUPABASE_SERVICE_ROLE_KEY` | 관리자 보안 키    | 외부 노출 금지             |
| `MIRRAI_AI_SERVICE_URL`     | AI 분석 서버 주소 | 얼굴 분석 엔진 엔드포인트  |

---

## ☁️ DevOps & 클라우드 아키텍처

본 프로젝트는 고가용성과 관리 편의성을 위해 **AWS 기반의 클라우드 네이티브 아키텍처**를 채택하고 있습니다.

### **인프라 구성 요소 (Architecture)**
- **Orchestration**: AWS Elastic Beanstalk (Docker Platform)를 활용한 자동 확장 및 로드 밸런싱
- **Container Registry**: Amazon ECR을 통한 안전한 Docker 이미지 관리
- **Storage**: Amazon S3를 사용하여 사용자 업로드 이미지 및 배포 버전 관리
- **Database**: Supabase (Cloud PostgreSQL)를 메인 DB로 활용
- **Infrastructure as Code**: Terraform을 통해 VPC, ECR, S3 등 모든 리소스를 코드로 정의 및 관리

### **보안 가이드 (Security)**
- **IAM OIDC**: GitHub Actions와의 연동 시 고정된 액세스 키 대신 OIDC를 사용하여 보안 강화
- **환경 변수 관리**: 민감한 정보는 AWS SSM Parameter Store 및 EB Environment Properties를 통해 안전하게 주입
- **Static Serving**: WhiteNoise 라이브러리를 활용하여 Django 내에서 효율적인 정적 파일 서빙 및 보안 유지

---

## 📦 CI/CD 파이프라인

본 프로젝트는 **GitHub Actions**와 **AWS**를 연동하여 완전 자동화된 배포 파이프라인을 구축하였습니다.

### **배포 워크플로우 (GitHub Actions)**
1.  **Trigger**: `main` 브랜치에 코드 Push 발생 시 가동 (backend 소스 및 배포 설정 변경 시)
2.  **Build**: `backend/Dockerfile`을 기반으로 Docker 이미지 빌드
3.  **Registry**: 빌드된 이미지를 **Amazon ECR**에 업로드 (이미지 태그는 Git SHA 활용)
4.  **Configuration**: 최신 이미지 URI를 `Dockerrun.aws.json`에 자동 주입
5.  **Deployment**: **AWS Elastic Beanstalk** 환경에 새로운 애플리케이션 버전 생성 및 업데이트 트리거
6.  **Monitoring**: 배포 완료 상태를 감시하여 최종 성공 여부 확인

### **인프라 구성 (IaC)**
- **Terraform**: S3, ECR, VPC 등 핵심 AWS 리소스를 코드로 관리하여 일관된 인프라 환경 보장
- **AWS OIDC**: 액세스 키 노출 없는 안전한 GitHub-AWS 인증 연동

---

## 🛠️ 기술 스택

- **Framework**: Django 5.0 (MVT), DRF
- **Frontend**: Vanilla JS, Responsive CSS3, Chart.js
- **Middleware**: WhiteNoise (Static serving)
- **Database**: Supabase (PostgreSQL), SQLite (Local)
- **Infra**: AWS Elastic Beanstalk, ECR, S3, GitHub Actions

---

## 🔑 로컬 테스트 계정 정보 (Local Test Accounts)

로컬 환경(`seed_test_data.py` 실행 시 생성됨)에서 테스트에 사용할 수 있는 계정 정보입니다.

### **1. 파트너/관리자 (Partner/Admin)**

- **접속 경로**: [http://localhost:8000/partner/](http://localhost:8000/partner/)
- **계정 1**: `01012345678` / `partner1234` (기본 관리자)
- **계정 2**: `01011112222` / `testpartner123` (테스트 파트너)
- **역할**: 대시보드 관리, 상담 신청 확인, 스타일 통계 리포트 조회

### **2. 고객 (Customer)**

- **접속 경로**: [http://localhost:8000/customer/](http://localhost:8000/customer/)
- **테스트 고객 1**: `01099998888` (홍길동)
- **테스트 고객 2**: `01033334444` (김철수)
- **설명**: 전화번호 입력 기반으로 접근하며, 설문조사 및 카메라 분석 기능을 테스트할 수 있습니다.
