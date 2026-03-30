# [Report] MirrAI 서비스 플로우 및 API 연동 동기화 가이드

**작성일:** 2026년 3월 30일  
**대상:** 프론트엔드 및 백엔드 개발팀 전체  
**목적:** 전체 서비스 여정(User Journey)에 따른 페이지 이동, 버튼 인터랙션, API 파라미터 규격 동기화

---

## 1. 전체 서비스 흐름 (High-Level Flow)
1. **[고객] 정보 입력 및 인증** → **[고객] 성별 맞춤 설문** → **[고객] 페이스 스캔** → **[고객] AI 추천 결과 확인 및 상담 예약**
2. **[파트너] 로그인/보안 인증** → **[파트너] 관리 대시보드 (고객 목록 및 트렌드 분석)** → **[파트너] AI 시술 가이드 챗봇 활용**

---

## 2. 고객 페이지 (Customer Journey) 상세

| 단계 | 페이지 (URL) | 주요 액션 (버튼) | 다음 페이지 | 호출 API & 주요 파라미터 |
| :--- | :--- | :--- | :--- | :--- |
| **정보 입력** | `/customer/` | 분석하기 | `/customer/survey/{gender}/` | `POST /customer/` (form-data: `name`, `gender`, `age`, `phone`) |
| **설문 조사** | `/customer/survey/male/` 또는 `/female/` | 분석 및 촬영 시작 | `/customer/camera/` | `POST /api/v1/survey/` (JSON: `customer`, `q1`~`q6`) |
| **페이스 스캔** | `/customer/camera/` | 사진 촬영 → 분석 시작 | `/customer/result/` | `POST /api/v1/capture/upload/` (form-data: `customer_id`, `file`) |
| **결과 확인** | `/customer/result/` | 스타일 선택 → 상담 예약 | `/` (메인) | `POST /api/v1/analysis/consult/` (JSON: `recommendation_id`, `client_id`) |

---

## 3. 파트너/관리자 페이지 (Admin Journey) 상세

| 단계 | 페이지 (URL) | 주요 액션 (버튼) | 다음 페이지 | 호출 API & 주요 파라미터 |
| :--- | :--- | :--- | :--- | :--- |
| **보안 인증** | `/partner/` | PIN 입력 (4자리) | `/partner/dashboard/` | `POST /partner/verify/` (form-data: `pin`) |
| **대시보드** | `/partner/dashboard/` | 고객 상세보기 | (모달 노출) | `GET /api/v1/customers/{id}/` |
| **통계 분석** | `/partner/dashboard/` | 트렌드 리포트 탭 | (화면 전환) | `GET /api/v1/admin/trend-report/` |
| **시술 가이드** | (상시 노출 위젯) | 챗봇 질문 전송 | (채팅 버블) | `POST /api/v1/admin/chatbot/ask/` (JSON: `message`) |
| **파트너 가입** | `/partner/signup/` | 가입 완료 | `/partner/` | `POST /api/v1/admin/auth/register/` (JSON: `name`, `phone`, `store_name`, `password` 등) |

---

## 4. 백엔드-프론트엔드 싱크 체크포인트 (Sync Point)

### 4.1 데이터 형식 및 타입
- **연락처(Phone):** 모든 API에서 하이픈(`-`)을 제외한 숫자만 전송하는 것을 원칙으로 하며, 프론트엔드에서 포맷팅을 수행함.
- **성별(Gender):** `male`, `female` 소문자 문자열로 통일.
- **인증 토큰:** 관리자 API 호출 시 Header에 `Authorization: Bearer <token>` 필수 포함.

### 4.2 에러 핸들링
- **400 Bad Request:** 필드 유효성 실패 시 `{ "errors": { "field_name": ["error message"] } }` 구조를 기대함.
- **401 Unauthorized:** PIN 번호 불일치 혹은 토큰 만료 시 로그인 페이지로 리다이렉트 처리.

---
*본 문서는 현재 구현된 코드를 바탕으로 작성되었으며, 백엔드 API 명세 변경 시 즉시 업데이트가 필요합니다.*
