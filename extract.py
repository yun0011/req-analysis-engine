#!/usr/bin/env python3
"""
Requirements Derivation Pipeline - Phase 1: Extract
통합 정적 분석 스크립트

Usage:
  python extract.py                    # 전체 실행 (백엔드 + 클라이언트 + Call Graph)
  python extract.py --backend          # 백엔드 AST만 추출
  python extract.py --client           # 클라이언트만 분석
  python extract.py --graph            # Call Graph만 생성
  python extract.py --schemas          # 스키마 추출만 (Rule Record 후)
  python extract.py --enrich           # 명세 보강만 (structured_spec 후)
  python extract.py --skip-client      # 클라이언트 제외하고 실행
"""

import os
import sys
import json
import argparse
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════
# 설정
# ═══════════════════════════════════════════════════════════════════

BASE = Path(__file__).parent
TARGET_DIR = BASE / "target_legacy_code"
BACKEND_DIR = TARGET_DIR / "pati-server"
CLIENT_DIR = TARGET_DIR / "pati-client"
ANALYSIS_OUTPUT = BASE / "analysis_output"
VUE_OUTPUT = BASE / "vue_output"
REQ_ANALYSIS = BASE / ".req-analysis"
CALL_GRAPH_FILE = BASE / "global_call_graph.json"

# ═══════════════════════════════════════════════════════════════════
# 모듈 임포트 (기존 스크립트를 함수로 래핑)
# ═══════════════════════════════════════════════════════════════════

def extract_backend():
    """백엔드 Go AST 추출 (scripts/main.py 로직)"""
    print("\n" + "="*60)
    print("Phase 1-1: 백엔드 AST 추출 (Go)")
    print("="*60)
    
    if not BACKEND_DIR.exists():
        print(f"⚠️  {BACKEND_DIR} 폴더가 없습니다. 백엔드 분석을 건너뜁니다.")
        return False
    
    # scripts/extract_backend.py 임포트하여 실행
    sys.path.insert(0, str(BASE / "scripts"))
    from scripts import extract_backend
    print(f"입력: {TARGET_DIR}")
    print(f"출력: {ANALYSIS_OUTPUT}")
    
    extract_backend.main()
    
    # 결과 확인
    if ANALYSIS_OUTPUT.exists():
        json_count = len(list(ANALYSIS_OUTPUT.rglob("*.json")))
        print(f"✓ 백엔드 AST 추출 완료: {json_count}개 JSON 파일")
        return True
    else:
        print("✗ 백엔드 AST 추출 실패")
        return False


def extract_client():
    """클라이언트 Vue 분석 (scripts/extract_client.py 로직)"""
    print("\n" + "="*60)
    print("Phase 1-2: 클라이언트 정적 분석 (Vue)")
    print("="*60)
    
    if not CLIENT_DIR.exists():
        print(f"⚠️  {CLIENT_DIR} 폴더가 없습니다. 클라이언트 분석을 건너뜁니다.")
        return False
    
    # scripts/extract_client.py 임포트하여 실행
    sys.path.insert(0, str(BASE / "scripts"))
    from scripts import extract_client
    print(f"입력: {CLIENT_DIR}")
    print(f"출력: {VUE_OUTPUT}")
    
    extract_client.main()
    
    # 결과 확인
    if VUE_OUTPUT.exists():
        json_files = list(VUE_OUTPUT.glob("*.json"))
        print(f"✓ 클라이언트 분석 완료: {len(json_files)}개 JSON 파일")
        return True
    else:
        print("✗ 클라이언트 분석 실패")
        return False


def build_call_graph():
    """Call Graph 생성 (scripts/build_graph.py 로직)"""
    print("\n" + "="*60)
    print("Phase 1-3: Call Graph 생성")
    print("="*60)
    
    if not ANALYSIS_OUTPUT.exists() or not list(ANALYSIS_OUTPUT.rglob("*.json")):
        print("⚠️  analysis_output/ 폴더가 비어있습니다. 먼저 백엔드 AST를 추출하세요.")
        return False
    
    # scripts/extract_call_graph.py 임포트하여 실행
    sys.path.insert(0, str(BASE / "scripts"))
    from scripts import extract_call_graph
    print(f"입력: {ANALYSIS_OUTPUT}")
    print(f"출력: {CALL_GRAPH_FILE}")
    
    extract_call_graph.build_call_graph()
    
    # 결과 확인
    if CALL_GRAPH_FILE.exists():
        with open(CALL_GRAPH_FILE) as f:
            data = json.load(f)
        func_count = data["stats"]["total_functions"]
        print(f"✓ Call Graph 생성 완료: {func_count}개 내부 함수")
        return True
    else:
        print("✗ Call Graph 생성 실패")
        return False


