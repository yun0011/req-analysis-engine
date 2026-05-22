---
name: slice
description: |
  AST 추출 결과를 기반으로 진입점을 열거하고, 각 진입점에서 효과 지점을 탐색하고,
  슬라이스를 생성한 뒤 Rule Record를 추출한다.
  추가로 클라이언트 컴포넌트를 직접 읽어 백엔드 EP가 없는 클라이언트 전용 동작(필터링, UI 조건 분기 등)을 CL Rule Record로 추출한다.
  요구사항 도출 파이프라인의 Phase 2. extract 스킬 완료 후 실행한다.
  "slice 실행", "진입점 찾기", "Rule Record 추출", "슬라이스 생성"이라고 하면 이 스킬을 사용한다.
---

# slice — 진입점 열거 → 효과지점 탐색 → Rule Record 추출 → 클라이언트 컴포넌트 슬라이싱

요구사항 도출 파이프라인의 **Phase 2**이다.
이 단계에서는 코드 사실만 추출한다. 의미 해석은 하지 않는다.

입력: `analysis_output/`, `global_call_graph.json`, (선택) 클라이언트 소스 파일
출력: `.req-analysis/1_entry_points.json`, `.req-analysis/2_effect_points.json`, `.req-analysis/3_rule_records.json`

---

## Step 1 — 진입점 열거

`analysis_output/`의 JSON 파일들과 `global_call_graph.json`을 읽는다.

Go 코드에서 진입점을 찾는 방법:

**라우터 등록 패턴 탐색**

`main` 함수 → 서버 부팅 함수 → 라우터 등록 함수의 체인을 Call Graph로 추적한다.
다음 패턴이 있는 함수 호출을 진입점 후보로 수집한다:

- `r.GET`, `r.POST`, `r.PUT`, `r.DELETE`, `r.PATCH` (gin)
- `v1.GET`, `v1.POST` 등 그룹 라우터
- `http.HandleFunc`, `mux.HandleFunc`
- `router.Handle`, `router.HandleFunc`
- `GET(path, handler)`, `POST(path, handler)` 패턴

**핸들러 함수 시그니처**

다음 파라미터를 가진 함수는 HTTP 핸들러 후보다:
- `(c *gin.Context)`
- `(w http.ResponseWriter, r *http.Request)`
- `(ctx echo.Context)`

**크론/스케줄러**

`cron.AddFunc`, `scheduler.Every`, `time.AfterFunc`가 있는 등록 지점도 진입점이다.

**결과 저장 형식**

`.req-analysis/1_entry_points.json`:
```json
{
  "entry_points": [
    {
      "ep_id": "EP-001",
      "type": "http",
      "method": "POST",
      "route": "/api/enrollments/{id}/confirm",
      "handler_symbol": "ConfirmEnrollment",
      "file": "service/enrollment.go",
      "registration_site": "router/router.go"
    },
    {
      "ep_id": "EP-002",
      "type": "cron",
      "schedule": "0 0 * * *",
      "handler_symbol": "RunDailyBatch",
      "file": "batch/daily.go"
    }
  ],
  "total": 0
}
```

---

## Step 2 — 효과 지점 탐색

각 진입점의 핸들러 함수에서 시작해 Call Graph를 따라 내려가며 효과 지점을 찾는다.

**수집 대상 효과 지점**

Write 기반:
- DB write: `tx.Exec`, `tx.QueryRow` + `INSERT/UPDATE/DELETE` 쿼리 포함
- 상태 필드 변경: 구조체 필드에 값을 직접 대입하는 코드
- 외부 API 호출: `http.Post`, `http.Get`, `client.Do`
- 이벤트/메시지 발행: `Publish`, `Emit`, `Send`, `Produce`
- 파일 생성: `os.Create`, `ioutil.WriteFile`
- 이메일/알림 전송: `smtp.SendMail`, `notification.Send`

Read 기반 (반드시 포함):
- DB read: `tx.Query`, `tx.QueryRow` + `SELECT` 쿼리
- 외부 API 조회

