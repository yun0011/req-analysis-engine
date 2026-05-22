---
name: group
description: |
  Rule Record들을 도메인 우선으로 그룹핑하고, 그룹 내 구조 클러스터링을 수행하고,
  횡단 관심사를 분리한다. 두 번째 모델로 교차검증을 수행해 불일치 항목을 표시한다.
  요구사항 도출 파이프라인의 Phase 3. slice 스킬 완료 후 실행한다.
  "group 실행", "도메인 그룹핑", "클러스터링"이라고 하면 이 스킬을 사용한다.
---

# group — 도메인 그룹핑 + 구조 클러스터링 + 교차검증

요구사항 도출 파이프라인의 **Phase 3**이다.
이 단계에서 처음으로 추론이 개입된다. LLM이 Rule Record들 사이의 관계를 판단한다.

입력: `.req-analysis/3_rule_records.json`, `vue_output/component_map.json` (선택)
출력: `.req-analysis/4_domain_groups.json`

---

## Step 0 — Vue route namespace 기반 도메인 분리 신호 수집 (vue_output이 있을 때만)

`vue_output/component_map.json`이 존재하면, Step 1의 그룹핑 전에 먼저 아래를 확인한다.

**목적**: backend module 기준으로는 하나로 보이지만 실제로는 별도 사용자 도메인인 경우를 미리 포착한다.

**확인 방법**:

1. `component_map.json`에서 각 컴포넌트의 `route_paths`와 `vuex_dispatches`를 읽는다.
2. **같은 Vuex action을 dispatch하는 컴포넌트들이 서로 다른 route namespace(경로 prefix)에 속하는지** 확인한다.

   예시:
   ```
   views/academic_info/rule/Rule.vue       route: /rule     dispatches: [getBoardList]
   views/academic_info/notice/Notice.vue   route: /notice   dispatches: [getBoardList]
   views/academic_info/schedule/Schedule.vue route: /schedule dispatches: [getBoardList]
   ```
   → 세 개의 다른 route namespace가 같은 `getBoardList` action을 사용한다
   → Step 1의 백엔드 기준 도메인 그룹이 하나(`DG-BOARD`)로 만들어지더라도
     Step 1-b에서 route namespace 수만큼 분리한다

3. route namespace 분리 기준:
   - route의 **첫 번째 경로 세그먼트** (`/rule`, `/notice`, `/schedule`)가 다르면 다른 namespace
   - `/admin/...`, `/student/...`, `/professor/...`처럼 역할 prefix가 다른 것은 namespace 분리가 아닌 **actor 분리**다 (Step 1에서 `trigger.actor`로 처리)
   - 같은 namespace 안의 CRUD (`/rule`, `/rule/add`, `/rule/update/:id`)는 하나의 namespace

**결과**: namespace별 도메인 분리 신호를 `vue_route_signals`로 메모해두고 Step 1-b에서 사용한다.

---

## Step 1 — 1차 패스: 도메인 컨텍스트 기반 그룹핑

`.req-analysis/3_rule_records.json`을 읽는다.

**그룹핑 기준 (코드 사실, 해석 없음)**

`domain_context.source_module`과 `domain_context.primary_tables`가 겹치는 Rule Record들을 같은 도메인 그룹으로 묶는다.

이것은 의미 해석이 아닌 코드 사실 분류다. `enrollment.go`에 있는 것들을 묶는 것은 인증 guard가 같은 것들을 묶는 것과 동일한 수준의 사실 기반 분류다.

**왜 구조 기반보다 도메인 기반이 먼저인가**

구조만으로 먼저 묶으면 수강 신청, 결제, 일정 등록이 같은 클러스터가 된다. 이 세 가지 모두 `auth guard → DB insert → response` 구조를 공유하지만 서로 다른 도메인이다. 도메인 경계를 먼저 그은 뒤 구조 패턴을 찾아야 한다.

**도메인 그룹 ID 부여**

소스 모듈명에서 도메인 이름을 추출한다.
- `service/enrollment.go` → `DG-ENROLLMENT`
- `service/payment.go` → `DG-PAYMENT`
- `handler/lecture.go` → `DG-LECTURE`

**Step 1-b — vue_route_signals 반영**

Step 0에서 수집한 `vue_route_signals`가 있으면:

- 백엔드 기준으로 하나의 도메인 그룹이 된 그룹에 대해,
  해당 그룹의 Rule Record들이 Step 0에서 식별된 여러 route namespace에서 호출된다면
  → 그 그룹을 namespace 수만큼 **분리된 도메인 그룹**으로 나눈다.

예시:
```
Step 0 신호: /rule, /notice, /schedule → 모두 getBoardList → DG-BOARD (1개)
Step 1 결과 → DG-BOARD를 DG-RULE, DG-NOTICE, DG-SCHEDULE로 분리

DG-RULE:     source_modules: ["handler/board.go"], vue_namespace: "/rule"
DG-NOTICE:   source_modules: ["handler/board.go"], vue_namespace: "/notice"
DG-SCHEDULE: source_modules: ["handler/board.go"], vue_namespace: "/schedule"
```

- 분리된 그룹의 `source_modules`와 `primary_tables`는 원본 그룹과 동일하다
- `vue_namespace` 필드를 추가해 분리 근거를 명시한다
- 분리된 각 그룹에는 해당 namespace에서 사용하는 Rule Record만 포함한다
  (같은 EP를 여러 namespace가 공유하면 모두 포함)