def extract_schemas():
    """스키마 추출 (scripts/extract_schemas.py 로직) - Rule Record에 추가"""
    print("\n" + "="*60)
    print("Phase 추가: Rule Record 스키마 추출")
    print("="*60)
    
    rr_file = REQ_ANALYSIS / "3_rule_records.json"
    if not rr_file.exists():
        print(f"⚠️  {rr_file} 파일이 없습니다. slice 단계를 먼저 실행하세요.")
        return False
    
    # scripts/enrich_schemas.py 실행 (모듈은 독립 실행형)
    sys.path.insert(0, str(BASE / "scripts"))
    import subprocess
    result = subprocess.run([sys.executable, str(BASE / "scripts" / "enrich_schemas.py")],
                          capture_output=True, text=True)
    
    print(result.stdout)
    if result.returncode == 0:
        print("✓ Rule Record 스키마 추가 완료")
        return True
    else:
        print("✗ Rule Record 스키마 추가 실패")
        print(result.stderr)
        return False


def enrich_structured_spec():
    """명세 보강 (scripts/enrich_spec.py 로직) - structured_spec에 스키마 추가"""
    print("\n" + "="*60)
    print("Phase 추가: Structured Spec 스키마 보강")
    print("="*60)
    
    spec_file = REQ_ANALYSIS / "6_structured_spec.json"
    if not spec_file.exists():
        print(f"⚠️  {spec_file} 파일이 없습니다. derive 단계를 먼저 실행하세요.")
        return False
    
    # scripts/enrich_spec.py 실행 (모듈은 독립 실행형)
    sys.path.insert(0, str(BASE / "scripts"))
    import subprocess
    result = subprocess.run([sys.executable, str(BASE / "scripts" / "enrich_spec.py")],
                          capture_output=True, text=True)
    
    print(result.stdout)
    if result.returncode == 0:
        print("✓ Structured Spec 스키마 보강 완료")
        return True
    else:
        print("✗ Structured Spec 스키마 보강 실패")
        print(result.stderr)
        return False


# ═══════════════════════════════════════════════════════════════════
# CLI 진입점
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Requirements Derivation Pipeline - Phase 1: Extract",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예제:
  python extract.py                    # 전체 실행
  python extract.py --backend          # 백엔드만
  python extract.py --client           # 클라이언트만
  python extract.py --graph            # Call Graph만
  python extract.py --skip-client      # 클라이언트 제외
  python extract.py --schemas          # 스키마 추출 (Phase 2 이후)
  python extract.py --enrich           # 명세 보강 (Phase 5 이후)
        """
    )
    
    parser.add_argument("--backend", action="store_true", 
                       help="백엔드 Go AST만 추출")
    parser.add_argument("--client", action="store_true",
                       help="클라이언트 Vue만 분석")
    parser.add_argument("--graph", action="store_true",
                       help="Call Graph만 생성")
    parser.add_argument("--schemas", action="store_true",
                       help="Rule Record에 스키마 추가 (Phase 2 이후)")
    parser.add_argument("--enrich", action="store_true",
                       help="Structured Spec에 스키마 보강 (Phase 5 이후)")
    parser.add_argument("--skip-client", action="store_true",
                       help="클라이언트 분석 건너뛰기")
    
    args = parser.parse_args()
    
    # 특정 단계만 실행
    if args.backend:
        return extract_backend()
    elif args.client:
        return extract_client()
    elif args.graph:
        return build_call_graph()
    elif args.schemas:
        return extract_schemas()
    elif args.enrich:
        return enrich_structured_spec()
    
    # 전체 실행 (Phase 1)
    print("\n" + "="*60)
    print("Requirements Derivation - Phase 1: Extract (전체)")
    print("="*60)
    
    results = {}
    
    # 1. 백엔드 AST
    results["backend"] = extract_backend()
    
    # 2. 클라이언트 분석 (옵션)
    if not args.skip_client:
        results["client"] = extract_client()
    else:
        print("\n⏭️  클라이언트 분석 건너뜀 (--skip-client)")
        results["client"] = None
    
    # 3. Call Graph
    if results["backend"]:
        results["graph"] = build_call_graph()
    else:
        print("\n⚠️  백엔드 AST가 없어 Call Graph를 생성할 수 없습니다.")
        results["graph"] = False
    
    # 요약
    print("\n" + "="*60)
    print("Phase 1 Extract 완료 요약")
    print("="*60)
    print(f"✓ 백엔드 AST:        {'완료' if results['backend'] else '실패'}")
    print(f"✓ 클라이언트 분석:   {'완료' if results['client'] else '건너뜀' if results['client'] is None else '실패'}")
    print(f"✓ Call Graph:        {'완료' if results['graph'] else '실패'}")
    
    print("\n산출물:")
    if results["backend"]:
        json_count = len(list(ANALYSIS_OUTPUT.rglob("*.json")))
        print(f"  - {ANALYSIS_OUTPUT}: {json_count}개 파일")
    if results["client"]:
        json_files = list(VUE_OUTPUT.glob("*.json"))
        print(f"  - {VUE_OUTPUT}: {len(json_files)}개 파일")
    if results["graph"]:
        print(f"  - {CALL_GRAPH_FILE}")
    
    print("\n다음 단계: Phase 2 slice 실행")
    print("  파이프라인 진행: python -c 'from claude.skills.slice import SKILL; ...'")
    print("  또는 run 스킬 사용")
    
    return all(v for v in results.values() if v is not None)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