조회 기능도 "사용자에게 결과를 반환한다"는 관찰 가능한 효과이므로 수집한다.

**결과 저장 형식**

`.req-analysis/2_effect_points.json`:
```json
{
  "effect_points": [
    {
      "ep_id": "EP-001",
      "effect_id": "EFX-001-01",
      "kind": "db_write",
      "target": "enrollments.status := ENROLLED",
      "query_hint": "UPDATE enrollments SET status = ?",
      "file": "service/enrollment.go",
      "symbol": "ConfirmEnrollment",
      "line_hint": "tx.Exec(qry, ...)"
    },
    {
      "ep_id": "EP-001",
      "effect_id": "EFX-001-02",
      "kind": "publish",
      "target": "PublishEnrollmentConfirmed",
      "file": "service/enrollment.go",
      "symbol": "ConfirmEnrollment"
    }
  ]
}
```

---

## Step 3 — 슬라이스 생성 및 Rule Record 추출

각 효과 지점에 대해 슬라이스를 닫고 Rule Record를 추출한다.

### 슬라이스 단위 결정

**하나의 원자적 인과 연쇄 = 하나의 슬라이스**

같은 DB 트랜잭션(`tx`) 안에서 묶인 write들은 하나의 슬라이스다.
트랜잭션 밖의 side effect(이벤트 발행, 외부 API 호출)는 별도 슬라이스다.

```
EP-001 → ConfirmEnrollment
  [슬라이스 A] tx.Exec(status=ENROLLED) + tx.Exec(confirmedAt=now())  → 하나
  [슬라이스 B] PublishEnrollmentConfirmed                              → 별도
```

### Backward 슬라이스 (효과가 발생하기 위한 조건)

효과 지점에서 거슬러 올라가며:
- 어떤 guard 조건이 있는가 (`if ... return error`)
- 어떤 validation을 통과해야 하는가
- 어떤 상태 조건이 전제되어야 하는가

### Forward 슬라이스 (효과 이후에 발생하는 것)

효과 지점 이후:
- 추가 상태 변경이 있는가
- 후속 함수 호출이 있는가

### 에러 코드 추출

guard 조건과 에러 반환을 반드시 쌍으로 추출한다.

```go
// 이 코드에서:
if enrollment.Status != REQUESTED {
    return fmt.Errorf("ErrInvalidState: enrollment is not in requested state")
}
```

아래 형태로 추출:
```json
{
  "guard_condition": "enrollment.Status != REQUESTED",
  "error_name": "ErrInvalidState",
  "error_message": "enrollment is not in requested state",
  "http_status": 400
}
```

에러 타입 정의(`var ErrNotFound = errors.New(...)`)도 수집해 같은 형식으로 매핑한다.

### Rule Record 스키마

```json
{
  "rule_id": "EP-001-R-001",
  "entrypoint_id": "EP-001",
  "effect_id": "EFX-001-01",
  "subject_symbol": "enrollment",
  "state_field": "enrollment.status",
  "guard_predicates": [
    "enrollment.status == REQUESTED"
  ],
  "guard_failure": [
    {
      "guard_condition": "enrollment.status != REQUESTED",
      "error_name": "ErrInvalidState",
      "error_message": "enrollment is not in requested state",
      "http_status": 400
    }
  ],
  "success_writes": [
    { "field": "enrollment.status", "value": "ENROLLED" },
    { "field": "enrollment.confirmedAt", "value": "now()" }
  ],
  "side_effects": [
    { "kind": "publish", "target": "PublishEnrollmentConfirmed" }
  ],
  "domain_context": {
    "source_module": "service/enrollment.go",
    "route": "POST /api/enrollments/{id}/confirm",
    "primary_tables": ["enrollments"],
    "entity_types": ["Enrollment"]
  },
  "trigger": {
    "actor": "authenticated_user",
    "action": "confirm_enrollment"
  },
  "evidence": [
    { "file": "service/enrollment.go", "symbol": "ConfirmEnrollment" }
  ],
  "confidence": "high",
  "terminology_status": "ungrounded"
}
```

