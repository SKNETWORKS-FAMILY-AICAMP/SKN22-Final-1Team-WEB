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

## 🏗️ 비즈니스 계층 및 세션 구조

MirrAI는 매장 중심의 B2B2C 서비스 구조를 채택하여 체계적인 고객 관리를 지원합니다.

### **1. 계층 구조 (Hierarchy)**

- **파트너 (Partner / Store Owner)**: 매장 전체의 운영을 총괄하는 최상위 관리 계정입니다.
- **디자이너 (Designer / Staff)**: 매장에 소속되어 실제 고객 상담과 시술을 담당하는 전문가입니다.
- **고객 (Customer)**: 서비스를 이용하는 최종 사용자입니다.

### **2. 페이지별 독립 구동 모델 (Independent Page Operation)**

MirrAI의 파트너 센터는 사용자의 인증 상태에 따라 서로 다른 독립된 대시보드를 제공합니다.

- **[통합 대시보드] `/partner/dashboard/`**:
  - **대상**: 매장 관리자 (사업자 로그인 필수)
  - **주요 기능**: 전 소속 디자이너 관리, 매장 전체 고객 목록 통합 조회, 디자이너별 고객 필터링, 매장 전체 트렌드 분석 리포트.
- **[디자이너 대시보드] `/partner/staff/`**:
  - **대상**: 현장 디자이너 (디자이너 PIN 인증 필수)
  - **주요 기능**: 담당 고객 관리 전용 화면, 방문 기간별(30일/3개월 등) 타겟 고객 필터링, 개별 고객 상담 메모 관리.

### **3. 인증 및 세션 흐름 (Auth Flow)**

1. **파트너 인증**: `관리자 연락처`와 `비밀번호`로 매장 세션을 활성화합니다. (URL `next` 파라미터를 통한 유연한 리다이렉션 지원)
2. **디자이너 인증**: 활성화된 매장 내 디자이너 목록 중 본인을 선택하고 `4자리 PIN`으로 2차 인증을 완료합니다.
3. **분석 진입 최적화**: 로그아웃 상태에서 '분석 시작하기' 클릭 시, `매장 로그인 ➡️ 디자이너 인증 ➡️ 고객 분석` 단계가 연쇄적으로 진행됩니다.
4. **세션 보안**:
   - 브라우저 종료 시 모든 세션이 자동 만료되도록 설정 가능합니다.
   - 로그아웃 시 `session.flush()`를 호출하여 서버와 클라이언트의 모든 세션 데이터를 완전 파기합니다.

---

## ✨ 핵심 기능

- **정교한 스타일 설문**: 5가지 카테고리(길이, 분위기, 모발 상태, 컬러, 예산) 기반 취향 수집 및 벡터화 (가독성 높은 컴팩트 UI 적용)
- **AI 페이스 분석**:
  - **프론트엔드**: MediaPipe Face Landmarker를 활용한 실시간 얼굴 분석 및 **실시간 품질 체크리스트**, **3초 스마트 자동 촬영(Auto-capture)** 기능 제공
  - **백엔드**: OpenCV 기반 이미지 전처리 및 AI 엔진 연동을 통한 정밀 얼굴형 매칭 시스템 (사용성 개선을 위한 서버 측 검증 임계치 최적화 완료)
- **고도화된 파트너 대시보드**:
  - **데이터 관리**: 고객명, 담당 디자이너, 최근 방문 일수, 총 방문 횟수를 한눈에 파악.
  - **실시간 필터링**: 풀다운 메뉴를 통한 디자이너별 고객 쏘팅 및 방문 기간별(30일/3개월/6개월 등) 구간 필터링 제공.
