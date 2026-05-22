---
name: field
description: |
  같은 도메인의 여러 EP(생성/수정)를 가로질러 필드별 생애주기 제약을 분석한다.
  불변 필드(수정 불가), 조건부 필수(등록 시 필수/수정 시 선택), 서버 할당 필드를 도출한다.
  요구사항 도출 파이프라인의 Phase 4. group 스킬 완료 후 실행한다.
  "field 실행", "필드 분석", "불변 필드 찾기", "필드 생애주기"라고 하면 이 스킬을 사용한다.
---

# field — 필드 생애주기 분석

요구사항 도출 파이프라인의 **Phase 4**이다.
같은 도메인 엔티티를 다루는 여러 EP(생성/조회/수정/삭제)를 가로질러 각 필드의 동작을 종합한다.

입력: `.req-analysis/4_domain_groups.json`, `.req-analysis/3_rule_records.json`, `vue_output/ui_structure.json`
출력: `.req-analysis/5_field_spec.json`

---

## 왜 이 단계가 필요한가

Phase 2 (slice)는 EP를 독립 단위로 처리한다. 하나의 Rule Record는 "이 EP가 무엇을 하는가"만 담는다.

그런데 다음 요구사항들은 EP를 가로질러 비교해야만 나온다:

- **불변 필드 제약** — "과목코드는 생성 후 수정할 수 없다"
  → 수정 폼에서 해당 input이 disabled 상태로 존재함. 단일 EP 분석으로는 안 잡힘.

- **조건부 필수 차이** — "영문명은 등록 시 선택, 수정 시에도 선택"
  → 생성 EP의 request_schema와 수정 EP의 request_schema를 비교해야 "두 경우 모두 선택"임을 알 수 있음.

- **서버 할당 필드** — "id, createdAt은 클라이언트가 전송하지 않는다"
  → response_schema에는 있으나 어떤 request_schema에도 없는 필드.

Phase 3 (group)이 "어떤 EP들이 같은 도메인인가"를 확정한 뒤에만 이 비교가 가능하다.

---

## Step 1 — EP 유형 분류

각 도메인 그룹에서 EP를 CRUD 유형으로 분류한다.

```
CREATE  — POST + 엔티티 경로 (예: POST /subjects)
READ    — GET + 엔티티 경로 (단건 또는 목록)
UPDATE  — PUT / PATCH + 엔티티 경로
DELETE  — DELETE + 엔티티 경로
```

HTTP method가 불명확한 경우 핸들러명(`create*`, `add*`, `update*`, `edit*`, `delete*`, `remove*`)으로 보조 판단한다.

---

## Step 2 — 엔티티 필드 목록 수집

도메인 그룹의 모든 EP에서 request_schema와 response_schema를 수집한다.

**전체 필드 후보 집합 = 모든 EP의 request + response 필드의 합집합**

각 필드에 대해 EP별 존재 여부와 required 여부를 표로 정리한다:

```
필드명        | CREATE req | UPDATE req | response
-------------|-----------|-----------|----------
subject_code | required  | present   | present
name         | required  | required  | present
english_name | optional  | optional  | present
id           | absent    | absent    | present
created_at   | absent    | absent    | present
```

---

## Step 3 — UI 정보 교차 참조

`vue_output/ui_structure.json`에서 해당 도메인의 편집 폼(edit form) 컴포넌트를 찾는다.

**편집 폼 식별 기준**: 컴포넌트 파일명 또는 라우트 경로에 `edit`, `update`, `modify`, `수정` 등이 포함되거나, 라우트 경로에 파라미터(`:id` 등)가 있는 폼 컴포넌트.

편집 폼에서 `immutable: true`로 표시된 필드 → **불변 제약** 후보.

---

## Step 4 — 필드별 생애주기 제약 결정

Step 2 표와 Step 3 UI 정보를 종합해 각 필드에 제약 유형을 부여한다.

| 제약 유형 | 판단 기준 |
|---|---|
| `server_assigned` | 모든 request에 absent, response에만 present (`id`, `createdAt` 등) |
| `immutable_after_create` | CREATE request에 present, UPDATE 폼에서 disabled (`immutable: true`) |
| `create_only` | CREATE request에 present, UPDATE request에 absent (서버가 UPDATE 시 무시) |
| `always_required` | CREATE와 UPDATE request 모두 required |
| `create_required_update_optional` | CREATE에서 required, UPDATE에서 optional |
| `always_optional` | CREATE와 UPDATE request 모두 optional |
| `read_only_display` | response에만 present, 어떤 폼에도 없음 (조회 전용 표시 필드) |