---

## Step 2 — 2차 패스: 그룹 내 구조 클러스터링

각 도메인 그룹 안에서 구조가 같은 Rule Record들을 클러스터로 묶는다.

**클러스터링 기준**

다음 세 가지가 동일하거나 거의 같으면 같은 클러스터다:
- `state_field` 역할 (변수명은 달라도 됨 — `enrollment.status`와 `e.status`는 같은 역할)
- `guard_predicates` 패턴
- `success_writes` 패턴

**변형(variant) 처리**

core는 같지만 side_effect가 하나 더 있거나 추가 write가 있는 경우 → core cluster + variant로 처리한다. 별도 클러스터로 분리하지 않는다.

**클러스터 스키마**

```json
{
  "domain_group": "DG-ENROLLMENT",
  "cluster_id": "DG-ENROLLMENT-C-001",
  "shared_structure": {
    "state_field_role": "*.status",
    "guard": ["status == REQUESTED"],
    "success_writes": ["status := ENROLLED", "confirmedAt := now()"],
    "side_effects": ["PublishEnrollmentConfirmed"]
  },
  "member_rules": ["EP-001-R-001", "EP-002-R-001"],
  "variants": [
    {
      "rule_id": "EP-045-R-002",
      "diff": "추가 audit log write 포함"
    }
  ]
}
```

---

## Step 3 — 횡단 관심사 분리

**모든 도메인 그룹에 공통으로 나타나는 구조**를 찾아 XC(Cross-Cutting) 항목으로 분리한다.

공통으로 나타나는 전형적인 패턴:
- JWT/세션 인증 guard — 모든 보호된 엔드포인트에 존재
- DB 트랜잭션 wrap — 모든 데이터 변경 작업에 존재
- 입력값 빈 값/형식 검증 — 모든 데이터 수신 엔드포인트에 존재
- 권한(role) 확인 — 특정 actor에게만 허용된 엔드포인트에 존재

이것들은 특정 도메인 기능이 아니라 시스템 전체에 걸친 제약이다.
도메인 그룹 안에 남기면 모든 그룹에서 중복 기술되므로 XC로 분리한다.

**XC 스키마**

```json
{
  "xc_id": "XC-AUTH-001",
  "type": "architectural_constraint",
  "statement": "모든 보호된 엔드포인트는 JWT 인증 guard를 통과해야 한다",
  "applies_to_groups": ["DG-ENROLLMENT", "DG-PAYMENT", "DG-LECTURE"],
  "evidence_refs": ["EP-001-R-001", "EP-002-R-001"]
}
```

---

## Step 4 — 교차검증

**이 단계가 교차검증을 수행하는 이유**

이 단계는 추론이 가장 많이 개입된다. 클러스터가 잘못 만들어지면 derive 단계 전체가 그 위에 쌓이므로 오류가 증폭된다. 두 모델이 독립적으로 그룹핑을 수행해 불일치를 찾는다.

**교차검증 절차**

1. 위 Step 1–3에서 생성한 그룹핑 결과를 `draft_groups`로 저장한다.

2. 동일한 Rule Records를 두 번째 모델(Codex 또는 다른 Claude 인스턴스)에게 전달한다.
   프롬프트: "아래 Rule Record들을 domain_context.source_module과 primary_tables 기준으로 도메인 그룹핑하고, 각 그룹 내 구조 패턴을 클러스터로 묶어라. 의미 해석 없이 코드 사실만 기준으로 하라."

3. 두 결과를 비교한다:
   - **일치**: 두 모델이 같은 그룹 경계와 클러스터를 만든 경우 → `confidence: "high"`
   - **불일치**: 어느 클러스터 또는 도메인 경계가 다른 경우 → `confidence: "low"`, `cross_validation_conflict: true`로 표시

**불일치 처리**

불일치 항목은 강제 병합하지 않는다. 두 모델의 결과를 모두 기록하고 derive 단계에서 주의 표시와 함께 전달한다.

---

## 결과 저장

`.req-analysis/4_domain_groups.json`:
```json
{
  "domain_groups": [
    {
      "group_id": "DG-ENROLLMENT",
      "source_modules": ["service/enrollment.go"],
      "primary_tables": ["enrollments"],
      "clusters": [
        {
          "cluster_id": "DG-ENROLLMENT-C-001",
          "shared_structure": { ... },
          "member_rules": ["EP-001-R-001"],
          "variants": [],
          "confidence": "high",
          "cross_validation_conflict": false
        }
      ]
    }
  ],
  "cross_cutting": [
    {
      "xc_id": "XC-AUTH-001",
      "type": "architectural_constraint",
      "statement": "...",
      "applies_to_groups": ["DG-ENROLLMENT"],
      "evidence_refs": ["..."]
    }
  ],
  "cross_validation_summary": {
    "total_clusters": 0,
    "agreed": 0,
    "conflicted": 0,
    "conflict_items": []
  }
}
```

---

## 완료 확인

- 모든 Rule Record가 최소 하나의 도메인 그룹에 속하는지 확인
- 어떤 그룹에도 속하지 않은 Rule Record가 있으면 `DG-UNCLASSIFIED`로 분류하고 경고 표시
- 교차검증 불일치 비율이 20% 이상이면 Rule Record 품질 재검토 필요

완료 후 도메인 그룹 수, 클러스터 수, 교차검증 불일치 수를 요약해서 보고한다.
