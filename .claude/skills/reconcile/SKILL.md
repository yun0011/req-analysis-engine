# reconcile — Enum 일관성 검증 + 불일치 수정

요구사항 도출 파이프라인의 **Phase 6**이다.
요구사항 문서가 완성된 후, 문서에 사용된 코드값(enum 상수)이 실제 소스 코드와 일치하는지 역방향으로 검증하고 수정한다.

입력: `target_legacy_code/**/types/*.go`, `.req-analysis/spec/functional_requirements.json`, `.req-analysis/spec/ui_requirements.md`
출력: `.req-analysis/validation/reconcile_report.json` (수정 내역 + 잔여 충돌 목록)

---

## 왜 이 단계가 필요한가

Phase 4 (derive)에서 LLM이 자연어 요구사항을 생성할 때 enum 코드값을 hallucination한다.
예: `PROCEEDING`(실제) → `ONGOING`(LLM 추측), `FINISHED`(실제) → `GRADUATED`(StudentStatus 코드 혼입).

Phase 5 (audit)는 함수 커버리지만 검증하고 **값의 정확성**은 보지 않으므로 이런 불일치가 통과된다.
재구현 시 AI가 잘못된 enum 값을 그대로 사용하면 런타임 오류가 발생한다.

---

## 진실표 우선순위

문서 간 또는 문서와 코드 간에 불일치가 발생했을 때 아래 순서로 우선순위를 적용한다.

```
1순위  Go types/*.go               — 백엔드 enum 정의. 최우선 진실표.
2순위  UI_requirements.md          — translator.js에서 정적 추출. 코드 직접 파싱이므로 신뢰도 높음.
3순위  6_structured_spec.json      — LLM이 생성. hallucination 가능성 가장 높음. 주 수정 대상.
```

**규칙:**
- Go 코드와 다른 값이 `6_structured_spec.json`에 있으면 → `6_structured_spec.json`을 수정한다.
- Go 코드와 다른 값이 `UI_requirements.md`에 있으면 → `UI_requirements.md`를 수정한다.
- `UI_requirements.md`와 `6_structured_spec.json`이 서로 다를 때 Go 코드가 둘 중 하나와 일치하면
  → Go 코드와 다른 쪽을 수정한다.
- `UI_requirements.md`와 Go 코드가 모두 다른 값을 가지면 → `translator.js` 자체가 백엔드와
  drift된 것이므로 **자동 수정하지 않고 conflict로 표시**한다. 사람이 판단해야 한다.

**왜 `UI_requirements.md`를 2순위로 두는가**

`UI_requirements.md`는 `translator.js`에서 정적으로 추출한다. LLM 추론이 개입하지 않으므로
`6_structured_spec.json`보다 신뢰도가 높다. 불일치 발생 시 역으로 `6_structured_spec.json`의
오류를 확인하는 기준으로 사용할 수 있다.

---

## Step 1 — 소스에서 canonical enum 수집

`target_legacy_code/**/types/*.go`에서 Go enum 정의를 추출한다.

**추출 패턴:**
```go
type TermStatus string           // type alias string → enum 도메인 이름
const (
    Ready      TermStatus = "READY"      // Go 상수명 = "코드값"
    Applying   TermStatus = "APPLYING"
    Proceeding TermStatus = "PROCEEDING"
    Finished   TermStatus = "FINISHED"
)
```

결과로 도메인별 허용값 목록을 빌드한다:
```json
{
  "TermStatus":        ["READY", "APPLYING", "PROCEEDING", "FINISHED"],
  "StudentStatus":     ["ATTENDING", "LEAVE", "GRADUATED", "COMPLETED", "EXPELLED"],
  "Semester":          ["SPRING", "FALL"],
  "LectureCategory":   ["RP", "RW", "RU", "RT", "EP", "EW", "EU", "ET"],
  "RegistrationStatus":["WAITING", "APPROVED"],
  "AttendanceStatus":  ["ATTEND", "TARDY", "HALF_TARDY", "ABSENCE", "EXCUSED_ABSENCE", "EARLY_LEAVE"],
  "BoardType":         ["NOTICE", "REGULATION", "CALENDAR"],
  "Grade":             ["H1", "H2", "H3", "H4", "D1", "D2", "DJ"]
}
```

---

## Step 2 — 문서 전체 스캔

수집된 canonical enum 목록 기준으로 아래 두 문서를 **독립적으로** 스캔한다.

**스캔 순서**: `UI_requirements.md` → `6_structured_spec.json`
(UI 문서를 먼저 확인해 Go 코드와의 불일치 여부를 파악한 뒤 spec 스캔에서 참조한다)

**탐지 대상:**

1. **존재하지 않는 enum 값** — 어떤 도메인에도 속하지 않는 대문자 토큰
   - `ONGOING` → 어떤 Go type에도 없음 → hallucination
   - 단, `FR-*`, `EP-*`, `XC-*`, `CL-*`, `DG-*` 등 파이프라인 내부 ID 접두사는 제외

