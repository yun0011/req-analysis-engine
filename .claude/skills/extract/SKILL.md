---
name: extract
description: |
  레거시 코드베이스에서 백엔드 AST, 클라이언트 정적 분석, Call Graph를 추출한다.
  백엔드 소스를 파싱해 structs/functions/db_access/error_messages를 수집하고,
  클라이언트 소스에서 API 매핑/라우트 권한/컴포넌트 행동 패턴/상태 라벨/UI 구조를 정적 분석한다.
  마지막으로 내부 함수 간 Call Graph를 생성한다.
  요구사항 도출 파이프라인의 Phase 1. slice 스킬 실행 전에 반드시 먼저 실행해야 한다.
  "extract 실행", "AST 추출", "코드 파싱"이라고 하면 이 스킬을 사용한다.
---

# extract — AST + 클라이언트 정적 분석 + Call Graph 추출

요구사항 도출 파이프라인의 **Phase 1**이다.
이 단계는 결정론적이다. LLM 해석 없이 Python 스크립트가 코드 구조를 파일로 저장한다.

---

## 실행 순서

### Step 1 — Go AST 추출

`main.py`를 실행한다.

```bash
python main.py
```

`target_legacy_code/` 아래의 모든 `.go` 파일을 tree-sitter-go로 파싱해
`analysis_output/` 폴더에 파일별 JSON을 생성한다.

각 JSON의 구조:
```json
{
  "file_path": "...",
  "structs": [
    {
      "name": "Enrollment",
      "body": "struct { ... }",
      "fields": [
        { "name": "Status", "type": "RegistrationStatus", "tag": "json:\"status\"" }
      ]
    }
  ],
  "functions": [
    {
      "function_name": "ConfirmEnrollment",
      "signature": "func (s *Service) ConfirmEnrollment(id int) error",
      "calls": ["validateEnrollment", "publishEvent"],
      "db_access": ["tx.Exec(qry, ...)"],
      "error_messages": ["ErrInvalidState"]
    }
  ]
}
```

실행 후 몇 개 파일이 생성됐는지 확인한다.

---

### Step 2 — 클라이언트 정적 분석

`extract_client.py`를 실행한다.

```bash
python extract_client.py
```

`target_legacy_code/pati-client/` 아래의 소스를 정적 분석해 `vue_output/` 폴더에 5개 파일을 생성한다.

**이 스크립트가 하는 일:**

1. `src/api/client.js` 파싱 → 60개 메서드 × (HTTP method + URL) 매핑
2. `src/router/index.js` 파싱 → 라우트별 `needsPermission` 비트마스크 디코딩 + 컴포넌트-라우트 매핑
   - `1=Admin`, `2=Employee`, `4=Professor`, `8=Student`
3. 모든 `.vue` 파일 처리 → 컴포넌트별 구조 정보 수집 (`route_paths`, `vuex_dispatches`, `api_calls`, `role_guards`)
4. 클라이언트 전용 행동 패턴 추출 (AI 없이 정적으로)
5. **상태값 한국어 표시 라벨 추출** → `display_labels.json`
   - `<option :value="'READY'">준비중</option>` 패턴
   - `v-if="status === 'FINISHED'"` 옆 텍스트 노드
   - JS 상수 매핑 (`const STATUS_LABELS = { READY: '준비중', ... }`)
6. 클라이언트 전용 요구사항 후보 생성 (백엔드 EP가 없는 순수 클라이언트 기능만)

**산출물 상세:**

`vue_output/api_map.json` — client.js 메서드 → EP 매핑
```json
{
  "methods": [
    {
      "method_name": "getEnrollments",
      "http_method": "GET",
      "url": "/api/registrations",
      "ep_id": "EP-031"
    }
  ]
}
```

`vue_output/routes.json` — 라우트별 권한
```json
{
  "routes": [
    {
      "path": "/student/enrolment",
      "name": "Enrolment",
      "required_roles": ["Student"],
      "required_auth": true,
      "component": "Enrolment.vue"
    }
  ]
}
```

`vue_output/component_map.json` — 컴포넌트 → API 호출 체인
```json
{
  "components": [
    {
      "component": "views/student/lecture_manage/enrolment/Enrolment.vue",
      "component_name": "Enrolment",
      "route_paths": ["/student/enrolment"],
      "vuex_dispatches": ["getLectureList"],
      "api_calls": ["getRegistrations", "addFallRegistration", "addSpringRegistration"],
      "role_guards": []
    }
  ]
}
```