**confidence 기준**
- `high` — 코드에서 직접 읽힌 사실
- `medium` — 한 단계 호출 체인을 추론한 것
- `low` — 이름이나 부분 근거로 추측한 것

### Vue enrichment 적용

`vue_output/`가 존재하면 Rule Record 생성 시 다음을 보강한다:

- `vue_output/vuex_api_map.json`에서 같은 route에 매핑된 Vuex action 이름을 찾는다
- `vue_output/routes.json`에서 해당 route에 연결된 페이지의 `meta.roles`를 찾아 `trigger.actor`를 보강한다
  - `meta.roles: ["admin"]` → `actor: "admin_user"`
  - `meta.requiresAuth: true` → `actor: "authenticated_user"`
  - 없음 → `actor: "unauthenticated_user"`

**`client_behaviors.json` 형식 안내:**

`vue_output/client_behaviors.json`은 이제 타입 분류된 행동 목록이 아니라
컴포넌트별 **관찰 가능 출력의 raw 사실**을 담는다.

```json
{
  "components": [
    {
      "component": "views/archive/Archive.vue",
      "observable_facts": {
        "user_messages": [
          {
            "message": "첫번째 페이지입니다.",
            "preceding_context": "prevPage() { if (this.offsetList.length <= 1) {",
            "component": "views/archive/Archive.vue"
          }
        ],
        "conditional_renders": ["term.status !== 'FINISHED'"],
        "disabled_conditions": ["!isAdmin || term.status === 'FINISHED'"],
        "click_handlers": ["prevPage", "nextPage"],
        "polling": [{"interval_ms": 3000}],
        "has_loading_state": true,
        "lifecycle_calls": ["loadList"]
      }
    }
  ]
}
```

이 파일은 slice 단계에서 직접 소비하지 않는다. derive 단계에서 LLM이 해석한다.

**결과 저장**

`.req-analysis/3_rule_records.json`:
```json
{
  "rule_records": [ ...rule_record... ],
  "total": 0,
  "confidence_breakdown": {
    "high": 0,
    "medium": 0,
    "low": 0
  }
}
```

---

## Step 4 — 클라이언트 진입점 슬라이싱

**왜 독립된 단계인가**

백엔드는 HTTP 엔드포인트가 진입점이다. 클라이언트는 **라우트(페이지) × 사용자 행동**이 진입점이다.
두 진입점 체계는 겹치는 부분도 있고 겹치지 않는 부분도 있다.

- 백엔드 EP가 있는 행동 → 백엔드 Rule Record에 이미 잡힌다. 여기서는 `related_backend_ep`로 연결만 한다.
- 백엔드 EP가 없는 행동 → 여기서만 잡힌다. CL Rule Record로 뽑는다.
- 백엔드에서만 도는 작업 (크론, 배치) → Step 1에서 잡힌다. 여기서는 다루지 않는다.

클라이언트 분석 결과가 없으면 이 단계를 건너뛴다.

---

### Step 4-a — 클라이언트 진입점 열거

`vue_output/routes.json`에서 라우트 목록을 읽는다.
각 라우트 = 사용자가 진입할 수 있는 하나의 컨텍스트(페이지).

라우트별로 연결된 컴포넌트 파일을 직접 읽고, **사용자가 해당 페이지에서 취할 수 있는 모든 행동**을 열거한다.

행동 = 버튼 클릭, 폼 제출, 입력값 변경, 페이지 진입 시 자동 로드 등 사용자가 명시적·묵시적으로 트리거하는 모든 것.

---

### Step 4-b — 행동을 결과 유형으로 분류

열거한 행동 각각을 아래 결과 유형으로 분류한다.
분류 기준은 "이 행동이 사용자에게 어떤 결과를 낳는가"이다.

