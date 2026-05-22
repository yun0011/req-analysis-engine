---
name: run
description: |
  요구사항 도출 파이프라인 전체를 오케스트레이션한다.
  현재 파이프라인 상태를 파악하고, 다음 실행할 단계를 안내하고, 각 단계의 결과를 검토하고,
  문제가 있으면 재실행 여부를 결정한다. 파이프라인을 처음 시작하거나 중간에 재개할 때 사용한다.
  "run 실행", "파이프라인 실행", "요구사항 추출 시작", "어디까지 됐어", "다음 단계"라고 하면 이 스킬을 사용한다.
---

# run — 파이프라인 오케스트레이션

요구사항 도출 파이프라인의 전체 흐름을 관리한다.
각 단계를 순서대로 실행하고, 결과를 검토하고, 문제가 있으면 재실행 여부를 결정한다.

```
Phase 1  extract    백엔드 AST + Call Graph + 클라이언트 정적 분석
Phase 2  slice      진입점 → 효과지점 → Rule Record + 스키마 보강
Phase 3  group      도메인 그룹핑 + 교차검증
Phase 4  field      필드 생애주기 분석 → 불변 제약 · 조건부 필수 도출
Phase 5  derive     기능 도출 + 요구사항 문서 + 교차검증 + 스키마 전파
Phase 6  audit      Reverse Audit + 커버리지 검증 + UI 커버리지 역검증
Phase 7  reconcile  enum 진실표 수집 + 문서 스캔 + 불일치 수정
```

---

## 시작: 현재 상태 파악

스킬이 호출되면 가장 먼저 파이프라인의 현재 상태를 파악한다.
아래 파일들의 존재 여부와 기본 유효성을 확인한다.

| 파일 | Phase | 상태 판단 기준 |
|---|---|---|
| `analysis_output/` | 1 완료 | 폴더 존재 + JSON 파일 1개 이상 |
| `call_graph.json` | 1 완료 | 파일 존재 + `registry` 키 존재 |
| `client_output/api_map.json` | 1 완료 (선택) | 클라이언트 코드 존재할 때만 확인 |
| `client_output/routes.json` | 1 완료 (선택) | 동상 |
| `client_output/component_map.json` | 1 완료 (선택) | 동상 |
| `client_output/client_behaviors.json` | 1 완료 (선택) | 동상 |
| `client_output/display_labels.json` | 1 완료 (선택) | 동상 |
| `client_output/ui_structure.json` | 1 완료 (선택) | 동상 |
| `.req-analysis/1_entry_points.json` | 2 완료 | 파일 존재 + `entry_points` 배열 비어있지 않음 |
| `.req-analysis/2_effect_points.json` | 2 완료 | 파일 존재 + `effect_points` 배열 비어있지 않음 |
| `.req-analysis/3_rule_records.json` | 2 완료 | 파일 존재 + `rule_records` 배열 비어있지 않음 |
| `.req-analysis/4_domain_groups.json` | 3 완료 | 파일 존재 + `domain_groups` 배열 비어있지 않음 |
| `.req-analysis/5_field_spec.json` | 4 완료 | 파일 존재 + `domains` 배열 비어있지 않음 |
| `.req-analysis/6_structured_spec.json` | 5 완료 | 파일 존재 + `structured_spec.domains` 비어있지 않음 |
| `.req-analysis/UI_requirements.md` | 5 완료 | 파일 존재 + 비어있지 않음 |
| `.req-analysis/7_audit_report.json` | 6 완료 | 파일 존재 |
| `.req-analysis/8_reconcile_report.json` | 7 완료 | 파일 존재 |

확인 결과를 다음 형식으로 출력한다:

```
=== 파이프라인 상태 ===
Phase 1 extract    ✓ 완료  (분석 파일 N개, 함수 N개, 클라이언트 분석 완료)
Phase 2 slice      ✓ 완료  (EP N개, Rule Record N개, 스키마 N개 보강)
Phase 3 group      ✓ 완료  (도메인 그룹 N개, 클러스터 N개)
Phase 4 field      ✗ 미완료
Phase 5 derive     ✗ 미완료
Phase 6 audit      ✗ 미완료
Phase 7 reconcile  ✗ 미완료

다음 실행할 단계: Phase 4 field
```