**우선순위**: UI의 `immutable: true` 신호가 스키마 분석보다 우선한다. UI에서 disabled이면 스키마 상 required 여부와 무관하게 `immutable_after_create`로 분류한다.

---

## Step 5 — 필드 명세 생성

`.req-analysis/5_field_spec.json`:

```json
{
  "domains": [
    {
      "domain": "Subject",
      "entity": "Subject",
      "source_group": "DG-SUBJECT",
      "fields": [
        {
          "field": "subject_code",
          "json_key": "subject_code",
          "constraint": "immutable_after_create",
          "lifecycle": {
            "create": { "present": true, "required": true },
            "update": { "present": true, "required": false, "mutable": false },
            "read":   { "present": true }
          },
          "evidence": {
            "ui": "수정 폼에서 disabled (SubjectEdit.vue)",
            "schema": "updateSubjectParam에 포함되나 disabled 처리"
          },
          "derived_requirement": "과목코드는 등록 후 수정할 수 없다."
        },
        {
          "field": "english_name",
          "json_key": "english_name",
          "constraint": "always_optional",
          "lifecycle": {
            "create": { "present": true, "required": false },
            "update": { "present": true, "required": false },
            "read":   { "present": true }
          },
          "evidence": {
            "schema": "createSubjectParam, updateSubjectParam 모두 omitempty"
          },
          "derived_requirement": "영문교과목명은 등록 및 수정 시 모두 선택 입력이다."
        },
        {
          "field": "id",
          "json_key": "id",
          "constraint": "server_assigned",
          "lifecycle": {
            "create": { "present": false },
            "update": { "present": false },
            "read":   { "present": true }
          },
          "evidence": {
            "schema": "어떤 request_schema에도 없음, response_schema에만 존재"
          },
          "derived_requirement": null
        }
      ]
    }
  ]
}
```

`derived_requirement`가 null이 아닌 필드는 Phase 5 (derive)에서 해당 FR의 `behavior.preconditions` 또는 `request_schema.constraints`에 자동으로 포함된다.

---

## Step 6 — 특수 패턴 탐지

**패턴 1: CREATE에만 있고 UPDATE에 없는 필드 (create_only)**

UPDATE request에서 아예 없는 필드는 두 가지 중 하나다:
- 서버가 UPDATE 시 해당 필드를 무시함 (변경 불가와 동일 효과)
- 생성 시에만 의미 있는 필드 (예: 초기 비밀번호)

이 경우 `immutable_after_create` 또는 `create_only`로 분류하고, UI에서 교차 확인한다.

**패턴 2: 두 EP의 required가 다른 필드**

CREATE required → UPDATE optional: 생성 시에는 반드시 입력해야 하지만 수정 시에는 변경하지 않아도 됨.
`create_required_update_optional`로 분류하고 `derived_requirement`에 명시한다.

**패턴 3: 상태 조건부 필수**

UI `client_behaviors.json`의 `disabled_conditions`에 비즈니스 조건이 있는 경우 (예: `status === 'FINISHED'`):
→ `conditionally_mutable`로 분류, 조건을 `evidence.ui`에 기록.
→ 이 패턴은 자동 분류하지 않고 conflict로 표시, derive 단계에서 판단.

---

## derive 단계 연동

Phase 5 (derive)에서 FR을 생성할 때 `5_field_spec.json`을 읽어 다음을 자동 포함한다:

- `constraint: immutable_after_create` → FR의 `behavior.preconditions`에 "X는 변경할 수 없다" 추가
- `constraint: create_required_update_optional` → FR의 `request_schema.constraints`에 필드 조건 명시
- `constraint: always_optional` → FR의 request_schema 필드 설명에 "(선택)" 표기
- `constraint: server_assigned` → FR의 request_schema에서 해당 필드 제외, response_schema에만 유지

---

## 완료 확인

- 각 도메인 그룹에 최소 하나의 엔티티가 분석됐는가
- `immutable_after_create` 필드가 있으면 UI evidence와 schema evidence 모두 기록됐는가
- `derived_requirement`가 생성된 필드 수를 보고한다
- 판단 불가(conditionally_mutable) 항목을 목록으로 보고한다