- **데이터 보안 및 정책**:
  - 개인정보 보호를 위한 **휴대폰 번호 마스킹(`010-****-1234`)** 처리 적용.
  - 개인정보 수집 및 이용 동의 프로세스 강화 (#111).
- **데이터 시각화**: Chart.js를 활용한 매장 내 인기 스타일 및 방문자 통계 분석 (#81).

---

## 🏗️ 프로젝트 구조

```text
.
├── app/                    # 비즈니스 로직, API(v1), 뷰 및 데이터 모델
├── mirrai_project/         # Django 프로젝트 설정 (WhiteNoise, 배포 설정)
├── static/                 # 정적 자산 (shared/, customer/, admin/ - Responsive CSS/JS)
├── templates/              # HTML 템플릿 (MVT 통합 레이아웃)
├── seed_100_data.py        # 대량 테스트 데이터 생성 스크립트 (100명 고객 생성)
├── manage.py               # Django 관리 스크립트
├── requirements.txt        # 최적화된 파이썬 패키지 (WhiteNoise, Boto3 등)
├── docs/                   # DevOps 가이드 및 기술 문서
├── terraform/              # AWS 인프라 자동화 코드 (IaC)
├── .github/workflows/      # CI/CD 자동화 파이프라인 (GitHub Actions)
└── Dockerrun.aws.json      # Elastic Beanstalk Docker 배포 정의
```

---

## 🚀 로컬 실행 및 초기 설정

### 1) 패키지 설치 및 DB 초기화

```bash
pip install -r requirements.txt
python manage.py migrate
```

트렌드 크롤링/정제/LLM 정제/ChromaDB 생성까지 로컬에서 같이 돌릴 경우:

```bash
pip install -r requirements-trends.txt
playwright install chromium
```

### 2) 테스트 데이터 생성 (선택 사항)

로컬 테스트 및 대시보드 필터링 확인을 위한 데이터를 자동으로 생성합니다.

```bash
# 기본 시드 데이터
python manage.py seed_test_accounts

# 대량 테스트 데이터 (고객 100명, 디자이너 10명 및 방문 기록 생성)
python seed_100_data.py
```

- **테스트 계정**: `01080001000` (비밀번호: 1234)
- **디자이너 PIN**: 남성 `0001` / 여성 `0002`

### 3) 서버 실행

```bash
python manage.py runserver
# Windows 사용자의 경우 루트의 run_server.bat으로 자동 실행 가능
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

운영 환경에 앱 인스턴스가 여러 대면 스케줄러는 한 인스턴스에만 켜야 중복 실행되지 않습니다.

---

## 🔗 주요 접속 경로 (Local Access Paths)

로컬 개발 환경(`http://localhost:8000`) 기준의 전체 페이지 맵입니다.

### **1. 고객 서비스 (Customer Journey)**

- **서비스 시작/로그인**: [http://localhost:8000/customer/](http://localhost:8000/customer/)
- **스타일 취향 설문**: [http://localhost:8000/customer/survey/](http://localhost:8000/customer/survey/)
- **페이스 정밀 스캔 (카메라)**: [http://localhost:8000/customer/camera/](http://localhost:8000/customer/camera/)
- **AI 분석 결과 및 추천**: [http://localhost:8000/customer/recommendations/](http://localhost:8000/customer/recommendations/)

### **2. 파트너 센터 (Partner & Designer)**

- **파트너 로그인/인증**: [http://localhost:8000/partner/](http://localhost:8000/partner/)
- **디자이너 선택**: [http://localhost:8000/partner/designer-select/](http://localhost:8000/partner/designer-select/)
- **통합 관리 대시보드 (사업자)**: [http://localhost:8000/partner/dashboard/](http://localhost:8000/partner/dashboard/)
- **디자이너 전용 대시보드 (Staff)**: [http://localhost:8000/partner/staff/](http://localhost:8000/partner/staff/)

---

## 🔐 환경 설정 (Environment Variables)

| 변수명                              | 설명                      | 비고                       |
| :---------------------------------- | :------------------------ | :------------------------- |
| `DEBUG`                           | 디버그 모드 여부          | 운영 환경 반드시 `False` |
| `SUPABASE_URL`                    | API 주소                  | Supabase 연동 필수         |
| `SUPABASE_USE_REMOTE_DB`          | 원격 DB 사용 여부         | Supabase 연동 시 `True`  |
| `SESSION_EXPIRE_AT_BROWSER_CLOSE` | 브라우저 종료 시 로그아웃 | 보안 설정 `True` 권장    |

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

1. **Trigger**: `main` 브랜치에 코드 Push 발생 시 가동
2. **Build**: `backend/Dockerfile`을 기반으로 Docker 이미지 빌드
3. **Registry**: 빌드된 이미지를 **Amazon ECR**에 업로드
4. **Configuration**: 최신 이미지 URI를 `Dockerrun.aws.json`에 자동 주입
5. **Deployment**: **AWS Elastic Beanstalk** 환경 업데이트 트리거

---

## 🧭 헤더 네비게이션 로직 (Navigation Logic)

사용자의 현재 세션 상태에 따라 헤더 메뉴의 동작 방식이 동적으로 제어됩니다.

### **1. 분석 시작하기 (Customer Journey)**

사용자가 분석을 시작하려 할 때, 필수적인 인증 단계를 순차적으로 강제합니다.

- **로그아웃 상태**: `매장 로그인 페이지`로 이동 (로그인 후 디자이너 선택으로 자동 연결)
- **매장 로그인만 완료**: `디자이너 선택 페이지`로 즉시 이동 (인증 후 분석 페이지로 자동 연결)
- **모든 인증 완료**: `고객 분석 시작 페이지(/customer/)`로 즉시 이동

### **2. 파트너 센터 메뉴 (Admin/Designer Flow)**

로그인 전후의 목적지를 명확히 분리하여 업무 효율을 높입니다.

- **로그인 전**:
  - **디자이너**: 클릭 시 로그인 후 `디자이너 선택`으로 리다이렉트
  - **파트너 센터**: 클릭 시 로그인 후 `통합 대시보드`로 리다이렉트
- **로그인 후**:
  - **디자이너**: `디자이너 선택` 페이지로 직접 이동
  - **파트너 센터**: `통합 대시보드(/partner/dashboard/)`로 직접 이동
  - **특수 로직**: 디자이너 세션 상태에서 '파트너 센터' 클릭 시, **디자이너 세션만 선택적 파기** 후 관리자 대시보드로 전환 지원 (예정)

---

## 🛠️ 기술 스택

- **Framework**: Django 5.0 (MVT), DRF
- **Frontend**: Vanilla JS, Responsive CSS3, Chart.js, MediaPipe
- **Database**: Supabase (PostgreSQL), SQLite (Local), ChromaDB
- **Infra**: AWS Elastic Beanstalk, ECR, S3, GitHub Actions, Terraform
