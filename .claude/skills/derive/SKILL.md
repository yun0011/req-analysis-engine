---
name: derive
description: |
  도메인 그룹과 필드 생애주기 제약을 바탕으로 기능을 도출하고, 명세 후보를 승격하고, 요구사항 문서를 재구성한다.
  두 번째 모델로 교차검증을 수행해 hallucination을 감소시킨다.
  요구사항 도출 파이프라인의 Phase 5. field 스킬 완료 후 실행한다.
  "derive 실행", "기능 도출", "요구사항 문서 생성", "명세 작성"이라고 하면 이 스킬을 사용한다.
---

# derive — 기능 도출 + 명세 후보 승격 + 요구사항 문서 재구성

요구사항 도출 파이프라인의 **Phase 4**이다.
코드 사실에서 자연어 요구사항으로 넘어가는 단계다. hallucination 위험이 가장 높은 구간이므로 교차검증을 적용한다.

입력: `.req-analysis/4_domain_groups.json`, `vue_output/` (선택)
출력: `.req-analysis/5_features/DG-{ID}.json`, `.req-analysis/6_structured_spec.json`, `.req-analysis/UI_requirements.md`

**vue_output 소비 우선순위**
- `display_labels.json` → FR의 `ui.display_labels` (상태값 한국어 라벨)
- `client_behaviors.json` observable_facts → FR의 `ui` 섹션 (백엔드 EP가 있는 경우)
- `client_only_reqs.json` → CL-* FR (백엔드 EP가 **없는** 순수 클라이언트 전용만)

---

## Step 0 — observable_facts 해석 (vue_output이 있을 때만)

`vue_output/client_behaviors.json`이 존재하면 기능 도출 전에 먼저 읽어 해석한다.

이 파일에는 Python이 추출한 **raw 사실**만 들어있다. `type` 필드로 미리 분류되지 않는다.
LLM이 raw 사실을 보고 "이것이 어떤 요구사항인가"를 직접 판단해야 한다.

**해석 방법:**

`observable_facts.user_messages`에는 각 메시지와 메시지가 호출된 앞 문맥이 함께 있다.

```json
{
  "message": "첫번째 페이지입니다.",
  "preceding_context": "prevPage() { if (this.offsetList.length <= 1) {"
}
```

`preceding_context`를 읽어 메시지의 의미를 판단한다:
- `if (offset === 0)` + "첫번째 페이지입니다." → **페이지네이션 경계 알림 요구사항**
- `if (!this.title)` + "제목을 입력해주세요." → **입력 유효성 검사 요구사항**
- `if (result.ok)` + "저장되었습니다." → **작업 성공 피드백** (별도 FR로 승격할지 판단)

`observable_facts.conditional_renders`는 `v-if`/`v-show` 조건이다.
연산자(`===`, `!==`, `&&`, `||`)가 포함된 것만 비즈니스 규칙 후보로 간주한다:
- `term.status !== 'FINISHED'` → **학기 상태 조건부 표시 요구사항**
- `loading` (단순 변수) → 노이즈, 무시

`observable_facts.disabled_conditions`는 `:disabled` 조건이다.
비즈니스 상태나 권한에 관련된 것만 포착한다:
- `!isAdmin || term.status === 'FINISHED'` → **Admin 전용 + 학기 종료 시 비활성화 요구사항**
- `loading` → 노이즈, 무시

`observable_facts.polling`은 `setInterval` 주기다.
→ **비동기 상태 반복 조회 UX 요구사항** 후보

해석 결과를 두 가지로 분류한다:

**A. 백엔드 FR과 연관 있는 것 → FR `ui` 섹션 통합 대상**

| observable_facts 항목 | FR ui 섹션 필드 |
|---|---|
| `user_messages` (if 조건 + 오류 메시지) | `ui.validation_messages` |
| `disabled_conditions` | `ui.disabled_conditions` |
| `polling` | `ui.polling` |
| `confirmation_guard` | `ui.confirmation_guard` |
| `conditional_renders` (비즈니스 상태 조건) | `ui.display_conditions` |

→ Step 1-d에서 해당 FR을 생성할 때 `ui` 섹션에 함께 넣는다.

**B. 백엔드 EP가 없는 순수 클라이언트 기능 → CL-* FR**