---

## Phase 1 — extract 실행 및 검토

**실행 조건**: `analysis_output/`가 없거나 비어있을 때

`/extract` 스킬을 실행한다. 다음 순서로 스크립트를 실행한다:

1. 백엔드 AST 추출 스크립트 → `analysis_output/`
2. 클라이언트 정적 분석 스크립트 → `client_output/` (클라이언트 코드 존재 시)
3. Call Graph 생성 스크립트 → `call_graph.json`

**완료 후 검토 항목:**

```
✓ analysis_output/ 파일 수: {N}개
✓ call_graph.json 내부 함수 수: {N}개 / 외부 호출 필터링: {N}개 제거
✓ 클라이언트 분석 (클라이언트 코드가 있을 때):
  - api_map.json:         API 메서드 → EP 매핑 {N}개
  - routes.json:          라우트 {N}개, 권한 분기 포함
  - component_map.json:   컴포넌트 {N}개 → API 호출 체인
  - client_behaviors.json: 행동 패턴 (폴링 {N}, 확인 가드 {N}, disabled 조건 {N})
  - display_labels.json:  상태 코드 → 표시 텍스트 도메인 {N}개
  - ui_structure.json:    페이지 {N}개 (컬럼 있는 페이지 {N}, 폼 있는 페이지 {N})
```

**중단 조건:**
- `analysis_output/`가 비어있음 → AST 추출 스크립트 실행 오류 진단
- `call_graph.json`의 `registry`가 비어있음 → Call Graph 생성 스크립트 오류 진단

**Phase 1 완료 체크포인트:**

> Phase 1이 완료됐습니다.
> - 백엔드 파일 {N}개 처리 / 함수 {N}개 추출
> - Call Graph 내부 함수: {N}개
> - 클라이언트 분석: {완료 (메서드 N개, 컴포넌트 N개, 페이지 N개) / 건너뜀}
>
> Phase 2 slice로 진행할까요?

---

## Phase 2 — slice 실행 및 검토

**실행 조건**: Phase 1 완료 + `.req-analysis/3_rule_records.json` 없음

`/slice` 스킬을 실행한다.

**클라이언트 정보 소비 — trigger.actor 보강:**

Rule Record 생성 시 `client_output/routes.json`의 권한 설정을 참조해 `trigger.actor`를 결정한다.

**슬라이스 완료 직후 — 스키마 보강 (자동 실행):**

스키마 보강 스크립트를 실행해 각 Rule Record에 `request_schema` / `response_schema`를 추가한다.

**클라이언트 컴포넌트 슬라이싱 (클라이언트 코드가 있을 때):**

백엔드 Rule Record 추출이 끝나면 클라이언트 컴포넌트 파일을 직접 읽어 CL Rule Record를 추출한다.

대상: `client_output/component_map.json`에서 라우트 경로가 있고 API를 호출하는 페이지 단위 컴포넌트.

LLM이 컴포넌트 파일을 읽고 다음을 판단한다:
- 백엔드 응답 전체를 받아서 클라이언트가 로컬로 필터링/정렬하는 로직이 있는가
- 해당 필터 파라미터가 백엔드 EP의 `request_schema`에 없는가 (진짜 클라이언트 전용인가)
- 사용자 관점에서 의미 있는 데이터 탐색 기능인가 (단순 UX 토글 제외)

조건을 충족하면 `source: "client"`, `rule_id: "CP-NNN-R-NNN"` 형식의 CL Rule Record로 기록한다.

**완료 후 검토 항목:**

```
✓ 진입점(EP): {N}개
✓ 효과 지점(EFX): {N}개
✓ 백엔드 Rule Record: {N}개
  - confidence high:   {N}개 ({%})
  - confidence medium: {N}개 ({%})
  - confidence low:    {N}개 ({%})
✓ CL Rule Record (클라이언트 전용): {N}개
  - client_filter: {N}개
  - client_sort:   {N}개
  - conditional_display: {N}개
✓ 스키마 보강:
  - request_schema 있음: {N}개
  - response_schema 있음: {N}개
  - 스키마 미발견: {N}개 (경고)
```

