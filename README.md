# Requirements Analysis Engine

레거시 코드베이스에서 기능 요구사항을 자동으로 도출하는 파이프라인

## 특징

- **정적 분석 + LLM 기반 도출**: tree-sitter AST 파싱과 Claude Agent를 결합
- **백엔드 + 클라이언트 통합 분석**: Go 백엔드와 Vue 클라이언트를 함께 분석
- **7단계 파이프라인**: Extract → Slice → Group → Field → Derive → Audit → Reconcile
- **교차 검증**: 두 개의 독립 모델로 hallucination 최소화

## 빠른 시작

### 1. 전제 조건

```bash
# Python 3.10+ 및 의존성 설치
pip install tree-sitter-go

# 분석 대상 코드 준비 (gitignore 되어있음)
# target_legacy_code/pati-server/  # Go 백엔드
# target_legacy_code/pati-client/  # Vue 클라이언트 (선택)
```

### 2. Phase 1: 정적 분석 실행

```bash
# 전체 추출 (백엔드 + 클라이언트 + Call Graph)
python extract.py

# 또는 개별 실행
python extract.py --backend    # Go AST만
python extract.py --client     # Vue 클라이언트만
python extract.py --graph      # Call Graph만
```

**산출물:**
- `analysis_output/` - 백엔드 Go AST (JSON)
- `vue_output/` - 클라이언트 분석 결과
- `global_call_graph.json` - 함수 호출 그래프

### 3. Phase 2~7: 요구사항 도출

Cursor Agent에서 실행:

```
run 스킬을 실행해주세요
```

또는 개별 스킬 실행:
- `slice` - 진입점 추적 → Rule Record 생성
- `group` - 도메인 그룹핑
- `field` - 필드 생애주기 분석
- `derive` - 기능 요구사항 도출
- `audit` - 커버리지 검증
- `reconcile` - 불일치 해소

**산출물:**
- `.req-analysis/6_structured_spec.json` - 최종 요구사항 명세 (75개 FR)

## 프로젝트 구조

```
req-analysis-engine/
├── extract.py                 # 통합 추출 스크립트 ⭐
├── PIPELINE_GUIDE.md          # 상세 사용 가이드
├── scripts/                   # 개별 스크립트
│   ├── extract_backend.py        # Go AST 추출
│   ├── extract_client.py         # Vue 클라이언트 분석
│   ├── extract_call_graph.py     # Call Graph 생성
│   ├── enrich_schemas.py         # 스키마 추출
│   └── enrich_spec.py            # 명세 보강
├── .claude/skills/            # Agent 스킬 정의
│   ├── extract/
│   ├── slice/
│   ├── group/
│   ├── field/
│   ├── derive/
│   ├── audit/
│   └── run/                  # 파이프라인 오케스트레이터
├── target_legacy_code/        # 분석 대상 (gitignore)
├── analysis_output/           # 백엔드 AST (gitignore)
├── vue_output/                # 클라이언트 분석 (gitignore)
└── .req-analysis/             # 파이프라인 산출물
    ├── 1_entry_points.json
    ├── 2_slices.json
    ├── 3_rule_records.json
    ├── 4_domain_groups.json
    ├── 5_field_lifecycle.json
    ├── 6_structured_spec.json  # 최종 명세
    ├── 7_audit_report.json
    └── 8_reconcile_report.json
```

## 주요 산출물

### 최종 명세 (6_structured_spec.json)

```json
{
  "structured_spec": {
    "domains": [
      {
        "domain": "User",
        "features": [
          {
            "id": "FR-USER-001",
            "capability": "로그인 아이디와 비밀번호로 로그인할 수 있다",
            "trigger": {
              "actor": "unauthenticated_user",
              "action": "POST /api/v1/user/login"
            },
            "behavior": {
              "preconditions": [...],
              "postconditions": [...],
              "side_effects": [...],
              "guard_failure": [...]
            },
            "evidence_refs": ["EP-009-R-001"],
            "request_schema": {...},
            "response_schema": {...}
          }
        ]
      }
    ],
    "cross_cutting": [...]
  }
}
```

**현재 프로젝트 결과 (pati 사례):**
- 기능 요구사항: 75개 (백엔드 70, 클라이언트 5)
- 횡단 관심사: 3개
- 도메인: 15개
- 커버리지: 60개 진입점 중 60개 매핑 (100%)

## 방법론

### Phase별 역할

| Phase | 도구 | 역할 | 산출물 |
|-------|------|------|--------|
| 1. Extract | Python 정적 분석 | AST 추출, Call Graph 생성 | `analysis_output/`, `vue_output/` |
| 2. Slice | LLM | 진입점 → 슬라이스 → Rule Record | `3_rule_records.json` |
| 3. Group | LLM | 도메인 그룹핑, 클러스터링 | `4_domain_groups.json` |
| 4. Field | LLM | 필드 생애주기 제약 분석 | `5_field_lifecycle.json` |
| 5. Derive | LLM (교차검증) | 기능 요구사항 도출 | `6_structured_spec.json` |
| 6. Audit | LLM | 커버리지 검증, 고아 함수 탐지 | `7_audit_report.json` |
| 7. Reconcile | LLM | 불일치 해소 | `8_reconcile_report.json` |

### 핵심 개념

- **진입점 (Entry Point)**: HTTP 엔드포인트, 백그라운드 워커 등 외부 트리거
- **슬라이스 (Slice)**: 진입점부터 DB 접근/에러까지 추적한 코드 경로
- **Rule Record**: 슬라이스에서 추출한 규칙 (precondition, postcondition, guard 등)
- **도메인 그룹**: 비슷한 Rule Record들의 클러스터 (User, Course, Lecture 등)
- **필드 생애주기**: 필드별 불변성, 조건부 필수, 서버 할당 제약
- **기능 요구사항 (FR)**: 사용자 관점의 capability + trigger + behavior

## 활용 사례

1. **레거시 시스템 리버스 엔지니어링**
   - 문서 없는 코드베이스에서 기능 명세 자동 생성
   
2. **마이그레이션 계획 수립**
   - 현행 시스템 기능 목록화 → 신규 시스템 요구사항 정의
   
3. **API 문서 자동 생성**
   - 엔드포인트별 request/response 스키마 + 행동 규칙
   
4. **테스트 케이스 설계**
   - precondition, postcondition, guard_failure → 테스트 시나리오

## 스크립트 사용법

### 통합 실행 (권장)

```bash
# Phase 1 전체
python extract.py

# 클라이언트 제외
python extract.py --skip-client
```

### 개별 실행

```bash
# 백엔드만
python extract.py --backend
# 또는: python scripts/extract_backend.py

# 클라이언트만
python extract.py --client
# 또는: python scripts/extract_client.py

# Call Graph만
python extract.py --graph
# 또는: python scripts/extract_call_graph.py

# 스키마 추출 (Phase 2 이후)
python extract.py --schemas
# 또는: python scripts/enrich_schemas.py

# 명세 보강 (Phase 5 이후)
python extract.py --enrich
# 또는: python scripts/enrich_spec.py
```

## 문서

- **[PIPELINE_GUIDE.md](PIPELINE_GUIDE.md)** - 상세 파이프라인 가이드
- **[요구사항 도출 방법론_수정본.md](요구사항 도출 방법론_수정본.md)** - 방법론 전체 설명
- **[.claude/skills/](\.claude/skills/)** - Agent 스킬별 상세 문서

## 라이선스

MIT

## 참고

이 프로젝트는 PaTI (학원 관리 시스템) 레거시 코드베이스를 대상으로 개발 및 검증되었습니다.
