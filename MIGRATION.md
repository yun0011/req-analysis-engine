# 스크립트 네이밍 변경 내역 (Migration Guide)

## 변경 일자
2026-05-22

## 변경 이유
- 파일명이 제각각이어서 무슨 역할인지 불명확
- Phase 1 추출과 후처리 단계가 혼재
- 통일된 네이밍 규칙 필요

## 변경 사항

### Phase 1: 정적 분석 (extract_* 프리픽스)

| 이전 파일명 | 새 파일명 | 역할 |
|-------------|-----------|------|
| `main.py` | `extract_backend.py` | Go 백엔드 AST 추출 |
| `extract_client.py` | `extract_client.py` | Vue 클라이언트 분석 (유지) |
| `build_graph.py` | `extract_call_graph.py` | Call Graph 생성 |

### 후처리 단계 (enrich_* 프리픽스)

| 이전 파일명 | 새 파일명 | 역할 |
|-------------|-----------|------|
| `extract_schemas.py` | `enrich_schemas.py` | Rule Record 스키마 추가 |
| `enrich_spec.py` | `enrich_spec.py` | Structured Spec 보강 (유지) |

### Deprecated

| 파일명 | 상태 | 사유 |
|--------|------|------|
| `main_vue.py` | `_deprecated_main_vue.py` | `extract_client.py`와 중복 |

## 마이그레이션 방법

### 1. 개별 스크립트를 직접 실행하는 경우

**이전:**
```bash
python main.py
python build_graph.py
python extract_schemas.py
```

**현재:**
```bash
python scripts/extract_backend.py
python scripts/extract_call_graph.py
python scripts/enrich_schemas.py
```

### 2. 통합 스크립트 사용 (권장)

개별 스크립트 이름을 몰라도 됩니다:

```bash
python extract.py --backend    # extract_backend.py 실행
python extract.py --graph      # extract_call_graph.py 실행
python extract.py --schemas    # enrich_schemas.py 실행
```

### 3. 다른 스크립트에서 임포트하는 경우

**이전:**
```python
import main
from build_graph import build_call_graph
import extract_schemas
```

**현재:**
```python
from scripts import extract_backend
from scripts.extract_call_graph import build_call_graph
from scripts import enrich_schemas
```

## 네이밍 규칙

### 동사 선택
- `extract_*` - 정적 분석으로 데이터 추출 (Phase 1)
- `enrich_*` - 기존 데이터에 정보 추가/보강 (후처리)

### 대상 명시
- `_backend` - Go 백엔드
- `_client` - Vue 클라이언트
- `_call_graph` - 함수 호출 그래프
- `_schemas` - 스키마 정보
- `_spec` - Structured Spec 명세

### 일관성
모든 Phase 1 스크립트는 `extract_` 프리픽스
모든 후처리 스크립트는 `enrich_` 프리픽스

## 영향받는 파일

다음 파일들이 자동으로 업데이트되었습니다:
- `extract.py` - 임포트 경로 수정
- `README.md` - 문서 업데이트
- `PIPELINE_GUIDE.md` - 가이드 업데이트

## 하위 호환성

**개별 스크립트는 여전히 독립 실행 가능합니다:**
```bash
cd scripts
python3 extract_backend.py
python3 extract_client.py
python3 extract_call_graph.py
```

**통합 스크립트는 새 파일명을 자동으로 사용합니다:**
```bash
python3 extract.py  # 알아서 scripts/extract_*.py 호출
```

## 체크리스트

- [x] 파일 리네이밍 완료
- [x] `extract.py` 임포트 경로 수정
- [x] `README.md` 업데이트
- [x] `PIPELINE_GUIDE.md` 업데이트
- [x] 마이그레이션 가이드 작성
- [ ] 테스트 실행 (`python3 extract.py --help`)
- [ ] 기존 워크플로우 확인

## 추가 정리 예정

- `_deprecated_main_vue.py` 삭제 여부 확인 (extract_client.py와 비교 후)
