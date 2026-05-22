---
name: audit
description: |
  요구사항 문서가 전체 코드베이스를 얼마나 커버하는지 역방향으로 검증한다.
  요구사항에 한 번도 반영되지 않은 고아 함수를 찾고, 진입점 커버리지를 검증한다.
  요구사항 도출 파이프라인의 Phase 6. derive 스킬 완료 후 실행한다.
  "audit 실행", "Reverse Audit", "고아 함수 찾기", "커버리지 검증"이라고 하면 이 스킬을 사용한다.
---

# audit — Reverse Audit + 커버리지 검증

요구사항 도출 파이프라인의 **Phase 5**이다.
요구사항 문서가 완성된 후 "이 코드는 어느 요구사항에 반영됐는가"를 역방향으로 검증한다.

입력: `analysis_output/`, `global_call_graph.json`, `.req-analysis/1_entry_points.json`, `.req-analysis/3_rule_records.json`, `.req-analysis/6_structured_spec.json`
출력: `.req-analysis/7_audit_report.json`

---

## Step 1 — 함수 도달 가능성 분류

`analysis_output/`의 전체 함수 목록과 `global_call_graph.json`을 읽는다.

**왜 이 전처리가 필요한가**

전체 함수 목록에는 유틸 함수, 내부 헬퍼, 초기화 함수가 포함된다. 이것들을 그냥 고아 후보로 취급하면 false alarm이 너무 많아진다. 진입점에서 도달 가능한 함수와 도달 불가능한 함수를 먼저 나눠야 한다.

**분류 절차**

`.req-analysis/1_entry_points.json`의 진입점 목록을 시작 노드로 삼아
`global_call_graph.json`을 BFS 또는 DFS로 탐색한다.

탐색 결과로 함수를 두 그룹으로 분류한다:
- `reachable`: 진입점에서 호출 체인을 따라 도달 가능한 함수
- `unreachable`: 어떤 진입점에서도 도달 불가능한 함수

`unreachable` 함수는 dead code 후보다. 고아 분석 대상에서 제외하고 별도로 보고한다.

---

## Step 2 — Reverse Audit (고아 함수 탐색)

`reachable` 함수 목록을 대상으로 요구사항 문서 커버리지를 확인한다.

**매핑 확인 방법**

`.req-analysis/3_rule_records.json`의 `evidence` 필드를 읽는다.
각 Rule Record의 evidence에 기록된 `file + symbol` 쌍을 수집한다.

Rule Record에 evidence로 등장한 함수 = 요구사항에 반영된 함수
Rule Record의 evidence에 한 번도 등장하지 않은 reachable 함수 = 고아 후보

**고아 분류 기준**

고아 후보를 아래 기준으로 추가 분류한다:

- `missed_slice`: 슬라이스 생성 시 누락된 것으로 보이는 함수. Rule Record에는 없지만 entry_points에 연결된 핸들러에서 직접 호출됨.
- `utility`: 여러 도메인에서 공유하는 유틸 함수. 단일 요구사항에 귀속되지 않음 — 비기능 요구사항 또는 분석 제외 대상.
- `cross_cutting`: XC 항목으로 이미 커버된 패턴 (인증 guard 함수, 트랜잭션 래퍼 등).
- `truly_orphan`: 위 어느 범주에도 속하지 않는 진짜 고아 — 요구사항 누락 가능성 높음.

---

## Step 3 — 진입점 커버리지 검증

`.req-analysis/1_entry_points.json`의 모든 진입점이 최소 하나의 FR 또는 XC에 매핑됐는지 확인한다.

**매핑 확인 방법**

`.req-analysis/6_structured_spec.json`의 모든 FR의 `evidence_refs`와
XC의 `evidence_refs`를 수집한다.

각 진입점의 `ep_id`가 어떤 FR 또는 XC의 evidence_refs에 등장하는지 확인한다.

**미매핑 진입점 처리**

매핑 안 된 EP가 있으면:
1. 해당 EP의 Rule Record를 확인한다 (Rule Record 자체가 누락됐는가?)
2. Rule Record는 있는데 어떤 FR에도 매핑 안 됐으면 → derive 단계에서 누락된 것
3. Rule Record 자체가 없으면 → slice 단계에서 누락된 것
4. EP가 내부 전용 엔드포인트(`/internal/`, `/debug/`, `/health`)이면 → 비기능 요구사항 또는 분석 제외로 분류

---

## Step 4 — 보고서 생성

`.req-analysis/7_audit_report.json`:
```json
{
  "summary": {
    "total_reachable_functions": 0,
    "covered_by_evidence": 0,
    "orphan_candidates": 0,
    "unreachable_dead_code": 0,
    "total_entry_points": 0,
    "mapped_entry_points": 0,
    "unmapped_entry_points": 0,
    "coverage_rate": "0/0 (0%)"
  },
  "orphan_functions": [
    {
      "function_name": "legacyValidate",
      "file": "service/enrollment.go",
      "reachable": true,
      "category": "truly_orphan",
      "reason": "어떤 Rule Record의 evidence에도 등장하지 않음",
      "suggested_action": "slice 단계에서 누락 여부 재확인"
    }
  ],
  "dead_code_candidates": [
    {
      "function_name": "oldMigrationHelper",
      "file": "service/migration.go",
      "reachable": false,
      "reason": "어떤 진입점에서도 도달 불가능"
    }
  ],
  "unmapped_entry_points": [
    {
      "ep_id": "EP-089",
      "route": "GET /internal/metrics",
      "reason": "어떤 FR에도 매핑되지 않음",
      "suggested_action": "비기능 요구사항 또는 분석 제외 대상으로 분류 검토"
    }
  ],
  "recommended_rerun": {
    "slice": ["EP-089"],
    "derive": []
  }
}
```

---

## Step 5 — 재실행 권고

Audit 결과에 따라 파이프라인 재실행을 권고한다.

**slice 재실행이 필요한 경우**
- `truly_orphan` 함수가 5개 이상
- 미매핑 진입점 중 `missed_slice` 범주가 있는 경우

**derive 재실행이 필요한 경우**
- Rule Record는 있는데 FR 매핑이 안 된 EP가 있는 경우
- 이 경우 해당 EP의 Rule Record를 derive 스킬에 다시 입력한다

---

## 완료 확인

- 커버리지 80% 미만이면 경고 — slice 또는 derive 재실행 강력 권고
- `truly_orphan` 목록을 보고한다
- dead code 후보 목록을 보고한다
- 전체 커버리지 요약과 재실행 권고 사항을 보고한다