**주의 조건:**
- confidence `low` 비율 30% 이상 → 슬라이싱 품질 경고. group 결과 보고 재실행 여부 결정.
- EP 0개 → 진입점 탐색 패턴이 코드베이스와 맞지 않음
- CL Rule Record가 0개인데 클라이언트 코드가 있다면 → 컴포넌트 읽기를 건너뛴 것인지 확인

**Phase 2 완료 체크포인트:**

> Phase 2가 완료됐습니다.
> - 진입점: {N}개 / 백엔드 Rule Record: {N}개 (high {N} / medium {N} / low {N})
> - CL Rule Record (클라이언트 전용): {N}개
> - 스키마 보강: request_schema {N}개 / response_schema {N}개
>
> Phase 3 group으로 진행할까요?

---

## Phase 3 — group 실행 및 검토

**실행 조건**: Phase 2 완료 + `.req-analysis/4_domain_groups.json` 없음

`/group` 스킬을 실행한다.

**완료 후 검토 항목:**

```
✓ 도메인 그룹: {N}개
  - {DG-XXX}: {N}개 클러스터
  - ...
✓ 횡단 관심사(XC): {N}개
✓ 교차검증 불일치: {N}개 / 전체 {N}개 클러스터
```

**중단 조건:**
- `DG-UNCLASSIFIED`에 Rule Record가 전체의 20% 이상 → slice 재실행 권고
- 교차검증 불일치 비율 30% 이상 → Rule Record 품질 문제, 사용자에게 재실행 여부 확인

**Phase 3 완료 체크포인트:**

> Phase 3이 완료됐습니다.
> - 도메인 그룹: {N}개 / 클러스터 총계: {N}개
> - 교차검증 불일치: {N}개
>
> Phase 4 field로 진행할까요?

---

## Phase 4 — field 실행 및 검토

**실행 조건**: Phase 3 완료 + `.req-analysis/5_field_spec.json` 없음

`/field` 스킬을 실행한다.

**이 단계가 하는 일:**

같은 도메인의 CREATE / UPDATE EP 스키마를 나란히 비교하고, 클라이언트 편집 폼의 disabled 필드 정보를 교차 참조해 필드별 생애주기 제약을 결정한다.

- **불변 필드** — 편집 폼에서 `disabled="true"`인 필드 → `immutable_after_create`
- **조건부 필수 차이** — CREATE required + UPDATE optional → `create_required_update_optional`
- **서버 할당 필드** — 어떤 request에도 없고 response에만 있는 필드 → `server_assigned`

이 단계의 결과(`derived_requirement`)가 Phase 5 (derive)의 FR.preconditions 입력으로 사용된다.
이 단계가 없으면 LLM이 "과목코드는 변경 불가" 같은 요구사항을 hallucination하거나 누락한다.

**완료 후 검토 항목:**

```
✓ 분석된 도메인: {N}개
✓ 분석된 필드 총계: {N}개
  - immutable_after_create:          {N}개
  - create_required_update_optional: {N}개
  - always_optional:                 {N}개
  - always_required:                 {N}개
  - server_assigned:                 {N}개
  - conditionally_mutable (판단 보류): {N}개
✓ derived_requirement 생성: {N}개
```

**주의 조건:**
- `conditionally_mutable` 항목이 있으면 목록 제시 → 사용자 판단 또는 Phase 5에서 conflict 처리
- `ui_structure.json`이 없으면 UI 교차 참조 불가 → 스키마 비교만으로 분석 (불변 필드 탐지 정확도 낮음)

**Phase 4 완료 체크포인트:**

> Phase 4가 완료됐습니다.
> - 도메인 {N}개 / 필드 {N}개 분석
> - derived_requirement {N}개 생성 (Phase 5로 전달)
> - 판단 보류(conditionally_mutable): {N}개
>
> Phase 5 derive로 진행할까요?

---

## Phase 5 — derive 실행 및 검토

**실행 조건**: Phase 4 완료 + `.req-analysis/7_structured_spec.json` 없음

`/derive` 스킬을 실행한다.

**field_spec 소비 — derived_requirement → FR.preconditions 자동 삽입:**