`vue_output/display_labels.json` — 상태값 코드 → 한국어 표시 라벨 매핑
```json
{
  "labels": {
    "TermStatus": {
      "READY":    "준비중",
      "APPLYING": "수강신청 중",
      "ONGOING":  "학기 중",
      "FINISHED": "종강"
    },
    "RegistrationStatus": {
      "APPROVED": "승인",
      "REJECTED": "반려"
    }
  },
  "source_components": ["views/admin/academic_manage/operation/Operation.vue"]
}
```

`vue_output/client_behaviors.json` — 행동 패턴 (폴링, 조건 분기, 확인 가드, 비활성화 가드)
```json
{
  "behaviors": [
    {
      "type": "polling",
      "component": "components/Enrolment.vue",
      "interval_ms": 3000,
      "api_called_indirect": ["getRequestStatusByID"],
      "termination": "NOT (this.requestStatus == 'PENDING')"
    },
    {
      "type": "conditional_api",
      "subtype": "template_ternary",
      "component": "...",
      "condition": "term.semester.toUpperCase() == 'SPRING'",
      "if_true": "applySpringTermLecture()",
      "if_false": "applyFallTermLecture()"
    },
    {
      "type": "confirmation_guard",
      "component": "...",
      "required_text": "폐강하겠습니다.",
      "action": "closeTerm"
    },
    {
      "type": "disabled_guard",
      "component": "...",
      "condition": "!isAdmin || term[l.year+l.semester] === 'FINISHED'"
    }
  ]
}
```

`vue_output/client_only_reqs.json` — 클라이언트 전용 요구사항 후보
```json
{
  "requirements": [
    {
      "id": "CL-004",
      "category": "irreversibility_guard",
      "statement": "강의를 폐강하기 전 '폐강하겠습니다.' 텍스트 입력으로 불가역 작업을 확인해야 한다",
      "evidence": { "component": "...", "required_text": "폐강하겠습니다." }
    },
    {
      "id": "CL-007",
      "category": "async_polling",
      "statement": "수강신청 요청 후 상태가 PENDING인 동안 3000ms 간격으로 상태를 반복 조회해야 한다",
      "evidence": { "component": "...", "interval_ms": 3000 }
    }
  ]
}
```

**`target_legacy_code/pati-client/` 폴더가 없으면 이 단계를 건너뛰고 Step 3로 진행한다.**

---

### Step 3 — Call Graph 생성

`build_graph.py`를 실행하되, **내부 함수 필터링을 적용**한다.

```bash
python build_graph.py
```

build_graph.py는 다음을 반드시 수행해야 한다:
- `registry`(함수명 → 파일 경로 맵)를 먼저 빌드한다
- `calls` 목록에서 `registry`에 없는 항목(stdlib, vendor 패키지)을 제거한다
- 내부 함수 간 호출만 남긴 `global_call_graph.json`을 생성한다

필터링 전/후 통계를 출력한다.

```json
{
  "registry": {
    "ConfirmEnrollment": "analysis_output/service/enrollment.go.json"
  },
  "graph": {
    "ConfirmEnrollment": ["validateEnrollment", "publishEvent"]
  },
  "stats": {
    "total_functions": 342,
    "internal_calls_only": true,
    "filtered_external_calls": 1847
  }
}
```

---

## 완료 확인

모든 단계 완료 후 다음을 확인한다:

- `analysis_output/` 폴더에 JSON 파일이 생성됐는가
- `global_call_graph.json`이 생성됐는가, `internal_calls_only: true` 확인
- `vue_output/` 폴더 (pati-client 폴더가 있는 경우):
  - `api_map.json` — client.js 메서드 매핑 수
  - `routes.json` — 라우트 + 권한 분기
  - `component_map.json` — 컴포넌트 수 (route_paths, vuex_dispatches 포함 여부 확인)
  - `client_behaviors.json` — 행동 패턴 수
  - `display_labels.json` — 상태값 한국어 라벨 매핑 수 (0이면 Vue template에서 option/v-if 패턴 확인 필요)
  - `client_only_reqs.json` — 순수 클라이언트 전용 요구사항 후보 수

문제가 있으면 해당 스크립트의 에러를 진단하고 수정한다.
완료 후 생성된 파일 수와 함수 수, 클라이언트 분석 결과를 요약해서 보고한다.