| 결과 유형 | 설명 | 백엔드 EP |
|---|---|---|
| `server_write` | 서버에 데이터를 생성·수정·삭제한다 | 있음 |
| `server_read` | 서버에서 데이터를 조회해 화면에 표시한다 | 있음 |
| `data_driven_action` | 서버 데이터를 재료로 콘텐츠에 접근한다 (파일 다운로드, 외부 URL 오픈) | 없거나 재활용 |
| `client_filter` | 서버 응답 전체를 받아 클라이언트에서 필터링·정렬한다 | 없음 |
| `client_feedback` | 비즈니스 상태에 따라 조건부로 UI를 표시하거나 비활성화한다 | 없음 |

**제외 유형 (CL Rule Record로 뽑지 않는다):**
- `loading`, `isOpen` 같은 순수 UX 상태 토글
- 라우터 이동만 하는 것 (페이지 이동 자체는 기능이 아님)
- 서버 데이터와 완전히 무관한 것

---

### Step 4-c — CL Rule Record 생성

분류 결과에 따라 CL Rule Record를 생성한다.

**`server_write` / `server_read`**: 백엔드 Rule Record에 이미 존재하므로 CL Rule Record를 새로 만들지 않는다. 대신 해당 백엔드 Rule Record의 `related_client_component` 필드에 컴포넌트 경로를 기록한다.

**나머지 유형**: 백엔드 EP가 없으므로 CL Rule Record로 뽑는다.

```json
{
  "rule_id": "CP-001-R-001",
  "source": "client",
  "component": "views/student/lecture_manage/Lecture.vue",
  "route": "/student/lecture",
  "actor": "student",
  "capability": "개설수업의 수업계획서를 조회할 수 있다",
  "behavior_type": "data_driven_action",
  "action_detail": {
    "trigger": "수업계획서 '보기' 버튼 클릭",
    "outcomes": [
      { "condition": "lecture.attachmentUrl 존재", "result": "외부 URL을 새 탭으로 오픈" },
      { "condition": "lecture.attachment 존재", "result": "lecture/get API 호출 후 PDF 다운로드" }
    ]
  },
  "related_backend_ep": "EP-031",
  "evidence": {
    "file": "components/Lecture.vue",
    "symbol": "downloadAttachment / openAttachmentUrl"
  },
  "confidence": "high",
  "terminology_status": "ungrounded"
}
```

`client_filter` 예시:
```json
{
  "rule_id": "CP-002-R-001",
  "source": "client",
  "component": "views/graduate/GraduateCandidate.vue",
  "route": "/admin/graduate/candidate",
  "actor": "admin",
  "capability": "졸업 후보를 졸업학기·배움과정·국문이름으로 필터링할 수 있다",
  "behavior_type": "client_filter",
  "filter_fields": [
    { "field": "student.graduated.semester", "label": "졸업학기" },
    { "field": "student.grade", "label": "배움과정" },
    { "field": "name.korean", "label": "국문이름" }
  ],
  "related_backend_ep": "EP-045",
  "evidence": {
    "file": "views/graduate/GraduateCandidate.vue",
    "symbol": "filteredList",
    "reason": "백엔드 EP의 request_schema에 필터 파라미터가 없음"
  },
  "confidence": "high",
  "terminology_status": "ungrounded"
}
```

---

**결과 병합**

CL Rule Record를 `.req-analysis/3_rule_records.json`의 `rule_records` 배열에 함께 저장한다.
`source: "client"` 필드로 백엔드 Rule Record와 구분한다.

---

## 완료 확인

- `.req-analysis/1_entry_points.json` — 진입점 목록
- `.req-analysis/2_effect_points.json` — 효과 지점 목록
- `.req-analysis/3_rule_records.json` — Rule Record 목록 (백엔드 + 클라이언트 통합)

confidence `low` 비율이 30% 이상이면 슬라이싱 범위나 Call Graph 품질에 문제가 있을 수 있다. 경고로 표시한다.
완료 후 EP 수, EFX 수, 백엔드 Rule Record 수, CL Rule Record 수를 구분해서 보고한다.
