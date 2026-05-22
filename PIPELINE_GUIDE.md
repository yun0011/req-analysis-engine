# Requirements Derivation Pipeline - 스크립트 가이드

## 개요

레거시 코드베이스에서 요구사항을 자동 도출하는 파이프라인입니다.

## 디렉터리 구조

```
req-analysis-engine/
├── extract.py              # 통합 추출 스크립트 (Phase 1)
├── scripts/                # 개별 스크립트 (레거시, 직접 사용 가능)
│   ├── extract_backend.py     # Go AST 추출
│   ├── extract_client.py      # Vue 클라이언트 분석
│   ├── extract_call_graph.py  # Call Graph 생성
│   ├── enrich_schemas.py      # Rule Record 스키마 추가
│   └── enrich_spec.py         # Structured Spec 보강
├── target_legacy_code/     # 분석 대상 코드 (gitignore)
│   ├── pati-server/       # Go 백엔드
│   └── pati-client/       # Vue 클라이언트
├── analysis_output/        # 백엔드 AST (gitignore)
├── vue_output/             # 클라이언트 분석 결과 (gitignore)
├── global_call_graph.json  # Call Graph
└── .req-analysis/          # 파이프라인 산출물
    ├── 1_entry_points.json
    ├── 2_slices.json
    ├── 3_rule_records.json
    ├── 4_domain_groups.json
    ├── 5_field_lifecycle.json
    ├── 6_structured_spec.json
    ├── 7_audit_report.json
    └── 8_reconcile_report.json
```

## Phase 1: Extract (정적 분석)

### 통합 실행 (권장)

```bash
# 전체 Phase 1 실행 (백엔드 + 클라이언트 + Call Graph)
python extract.py

# 클라이언트 제외하고 실행
python extract.py --skip-client
```

### 개별 단계 실행

```bash
# 백엔드 Go AST만
python extract.py --backend

# 클라이언트 Vue만
python extract.py --client

# Call Graph만
python extract.py --graph
```

### 후처리 단계 (Phase 2~6 이후)

```bash
# Rule Record에 스키마 추가 (Phase 2 slice 후)
python extract.py --schemas

# Structured Spec 보강 (Phase 5 derive 후)
python extract.py --enrich
```

## Phase 2~7: 요구사항 도출

```bash
# run 스킬로 파이프라인 오케스트레이션
# Cursor Agent에서 실행
```

또는 개별 스킬 실행:
- Phase 2: `slice` - 진입점 → 슬라이스 → Rule Record
- Phase 3: `group` - 도메인 그룹핑
- Phase 4: `field` - 필드 생애주기 분석
- Phase 5: `derive` - 기능 도출 → Structured Spec
- Phase 6: `audit` - 커버리지 검증
- Phase 7: `reconcile` - 불일치 해소

## 전제 조건

### 필수
- Python 3.10+
- tree-sitter-go 패키지
- `target_legacy_code/pati-server/` 소스 (Go)

### 선택 (클라이언트 분석 시)
- `target_legacy_code/pati-client/` 소스 (Vue 2)

## 주요 산출물

### Phase 1 (정적 분석)
| 산출물 | 경로 | 생성 방법 |
|--------|------|----------|
| 백엔드 AST | `analysis_output/` | `python extract.py --backend` |
| 클라이언트 분석 | `vue_output/` | `python extract.py --client` |
| Call Graph | `global_call_graph.json` | `python extract.py --graph` |

### Phase 2~6 (LLM 기반 도출)
| 산출물 | 경로 | 생성 스킬 |
|--------|------|----------|
| Entry Points | `.req-analysis/1_entry_points.json` | `slice` |
| Slices | `.req-analysis/2_slices.json` | `slice` |
| Rule Records | `.req-analysis/3_rule_records.json` | `slice` |
| Domain Groups | `.req-analysis/4_domain_groups.json` | `group` |
| Field Lifecycle | `.req-analysis/5_field_lifecycle.json` | `field` |
| Structured Spec | `.req-analysis/6_structured_spec.json` | `derive` |
| Audit Report | `.req-analysis/7_audit_report.json` | `audit` |
| Reconcile Report | `.req-analysis/8_reconcile_report.json` | `reconcile` |

## 스크립트 마이그레이션 가이드

### 기존 방식 (개별 실행)
```bash
python scripts/extract_backend.py      # 백엔드 AST
python scripts/extract_client.py       # 클라이언트
python scripts/extract_call_graph.py   # Call Graph
```

### 새 방식 (통합 실행)
```bash
python extract.py           # 위 3개 한 번에
```

기존 개별 스크립트는 `scripts/` 폴더로 이동 예정이며, 여전히 직접 사용 가능합니다.

## 트러블슈팅

### `analysis_output/` 비어있음
```bash
# 백엔드 소스 확인
ls target_legacy_code/pati-server/

# 다시 추출
python extract.py --backend
```

### `vue_output/` 없음
```bash
# 클라이언트 소스 확인
ls target_legacy_code/pati-client/

# 클라이언트만 추출
python extract.py --client
```

### Call Graph 생성 실패
```bash
# 백엔드 AST 먼저 생성 필요
python extract.py --backend
python extract.py --graph
```

## 참고

- 방법론 문서: `요구사항 도출 방법론_수정본.md`
- 스킬 문서: `.claude/skills/`
- 파이프라인 오케스트레이션: `.claude/skills/run/SKILL.md`
