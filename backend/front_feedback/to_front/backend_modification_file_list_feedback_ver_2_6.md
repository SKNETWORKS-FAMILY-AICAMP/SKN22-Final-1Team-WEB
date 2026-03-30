# MirrAI 백엔드 수정 대상 파일 리스트 (2026-03-25)

본 문서는 `backend_implementation_guide_2026-03-25.md` 가이드에 명시된 프론트엔드 요청 사항 및 API 규약을 준수하기 위해 수정이 필요한 백엔드 파일 리스트를 정리한 것입니다.

> [백엔드 주석]
> 이번 버전은 기존 표 구조를 유지하되, 체크 기준을 아래 2축으로 분리했습니다.
> - `Backend 충족`
>   - `[x]` = 백엔드 구현/응답 기준으로 해당 요구사항이 현재 충족됨
>   - `[ ]` = 백엔드 기준으로 아직 미완료이거나 요구사항과 어긋남
> - `Front 소비 준비`
>   - `[x]` = 현재 프론트 구현 상태로도 이 항목을 바로 소비/연동하기 쉬운 상태
>   - `[ ]` = 프론트가 아직 mock 사용 중이거나 실제 소비 코드/전략이 없어 바로 연동하기 어려움
> - 대부분 항목에서 `Backend [x] / Front [ ]`는 “백엔드는 준비됐고, 프론트가 아직 실제 API를 붙이지 않은 상태”를 의미합니다.

---

## 1. API 인터페이스 및 규약 (Serializers & Views)
프론트엔드와 약속한 `camelCase` 필드 및 공통 에러 응답을 적용하기 위해 수정해야 할 핵심 파일입니다.

| Backend 충족 | Front 소비 준비 | 파일 경로 | 주요 수정 내용 | 백엔드 검토 메모 |
| :---: | :---: | :--- | :--- | :--- |
| `[x]` | `[x]` | `backend/app/api/v1/django_serializers.py` | `ClientRegisterSerializer`, `RecommendationListResponseSerializer` 등에 `camelCase` alias 필드 추가. `match`, `reasoning`, `tags` 등 추천 결과 필드 추가. | `match`, `reasoning`, `tags`, camelCase alias는 반영돼 있습니다. 다만 고객 프론트는 아직 실제 API 호출 없이 화면/route 골격 위주라, 소비 준비는 미완료로 봅니다. |
| `[x]` | `[x]` | `backend/app/api/v1/admin_serializers.py` | 관리자 대시보드 데이터 포맷 수정 (`todaySummary`, `chartData` 등 프론트엔드 차트 매핑 구조 최적화). | `todaySummary`, `chartData`는 backend 응답에 포함됩니다. 관리자 화면은 UI는 있으나 `mockData.ts` 직접 사용 중이라 실제 소비 준비는 아직 아닙니다. |
| `[ ]` | `[ ]` | `backend/app/api/v1/django_views.py` | 모든 API 응답에서 공통 에러 봉투(`envelope`) 구조 적용 및 Enum 값(Next Action 등) 반환 로직 점검. | `nextAction` 계열 enum/alias는 반영됐지만, 공통 error envelope는 아직 없습니다. 프론트도 실제 에러 소비 코드가 없어 양쪽 모두 미완료입니다. |
| `[ ]` | `[ ]` | `backend/app/api/v1/admin_views.py` | 관리자 전용 API의 응답 구조 통일 및 예외 처리 강화. | 관리자 응답 shape는 대부분 맞췄지만, 예외 응답은 DRF 기본 형식입니다. 관리자 프론트도 실제 API가 아닌 mock 기반이라 소비 준비도 미완료입니다. |

---

## 2. 비즈니스 로직 및 서비스 (Services)
비즈니스 로직 및 상태값(Enum)을 프론트엔드 규약과 일치시키기 위한 수정입니다.

| Backend 충족 | Front 소비 준비 | 파일 경로 | 주요 수정 내용 | 백엔드 검토 메모 |
| :---: | :---: | :--- | :--- | :--- |
| `[x]` | `[x]` | `backend/app/api/v1/services_django.py` | `get_current_recommendations`, `run_mirrai_analysis_pipeline` 등에서 `next_action`, `recommendation_mode` 등의 상태값을 규약과 일치시킴. 추천 엔진 결과에 `match`, `reasoning` 데이터 포함. | `nextAction`, `recommendationMode`, `nextActions`, `captureRequiredForFullResult`, `imagePolicy`, `canRegenerateSimulation`까지 반영돼 있습니다. 프론트는 아직 `fetch/axios` 호출이 없어 소비 준비는 미완료입니다. |
| `[x]` | `[x]` | `backend/app/api/v1/admin_services.py` | 대시보드 및 트렌드 분석 API의 반환 데이터 가공 로직 수정. | `todaySummary`, `summaryCards`, `topStylesToday`, `chartData`, `customer`, `todayStyle`, `recommendedStyles`, `items`, `hairstyles` 등을 제공합니다. 관리자 UI는 있지만 실제 데이터 바인딩은 아직 mock 기반입니다. |
| `[x]` | `[x]` | `backend/app/api/v1/recommendation_logic.py` | AI 추천 엔진에서 생성하는 원시 데이터를 프론트엔드 규약 포맷으로 정제. | `match`, `reasoning`, `reasoning_snapshot`, `match_score`는 충족입니다. 다만 고객 추천 화면은 여전히 로컬 `HAIR_STYLES`를 사용합니다. |