FR 생성 시 `5_field_spec.json`을 읽어 `derived_requirement`가 있는 필드를 해당 FR의 `behavior.preconditions`에 자동으로 포함한다. LLM이 hallucination 없이 필드 수준 제약을 기술할 수 있게 한다.

**클라이언트 행동 소비 — observable_facts 해석:**

`client_behaviors.json`의 raw 사실(user_messages, conditional_renders, disabled_conditions, polling)을 해석해 FR의 `ui` 섹션에 통합하거나 CL-* FR로 승격한다.

**derive 완료 직후 — 스키마 전파 (자동 실행):**

스키마 전파 스크립트를 실행해 FR에 `request_schema` / `response_schema`를 전파한다.

**완료 후 검토 항목:**

```
✓ 기능 요구사항(FR): {N}개
  - grounding high:   {N}개
  - grounding medium: {N}개
  - grounding low:    {N}개
✓ field_spec 반영:
  - derived_requirement 삽입된 FR: {N}개
✓ 클라이언트 전용 FR (CL-): {N}개
✓ 횡단 관심사(XC): {N}개
✓ 충돌(conflict): {N}개
✓ 미해결(unresolved): {N}개
✓ 교차검증 불일치: {N}개
✓ 스키마 전파: request_schema {N}개 / response_schema {N}개
✓ UI_requirements.md 생성: ui 섹션 있는 FR {N}개 렌더링
```

**충돌 목록 제시:**
```
conflict가 {N}개 발견됐습니다:
- CF-001: DG-XXX-C-02 vs C-22 — precondition 상충
→ 6_structured_spec.json의 conflicts 섹션에 기록됨
```

**주의 조건:**
- `UI_requirements.md`가 생성되지 않았으면 → derive Step 4 누락. 수동으로 재실행 필요.

**Phase 5 완료 체크포인트:**

> Phase 5가 완료됐습니다.
> - FR: {N}개 (백엔드 도출 {N} + 클라이언트 전용 {N})
> - field_spec 반영: {N}개 FR에 필드 제약 삽입
> - conflict: {N}개 / unresolved: {N}개
> - UI_requirements.md: ui 섹션 {N}개 렌더링 완료
>
> Phase 6 audit으로 진행할까요?

---

## Phase 6 — audit 실행 및 검토

**실행 조건**: Phase 5 완료 + `.req-analysis/8_audit_report.json` 없음

`/audit` 스킬을 실행한다.

**완료 후 검토 항목:**

```
✓ 전체 도달 가능 함수: {N}개
✓ 요구사항에 반영됨: {N}개 ({%})
✓ 고아 후보: {N}개
  - truly_orphan:  {N}개  ← 중요
  - utility:       {N}개
  - cross_cutting: {N}개
✓ Dead code 후보: {N}개
✓ 미매핑 진입점: {N}개 / 전체 {N}개
✓ UI 커버리지:
  - ui 섹션 있는 FR: {N}개 / 전체 {N}개 ({%})
  - 내부 API FR (ui 없음, 정상): {N}개
  - UI만 있고 FR 없는 EP: {N}개 (경고)
```

**재실행 권고 분기:**

```
[slice 재실행 권고]
- truly_orphan 함수 5개 이상
- 미매핑 EP 중 missed_slice 범주 존재

[derive 재실행 권고]
- Rule Record는 있는데 FR 미매핑 EP 존재
- UI만 있고 FR 없는 EP가 2개 이상

선택:
1. 현재 결과로 Phase 7 reconcile 진행
2. Phase 2 slice 재실행
3. Phase 5 derive 재실행
```

**Phase 6 완료 체크포인트:**

> Phase 6이 완료됐습니다.
> - 커버리지: {N}/{N} ({%})
> - truly_orphan: {N}개 / UI 누락 EP: {N}개
>
> Phase 7 reconcile로 진행할까요?

---

## Phase 7 — reconcile 실행 및 검토

**실행 조건**: Phase 6 완료 + `.req-analysis/9_reconcile_report.json` 없음

`/reconcile` 스킬을 실행한다.

**이 단계가 하는 일:**

백엔드 타입 정의에서 canonical enum 값을 수집하고, 두 요구사항 문서(기능 요구사항, UI 요구사항)를 스캔해 hallucination된 enum 값을 탐지하고 수정한다.

