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
- **AI 페이스 분석**: OpenCV 기반 전처리 및 AI 엔진 연동을 통한 얼굴형 매칭 시스템
- **데이터 보안 및 정책**: 
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

---

## 🔗 주요 접속 경로 (Access Paths)

- **통합 쇼케이스**: [http://localhost:8000/demo/discovery/](http://localhost:8000/demo/discovery/)
- **고객 서비스**: [http://localhost:8000/customer/](http://localhost:8000/customer/)
- **파트너 센터**: [http://localhost:8000/partner/login/](http://localhost:8000/partner/login/)
- **API 문서**: [http://localhost:8000/docs/](http://localhost:8000/docs/)

---

## 🔐 환경 설정 (Environment Variables)

배포 및 실행을 위해 다음 변수들이 설정되어야 합니다. (EB 콘솔 또는 `.env` 파일)

| 변수명 | 설명 | 비고 |
| :--- | :--- | :--- |
| `DEBUG` | 디버그 모드 여부 | 운영 환경 반드시 `False` |
| `ALLOWED_HOSTS` | 접속 허용 호스트 | `*` 또는 도메인 |
| `SUPABASE_URL` | API 주소 | Supabase 연동 필수 |
| `SUPABASE_SERVICE_ROLE_KEY` | 관리자 보안 키 | 외부 노출 금지 |
| `MIRRAI_AI_SERVICE_URL` | AI 분석 서버 주소 | 얼굴 분석 엔진 엔드포인트 |

---

## 🛠️ 기술 스택
- **Framework**: Django 5.0 (MVT), DRF
- **Frontend**: Vanilla JS, Responsive CSS3, Chart.js
- **Middleware**: WhiteNoise (Static serving)
- **Database**: Supabase (PostgreSQL), SQLite (Local)
- **Infra**: AWS Elastic Beanstalk, ECR, S3, GitHub Actions