| 카테고리 | 설명 |
|---|---|
| `route_guard` | 라우트 접근 권한 제어 |
| `client_filter` | 클라이언트 측 데이터 필터링 |
| `pagination_ux` | 페이지네이션 경계 알림 (첫번째/마지막 페이지) |

`irreversibility_guard`(confirmation)와 `async_polling`은 대응하는 백엔드 FR이 있으므로 해당 FR의 `ui` 섹션으로 통합한다. CL-* FR로 분리하지 않는다.

**반복 패턴 처리:**
같은 메시지/조건이 여러 컴포넌트에서 반복되면 하나의 공통 요구사항으로 묶는다.
"첫번째 페이지입니다."가 11개 컴포넌트에서 나타나면 → `CL-PAGINATION-001` XC 후보 1개.

---

## Step 1 — 도메인 그룹별 기능 도출

각 도메인 그룹에 대해 순서대로 처리한다.

### 1-a. 진입점 목록에서 기능 후보 열거

진입점 이름은 코드 사실이므로 기능 후보의 1차 원료다.
route와 HTTP method에서 기능 후보를 문장으로 변환한다.

```
POST /api/enrollments              → 수강 신청을 생성할 수 있다
POST /api/enrollments/{id}/confirm → 수강 신청을 확정할 수 있다
GET  /api/enrollments              → 수강 신청 목록을 조회할 수 있다
DELETE /api/enrollments/{id}       → 수강 신청을 취소할 수 있다
```

기능 후보를 문장으로 만들 때 도메인 용어를 임의로 만들지 않는다. route 이름에서 읽히는 단어만 사용한다.

### 1-b. 각 기능 후보에 Rule Record 행동 정보 부착

해당 기능 후보에 연결된 클러스터에서 behavior를 추출한다.

```
기능 후보: 수강 신청을 확정할 수 있다
  preconditions:  enrollment.status == REQUESTED
  postconditions: enrollment.status := ENROLLED, confirmedAt := now()
  side_effects:   PublishEnrollmentConfirmed
  guard_failure:  status != REQUESTED → ErrInvalidState (400)
```

### 1-c. Grounding

도메인 용어를 부여하려면 코드에서 인용 가능한 근거가 있어야 한다.

**Grounding 가능한 근거 소스:**
- 변수명, 타입명, 함수명, 라우트명, 테이블명, 이벤트명
- 테스트 함수명
- 코드 주석
- Vue UI 문자열: `vue_output/client_behaviors.json`의 `observable_facts.user_messages[].message`
  (버튼 레이블, 알림 텍스트 등 사용자에게 직접 노출되는 문자열)
- Vue 조건부 렌더링: `observable_facts.conditional_renders`에서 도메인 용어 확인

**Grounding 결정 기준:**
- 여러 소스가 같은 용어를 가리키면 → `grounding_confidence: "high"`, 용어 부여
- 소스가 하나뿐이거나 모호하면 → `grounding_confidence: "medium"`
- 소스가 없거나 상충하면 → `grounding_confidence: "low"`, `terminology_status: "ungrounded"`, `blocked_items`에 기록

**절대 하지 말아야 할 것**: 코드에 없는 용어를 임의로 만들어 붙이는 것.

### 1-d. Feature 파일 생성

도메인 그룹별로 `.req-analysis/5_features/DG-{ID}.json`에 저장한다.

```json
{
  "domain_group": "DG-TERM",
  "features": [
    {
      "feature_id": "F-TERM-001",
      "capability": "학기 목록을 조회할 수 있다",
      "trigger": {
        "actor": "authenticated_user",
        "action": "POST /api/v1/term/list"
      },
      "behavior": {
        "preconditions": [],
        "postconditions": ["학기 목록을 반환해야 한다"],
        "side_effects": [],
        "guard_failure": []
      },
      "ui": {
        "display_fields": ["year", "semester", "status"],
        "display_labels": {
          "status": {
            "READY":    "준비중",
            "APPLYING": "수강신청 중",
            "ONGOING":  "학기 중",
            "FINISHED": "종강"
          },
          "semester": {
            "SPRING": "봄",
            "FALL":   "가을"
          }
        },
        "validation_messages": [],
        "disabled_conditions": [],
        "confirmation_guard": null,
        "polling": null
      },
      "evidence_refs": ["DG-TERM-C-001", "EP-046-R-001"],
      "grounding_confidence": "high",
      "terminology_status": "grounded",
      "blocked_items": []
    }
  ]
}
```