진실표 우선순위: 백엔드 타입 정의 > UI 요구사항 문서 > 기능 요구사항 문서

**완료 후 검토 항목:**

```
✓ 검증된 enum 도메인: {N}개
✓ 스캔한 문서: 기능 요구사항, UI 요구사항
✓ 자동 수정: {N}건
  - 기능 요구사항 문서: {N}건
  - UI 요구사항 문서: {N}건
✓ 잔여 conflict (자동 수정 불가): {N}개
```

**잔여 conflict 목록 제시 (있을 경우):**
```
자동 수정 불가 항목 {N}개:
- [도메인] UI 문서와 백엔드 코드가 모두 다른 값
  → 상태값 변환 모듈 자체가 백엔드와 drift됐을 가능성
  → 수동 검토 필요
```

**Phase 7 완료 체크포인트:**

> Phase 7이 완료됐습니다.
> - 자동 수정: {N}건 / 잔여 conflict: {N}개
>
> 파이프라인이 완료됐습니다.

---

## 파이프라인 완료

모든 Phase가 완료되면 최종 요약을 출력한다.

```
=== 파이프라인 완료 ===

산출물:
  analysis_output/                        — 백엔드 AST (함수 N개)
  call_graph.json                         — Call Graph (내부 함수 N개)
  client_output/api_map.json              — API 메서드 → EP 매핑 (N개)
  client_output/routes.json               — 라우트 + 권한 (N개)
  client_output/component_map.json        — 컴포넌트 → API 호출 체인 (N개)
  client_output/client_behaviors.json     — 클라이언트 행동 패턴
  client_output/display_labels.json       — 상태 코드 → 표시 텍스트
  client_output/ui_structure.json         — 페이지별 UI 구조 (N개)
  .req-analysis/1_entry_points.json       — 진입점 N개
  .req-analysis/2_effect_points.json      — 효과 지점 N개
  .req-analysis/3_rule_records.json       — Rule Record N개 (스키마 보강 완료)
  .req-analysis/4_domain_groups.json      — 도메인 그룹 N개
  .req-analysis/5_field_spec.json         — 필드 생애주기 제약 N개 도메인
  .req-analysis/6_features/              — 도메인별 기능 후보
  .req-analysis/7_structured_spec.json   — FR N개 / XC N개 (필드 제약 + 스키마 포함)
  .req-analysis/UI_requirements.md        — 화면 구성 요구사항
  .req-analysis/8_audit_report.json       — 커버리지 N%
  .req-analysis/9_reconcile_report.json   — enum 수정 N건 / 잔여 conflict N개

주의 사항:
  - conflict: {N}개 → 수동 검토 필요
  - unresolved: {N}개 → 추가 근거 탐색 필요
  - truly_orphan: {N}개 → 요구사항 누락 가능성
  - reconcile 잔여 conflict: {N}개 → 상태값 변환 모듈 drift 의심

다음 단계:
  7_structured_spec.json + UI_requirements.md를 기반으로 재작성을 시작할 수 있습니다.
  conflict와 unresolved 항목은 재작성 전에 결정이 필요합니다.
```

---

## 특수 명령

**특정 Phase만 재실행:**

"Phase N 다시 실행해줘", "{스킬명} 다시 돌려줘" → 해당 Phase부터 재실행하고 이후 단계 출력물을 초기화한다.

재실행 시 함께 실행해야 하는 후처리 스크립트:
- Phase 2 재실행 → 스키마 보강 스크립트도 함께 재실행
- Phase 5 재실행 → 스키마 전파 스크립트도 함께 재실행
- Phase 4 재실행 → Phase 5 출력물도 초기화 후 재실행 필요

**현재 상태만 확인:**
"상태 확인해줘", "어디까지 됐어" → 실행 없이 상태 파악 결과만 출력한다.

**특정 Phase 건너뛰기:**
사용자 명시적 요청 시에만 허용. 건너뛰는 Phase와 그 영향을 명확히 표시한다.
- Phase 4 (field) 건너뛰면 → Phase 5 (derive)에서 필드 수준 제약 누락 가능성 높음. 명시적으로 경고한다.
