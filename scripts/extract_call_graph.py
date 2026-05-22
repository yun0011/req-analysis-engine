import os
import json

def build_call_graph():
    json_dir = "./analysis_output"

    # 1. 함수 레지스트리: 함수명 → 파일 경로
    #    key를 "패키지경로::함수명"으로 구성해 동명 함수 충돌 방지
    registry = {}       # function_name → file_path (단순 조회용)
    full_registry = {}  # "file::function_name" → file_path (충돌 방지용)

    # 2. 호출 그래프: 함수명 → 호출하는 내부 함수 목록
    call_graph = {}

    # ── 1단계: 레지스트리 먼저 빌드 ──────────────────────────────
    for root, _, files in os.walk(json_dir):
        for file in files:
            if not file.endswith(".json"):
                continue
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for func in data.get("functions", []):
                func_name = func["function_name"]
                registry[func_name] = filepath
                full_registry[f"{filepath}::{func_name}"] = filepath

    internal_func_names = set(registry.keys())
    print(f"내부 함수 총계: {len(internal_func_names)}개")

    # ── 2단계: 내부 함수만 남긴 call graph 빌드 ──────────────────
    total_calls = 0
    filtered_calls = 0

    for root, _, files in os.walk(json_dir):
        for file in files:
            if not file.endswith(".json"):
                continue
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for func in data.get("functions", []):
                func_name = func["function_name"]
                raw_calls = func.get("calls", [])
                total_calls += len(raw_calls)

                # stdlib/vendor/외부 라이브러리 호출 제거
                # 함수명에 "." 이 있으면 패키지 호출 — registry에 없으면 외부
                internal_calls = []
                for call in raw_calls:
                    # "pkg.Func" 형태 → Func 부분만 체크
                    base = call.split(".")[-1] if "." in call else call
                    if base in internal_func_names or call in internal_func_names:
                        internal_calls.append(call)
                    else:
                        filtered_calls += 1

                call_graph[func_name] = list(set(internal_calls))

    print(f"전체 calls: {total_calls}개")
    print(f"외부 호출 제거: {filtered_calls}개")
    print(f"내부 호출 유지: {total_calls - filtered_calls}개")

    # ── 3단계: 역방향 그래프 (callers) 추가 ──────────────────────
    # 슬라이스 단계에서 backward traversal에 사용
    callers = {func: [] for func in call_graph}
    for caller, callees in call_graph.items():
        for callee in callees:
            if callee in callers:
                callers[callee].append(caller)

    # ── 최종 출력 ─────────────────────────────────────────────────
    final_output = {
        "registry": registry,
        "graph": call_graph,
        "callers": callers,
        "stats": {
            "total_functions": len(internal_func_names),
            "total_raw_calls": total_calls,
            "filtered_external_calls": filtered_calls,
            "internal_calls_only": True
        }
    }

    with open("global_call_graph.json", "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=4, ensure_ascii=False)

    print("\nCall Graph 생성 완료: global_call_graph.json")

if __name__ == "__main__":
    build_call_graph()