`ui` 섹션 작성 규칙:
- `display_fields`: response_schema 필드 중 화면에 실제로 표시되는 것만 선별한다. 내부 ID처럼 화면에 안 나오는 필드는 제외한다.
- `display_labels`: `display_labels.json`에서 해당 도메인의 상태값 매핑을 가져온다. 파일이 없으면 Vue template에서 직접 추출한다.
- `validation_messages`: `preceding_context`가 입력 검증 조건(`!this.title`, `!value`)인 user_messages만 포함한다.
- `disabled_conditions`: 비즈니스 상태나 권한 조건만 포함한다. `loading` 같은 UX 전용 조건은 제외한다.
- `ui` 섹션 전체가 비어있으면 `"ui": null`로 표기한다 (내부 API, 배치 작업 등).

---

## Step 2 — 교차검증

**이 단계가 교차검증을 수행하는 이유**

코드 사실에서 자연어 요구사항으로 넘어가는 이 단계가 hallucination이 가장 많이 발생한다. capability 문장, preconditions, postconditions을 LLM이 만들기 때문에 코드에 없는 내용이 섞일 수 있다.

**교차검증 절차**

1. Step 1에서 생성한 feature 파일들을 `draft_features`로 저장한다.

2. 동일한 domain_groups 데이터를 두 번째 모델에게 전달한다.
   프롬프트: "아래 도메인 그룹의 클러스터에서 기능 후보를 도출하라. capability는 route와 코드 사실에서만 추출하고, preconditions/postconditions는 Rule Record의 guard_predicates/success_writes에서만 추출하라. 코드에 없는 내용을 추가하지 마라."

3. 두 결과를 비교한다:
   - **capability 불일치**: 같은 기능을 다르게 표현한 경우 → 더 코드에 가까운 쪽을 채택, `cross_validation_note` 기록
   - **precondition/postcondition 불일치**: 한 모델만 언급한 조건이 있는 경우 → 코드에서 해당 조건 재확인, 없으면 제거
   - **한 모델만 기능을 도출한 경우**: `cross_validation_conflict: true`, `grounding_confidence: "low"` 강제

**불일치 처리**

불일치 항목은 feature에 `cross_validation_conflict: true`와 함께 두 모델의 결과를 모두 기록한다. 강제 병합하지 않는다.

---

## Step 3 — 요구사항 문서 재구성

모든 도메인 그룹의 feature 파일을 읽어 최종 문서로 재구성한다.

### 3-a. 의미상 동일한 규칙 병합

서로 다른 클러스터에서 나왔지만 같은 postcondition을 표현하면 하나의 FR로 통합한다.
evidence_refs는 두 클러스터의 것을 모두 유지한다.

### 3-b. 예외 결합

기본 규칙과 예외 규칙을 분리하지 않는다.
독자가 기본 규칙과 예외를 한 번에 볼 수 있게 같은 FR에 `exceptions` 필드로 붙인다.

### 3-c. 충돌 표시

상충하는 규칙은 강제 병합하지 않는다. `conflicts` 섹션에 기록한다.

예시:
```
DG-ENROLLMENT-C-02: REQUESTED 상태일 때만 확정 가능
DG-ENROLLMENT-C-22: 등록금 납부 상태이면 확정 가능
→ conflict, 사람이 판단 필요
```

### 최종 문서 형식