2. **도메인 혼입** — 올바른 값이지만 다른 도메인에 속한 값이 섞인 경우
   - TermStatus description에 `GRADUATED`(StudentStatus) 등장
   - 패턴: `"description": "학기 상태 (READY|...|GRADUATED)"` — GRADUATED는 학기 상태가 아님

3. **상태 전이 문장 불일치** — precondition이나 capability 문장의 코드값
   - `APPLYING → ONGOING → FINISHED` → ONGOING은 없음

**스캔에서 제외할 토큰:**
- 파이프라인 ID: `FR-*`, `EP-*`, `XC-*`, `CL-*`, `DG-*`
- 4자 미만 토큰 (단어 약어와 구분)
- 영문 설명의 일반 단어 (`INTERNAL`, `NULL` 등)

---

## Step 3 — 수정 대상 결정 및 수정

불일치가 발견되면 아래 흐름으로 수정 대상을 결정한다.

```
불일치 발견
    │
    ├─ Go 코드와 6_structured_spec.json 불일치
    │       → 6_structured_spec.json 수정
    │
    ├─ Go 코드와 UI_requirements.md 불일치
    │       → UI_requirements.md 수정
    │
    ├─ 6_structured_spec.json과 UI_requirements.md 불일치, Go 코드는 한쪽과 일치
    │       → Go 코드와 다른 쪽 문서를 수정
    │         (통상 6_structured_spec.json이 수정 대상)
    │
    └─ UI_requirements.md와 Go 코드가 모두 다른 값
            → 자동 수정 불가. conflict로 표시.
              translator.js와 백엔드 간 drift 가능성 → 사람이 판단
```

**자동 수정 가능한 경우** (대체값이 명확한 경우):

| 발견값 | 위치 | 수정값 | 판단 기준 |
|--------|------|--------|----------|
| `ONGOING` | `6_structured_spec.json` | `PROCEEDING` | TermStatus에 없음. types/term.go 기준. |
| TermStatus의 `GRADUATED` | `6_structured_spec.json` | `FINISHED` | GRADUATED는 StudentStatus. TermStatus 마지막 값은 FINISHED. |
| `APPLYING → ONGOING` | `6_structured_spec.json` | `APPLYING → PROCEEDING` | 동일 근거. |

정규식 치환으로 해당 문서에 일괄 적용한다.

**자동 수정 불가 — conflict로 표시하는 경우:**
- `UI_requirements.md`와 Go 코드가 모두 다른 값을 가질 때 (`translator.js` 자체 오류 가능성)
- 대체값이 2개 이상으로 추정될 때
- 도메인 자체가 불분명할 때
- 의미적 판단이 필요해 단순 치환이 부적절할 때

conflict 항목은 `validation/reconcile_report.json`의 `remaining_conflicts` 배열에 기록한다.

---

## Step 4 — 보고서 생성

`.req-analysis/validation/reconcile_report.json`:
```json
{
  "generated_at": "YYYY-MM-DD",
  "summary": {
    "enum_domains_verified": 8,
    "documents_scanned": ["6_structured_spec.json", "UI_requirements.md"],
    "total_fixes_applied": 63,
    "remaining_conflicts": 0
  },
  "truth_priority": [
    "1순위: Go types/*.go (백엔드 enum 정의)",
    "2순위: UI_requirements.md (translator.js 정적 추출)",
    "3순위: 6_structured_spec.json (LLM 생성, 주 수정 대상)"
  ],
  "canonical_enums": {
    "TermStatus": ["READY", "APPLYING", "PROCEEDING", "FINISHED"]
  },
  "fixes_applied": [
    {
      "document": "6_structured_spec.json",
      "pattern": "READY|APPLYING|PROCEEDING|GRADUATED",
      "replacement": "READY|APPLYING|PROCEEDING|FINISHED",
      "count": 57,
      "root_cause": "LLM이 StudentStatus의 GRADUATED를 TermStatus 마지막 값으로 혼동",
      "authority": "Go types/term.go + UI_requirements.md 모두 FINISHED 사용"
    }
  ],
  "documents_clean": [
    {
      "document": "UI_requirements.md",
      "result": "불일치 없음",
      "note": "translator.js에서 직접 추출했으므로 코드와 일치 보장됨"
    }
  ],
  "remaining_conflicts": [],
  "ground_truth_sources": [
    "target_legacy_code/pati-server/types/term.go"
  ]
}
```

---

## 완료 확인

- `remaining_conflicts`가 0이면 모든 문서의 enum이 소스 코드와 일치한다
- `remaining_conflicts`가 있으면 해당 항목을 사람이 검토한 후 수동 수정
- 수정 후 `6_structured_spec.json`의 JSON 유효성 확인 (파싱 오류 없어야 함)

---

## 재실행 기준

아래 상황에서 reconcile을 재실행한다:
- Phase 4 (derive)를 재실행한 경우
- 새로운 Go types가 추가된 경우
- `6_structured_spec.json`을 수동 편집한 경우
- `UI_requirements.md`를 재생성한 경우
- `translator.js`가 수정된 경우 (2순위 진실표 변경)
