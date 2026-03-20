# SKN22-Final-1Team-WEB

MirrAI 프로젝트 저장소입니다.  
현재 구조는 `FastAPI 백엔드 + Customer/Admin 프론트엔드(Vite 빌드)`이며, 배포는 Elastic Beanstalk 기준으로 구성되어 있습니다.

## 프로젝트 구조

```text
.
├─ backend/                 # FastAPI API 서버
│  ├─ main.py
│  ├─ requirements.txt
│  └─ Dockerfile
├─ frontend/
│  ├─ customer/
│  │  ├─ index.html         # 고객 앱 엔트리
│  │  └─ web/               # 고객 앱 소스(Vite)
│  ├─ admin/
│  │  ├─ index.html         # 관리자 앱 엔트리
│  │  └─ app/               # 관리자 앱 소스(Vite)
│  └─ shared/               # 공통 스타일/스크립트
├─ .github/workflows/
│  └─ deploy.yml            # ECR + Elastic Beanstalk 배포 워크플로우
└─ Dockerrun.aws.json       # EB 단일 Docker 배포 정의
```

## 로컬 실행

### 1) Backend (FastAPI)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

- API 문서: `http://localhost:8000/docs`
- 헬스체크: `http://localhost:8000/health`

### 2) Frontend 빌드

고객 앱:
```bash
cd frontend/customer/web
npm install
npm run build
```

관리자 앱:
```bash
cd frontend/admin/app
npm install
npm run build
```

정적 파일 서빙:
```bash
cd frontend
python -m http.server 3001
```

- 고객 화면: `http://localhost:3001/customer/index.html`
- 관리자 화면: `http://localhost:3001/admin/index.html`

## Elastic Beanstalk 배포

배포 파이프라인은 GitHub Actions에서 아래 순서로 동작합니다.

1. OIDC로 AWS 인증
2. `backend/` Docker 이미지 빌드
3. ECR 푸시
4. `Dockerrun.aws.json`에 이미지 URI 주입
5. `deploy.zip` 생성 후 EB Application Version 등록
6. Environment 업데이트 및 완료 대기

필수 GitHub Secrets:

- `AWS_OIDC_ROLE_ARN`
- `EB_APPLICATION_NAME`
- `EB_ENVIRONMENT_NAME`
- `ECR_REPOSITORY_NAME`

## 참고

- 민감정보는 `.env`에 보관하고 저장소에 커밋하지 않습니다.
- `node_modules`, 빌드 산출물(`dist`), 로컬 로그는 `.gitignore`로 제외됩니다.