`.req-analysis/6_structured_spec.json`:
```json
{
  "structured_spec": {
    "domains": [
      {
        "domain": "Enrollment",
        "features": [
          {
            "id": "FR-ENROLLMENT-001",
            "capability": "수강 신청을 확정할 수 있다",
            "trigger": {
              "actor": "authenticated_user",
              "action": "confirm_enrollment"
            },
            "behavior": {
              "preconditions": [
                "신청 상태(REQUESTED)의 수강 신청에 대해서만 허용해야 한다"
              ],
              "postconditions": [
                "상태를 ENROLLED로 변경해야 한다",
                "확정 시각을 기록해야 한다"
              ],
              "side_effects": [
                "EnrollmentConfirmed 이벤트를 발행해야 한다"
              ],
              "guard_failure": [
                "신청 상태가 REQUESTED가 아닌 경우 ErrInvalidState(400) 반환"
              ]
            },
            "evidence_refs": ["DG-ENROLLMENT-C-001"],
            "exceptions": [],
            "cross_validation_conflict": false,
            "request_schema": { "struct": "confirmEnrollmentParam", "fields": [] },
            "response_schema": null,
            "ui": {
              "display_fields": ["id", "status", "confirmedAt"],
              "display_labels": {
                "status": {
                  "REQUESTED": "신청",
                  "ENROLLED":  "확정"
                }
              },
              "validation_messages": [],
              "disabled_conditions": [],
              "confirmation_guard": null,
              "polling": null
            }
          }
        ]
      }
    ],
    "cross_cutting": [
      {
        "id": "XC-AUTH-001",
        "type": "architectural_constraint",
        "statement": "모든 보호된 엔드포인트는 JWT 인증 guard를 통과해야 한다",
        "applies_to": ["FR-ENROLLMENT-*", "FR-PAYMENT-*"],
        "evidence_refs": ["..."]
      }
    ],
    "conflicts": [
      {
        "conflict_id": "CF-001",
        "description": "두 클러스터의 preconditions 상충",
        "option_a": "DG-ENROLLMENT-C-02: REQUESTED 상태일 때만 허용",
        "option_b": "DG-ENROLLMENT-C-22: 등록금 납부 상태이면 허용",
        "refs": ["DG-ENROLLMENT-C-02", "DG-ENROLLMENT-C-22"]
      }
    ],
    "unresolved": [
      "EnrollmentConfirmed가 외부 알림인지 내부 이벤트인지 불명확"
    ]
  },
  "cross_validation_summary": {
    "total_features": 0,
    "agreed": 0,
    "conflicted": 0
  }
}
```

---

---

## Step 4 — UI_requirements.md 렌더링

`6_structured_spec.json` 생성이 완료된 직후 실행한다.

**목적**: `6_structured_spec.json`의 `ui` 섹션을 사람이 읽을 수 있는 마크다운으로 렌더링한다.
새로운 정보를 추가하지 않는다 — `6_structured_spec.json`의 부분집합을 다른 형식으로 표현하는 것이다.

**렌더링 대상**:
- `ui != null`인 모든 FR의 화면 표시 규칙
- CL-* (클라이언트 전용) FR
- UI에 영향을 주는 cross_cutting 항목

**출력 형식** `.req-analysis/UI_requirements.md`:

```markdown
# UI 요구사항

> 이 문서는 6_structured_spec.json의 ui 섹션을 렌더링한 뷰입니다.
> 정규 소스는 6_structured_spec.json이며, 이 문서는 읽기 전용입니다.

---

## {도메인명} (DG-XXX)

### FR-XXX-001 — {capability}

**표시 필드**

| 필드 | 표시명 |
|------|--------|
| status | 상태 |
| createdAt | 등록일 |

**상태값 표시 라벨**

| 코드값 | 표시 텍스트 |
|--------|------------|
| READY | 준비중 |
| APPLYING | 수강신청 중 |

**입력 유효성 검사 메시지**

- 제목을 입력해주세요. (`title` 필드 비어있을 때)

**비활성화 조건**

- Admin 권한이 없거나 학기가 종료된 경우 버튼 비활성화

**불가역 작업 확인 가드**

- 확인 텍스트: "폐강하겠습니다." 입력 필요

**비동기 폴링**

- 간격: 3000ms, 종료 조건: 상태가 PENDING이 아닐 때

---

## 클라이언트 전용 기능 (CL-*)

### CL-XXX-001 — {capability}

...

---

## 횡단 UI 제약

- XC-AUTH-001: 인증되지 않은 사용자는 모든 관리 화면에 접근할 수 없다
```

**렌더링 규칙**:
- `ui == null`인 FR (내부 API, 배치 작업)은 포함하지 않는다
- 비어있는 섹션(`validation_messages: []` 등)은 해당 소제목을 생략한다
- `display_labels`는 코드값 → 표시 텍스트 테이블로 렌더링한다
- 도메인 순서는 `6_structured_spec.json`의 `domains` 배열 순서를 따른다

---

## 완료 확인

- 모든 도메인 그룹에 최소 하나의 FR이 생성됐는가
- `ungrounded` 상태로 남은 feature가 있으면 목록을 보고한다
- conflict 항목을 별도로 목록화해서 보고한다
- 교차검증 불일치 비율과 대표 사례를 요약해서 보고한다
- `UI_requirements.md`가 생성됐는가 — `ui != null`인 FR 수와 파일 내 섹션 수가 일치하는지 확인한다