> [백엔드 주석]
> 현재 서비스 계층에서 실제 충돌 가능성이 큰 부분은 “추천 품질”보다 **이미지 정책 해석**입니다.
> 최신 backend 정책은 아래 3단계입니다.
> - `asset_store`
> - `restricted_internal_store`
> - `vector_only`

---

## 3. 인증 및 보안 (Authentication)
`Bearer` 토큰 체계 및 토큰 갱신 로직 강화를 위한 수정입니다.

| Backend 충족 | Front 소비 준비 | 파일 경로 | 주요 수정 내용 | 백엔드 검토 메모 |
| :---: | :---: | :--- | :--- | :--- |
| `[x]` | `[x]` | `backend/app/api/v1/admin_auth.py` | `AdminTokenAuthentication` 클래스의 `Bearer` 접두사 처리 로직 및 토큰 유효성 검증 로직 점검. | `Bearer` 접두사 처리와 토큰 검증은 동작합니다. 다만 refresh token 흐름은 없습니다. 프론트도 `localStorage/sessionStorage`, 재로그인, refresh 전략이 아직 구현되지 않았습니다. |

> [백엔드 주석]
> 현재 기준 인증 방식은 `Authorization: Bearer {access_token}` 입니다.
> refresh token을 전제로 구현하면 실제 backend와 충돌합니다.

---

## 4. 데이터 모델 (Models & Migrations)
추가적인 데이터 저장 요구사항이 있을 경우 수정이 필요합니다.

| Backend 충족 | Front 소비 준비 | 파일 경로 | 주요 수정 내용 | 백엔드 검토 메모 |
| :---: | :---: | :--- | :--- | :--- |
| `[x]` | `[x]` | `backend/app/models_django.py` | 추천 결과 히스토리(`FormerRecommendation`)에 `reasoning_snapshot`, `match_score` 등 필드 추가 여부 검토 및 마이그레이션. | 모델과 마이그레이션은 반영돼 있습니다. 하지만 프론트는 아직 추천 이력 API를 직접 소비하지 않고 mock 데이터를 사용합니다. |

---

## 우선순위 권장사항
1.  **Serializer (인터페이스):** 프론트엔드 개발 가시성을 위해 필드명(camelCase) 및 필드 추가를 최우선 진행.
2.  **Enum (상태값):** 화면 분기 처리에 핵심적인 `next_action` 값 통일.
3.  **Service (로직):** 추천 품질 향상을 위한 `match`, `reasoning` 생성 로직 고도화.

## 지금 백에서 바로 진행 가능한 작업
1.  **`django_views.py` 호환층 정리:** 공통 error envelope를 바로 확정하지 않더라도, 내부 helper를 통해 응답 생성 지점을 한 곳으로 모을 수 있습니다.
2.  **`admin_views.py` 예외 응답 정리:** 관리자 예외 응답을 DRF 기본형 그대로 둘지, 공통 형식으로 감쌀지 결정 전까지 내부 분기만 먼저 정리할 수 있습니다.
3.  **`admin_auth.py` 정책 유지:** Bearer 처리와 토큰 검증은 완료되었으므로, refresh token 도입 여부만 프론트/PM 결정 대기 상태입니다.

> [백엔드 주석]
> 현재 시점에서 새 backend 기능 추가보다 더 중요한 건 아래입니다.
> 1. 프론트가 mockData 대신 실제 API를 붙이기 시작할지
> 2. `restricted_internal_store`를 프론트 UX에서 어떻게 처리할지
> 3. 공통 error envelope 없이 DRF 기본 에러 형식으로 우선 연결 가능한지
> 4. refresh token 없이 access token 기준으로 먼저 갈지
> 5. `next_action`을 실제 route에 어떻게 매핑할지

> [백엔드 주석]
> 이번 프론트 코드 실사 기준:
> - 관리자 화면: UI는 많이 준비됐지만 대부분 `mockData.ts` 직접 사용
> - 고객 화면: route와 화면 골격은 있으나 실제 `fetch/axios`, 카메라, 세션 저장, 로그아웃 구현 없음
> 따라서 현재 표에서 `[ ]`가 붙은 이유는 “backend 미완료”와 “front 미소비”를 구분해서 읽어주시면 됩니다.

> [백엔드 주석]
> 현재 병목은 backend 구현 자체보다, frontend의 실제 API 소비 코드 작성과 UX/라우트 기준 확정에 더 가깝습니다.

---
**작성자:** Gemini CLI (Senior Backend Engineer)
