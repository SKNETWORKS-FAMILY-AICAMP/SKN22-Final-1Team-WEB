# ☁️ MirrAI 클라우드 배포 가이드 (DevOps)

이 가이드는 백엔드 개발 에이전트가 완성한 `Dockerfile`을 기반으로 AWS 클라우드에 배포하기 위한 환경 구성 및 CI/CD 자동화 파이프라인에 대한 안내입니다. 프리 티어와 비용 효율성을 고려하여 구성되었습니다.

---

## 🏗️ 1. 아키텍처 개요

- **컨테이너 저장소**: `AWS ECR` (Amazon Elastic Container Registry)
- **컴퓨팅 환경**: `AWS EC2` (t3.micro 권장, SSM 프로파일 적용)
- **CI/CD 파이프라인**: `GitHub Actions` (OIDC 인증 방식)
- **이미지 업로드 저장소**: `AWS S3` (mirrai-user-images-dev)

---

## 🛠️ 2. Terraform 인프라 프로비저닝 (`terraform/`)

프리 티어에 최적화된 최소 권한의 EC2 환경과 ECR 리포지토리를 생성합니다. 
`main.tf`와 `variables.tf`가 포함되어 있습니다.

### 실행 방법
```bash
cd terraform
terraform init
terraform plan
terraform apply
```

### 포함된 주요 리소스
1. **`aws_ecr_repository.backend_repo`**: Docker 이미지가 저장될 `mirrai-backend` 관리
2. **`aws_iam_role.ec2_role`**: EC2에서 ECR 이미지를 당겨오고(Pull) SSM(Session Manager)으로 원격 접속하기 위한 권한
3. **`aws_instance.backend`**: 
   - User Data(시작 스크립트)를 통해 인스턴스 부팅 직후 Docker 자동 설치 및 실행
4. **`aws_s3_bucket.image_bucket`**: 고객 얼굴 시뮬레이션 이미지를 저장할 S3 생성

> **ALB (Load Balancer) 관련**: 비용 절감을 위해 초기에는 EC2에 Elastic IP(탄력적 IP)를 붙여 직접 8000 포트로 서비스하는 것을 권장합니다. 프로덕션 스케일 확장이 필요할 때 ALB를 추가하기 쉽도록 분리 구조로 짰습니다.

---

## 🚀 3. CI/CD 파이프라인 (`.github/workflows/deploy.yml`)

GitHub 코드가 `main` 브랜치에 푸시되면 자동으로 빌드되고 AWS EC2에 배포되는 구조입니다.

### 동작 원리
1. **빌드 단계**: `backend` 폴더에서 Docker 이미지를 빌드하고 AWS ECR에 Push
2. **배포 단계**: AWS Systems Manager(SSM)를 통해 EC2 내부에 원격 명령(Run Command) 전달
   - ECR 로그인 ➡️ 새 이미지 Pull ➡️ 기존 컨테이너 Stop & rm ➡️ 새 컨테이너 Run

### 필수 GitHub Secrets 등록
GitHub 레포지토리 `Settings` > `Secrets and variables` > `Actions`에서 다음 항목을 등록하세요.

| Secret Name | 설명 |
|---|---|
| `AWS_OIDC_ROLE_ARN` | GitHub Actions가 OIDC로 임시 인증을 받을 IAM Role ARN |
| `AWS_ACCOUNT_ID` | 12자리 AWS 계정 ID (예: 123456789012) |
| `EC2_INSTANCE_ID` | 배포 타겟 서버(EC2)의 인스턴스 ID (예: i-0123456789abcdef) |

> 🔒 **OIDC 방식의 장점**: `AWS_ACCESS_KEY_ID` 같은 영구 자격 증명을 깃허브에 저장하지 않아 보안 사고를 원천 방지합니다. OIDC Role 셋업은 [AWS 공식 가이드](https://docs.aws.amazon.com/ko_kr/IAM/latest/UserGuide/id_roles_providers_create_oidc.html)를 참고하세요.

---

## 🔐 4. 앱 환경 변수(Secret) 보안 지침 

`main.py`나 데이터베이스에 접근할 때 필요한 민감한 정보(예: `DB_URL`, `OPENAI_API_KEY` 등)는 `docker run` 명령에 `-e` 옵션으로 추가하거나 **AWS System Manager Parameter Store**에 저장하여 런타임에 동적으로 주입받는 구조를 사용하세요. (코드 내 **Zero Hardcoding** 원칙 준수)
