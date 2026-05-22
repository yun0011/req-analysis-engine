import os
import re
import json

# ── Vue 2 SFC / Vuex / Router 파싱 ───────────────────────────────
# Vue 2 Options API 기반. tree-sitter 없이 regex로 충분히 커버 가능.
#
# 두 가지 추출 트랙:
#
#   Track 1 — API 호출 추출
#     백엔드와 통신하는 모든 호출을 추출한다.
#     "어떤 데이터가 백엔드로 오가는가"를 포착한다.
#
#   Track 2 — 사용자 관찰 가능 출력의 raw 사실 추출
#     사용자가 화면에서 직접 경험할 수 있는 출력(alert, 조건부 렌더링, 비활성화 등)의
#     코드 사실만 추출한다. "이게 무슨 요구사항이다"는 LLM이 해석한다.
#     내부 상태 관리(this.data=[], Vuex mutation, computed 계산 등)는
#     사용자에게 보이지 않으므로 추출하지 않는다.
#
# 역할 분리 원칙:
#   - Python/regex: 구조적 사실을 추출한다 (뭐가 불렸다, 어떤 조건이 있다)
#   - LLM (Phase 1/2 분석): 추출된 사실을 해석해 요구사항을 도출한다
#   - 분류(boundary_notification, validation_feedback 등)는 LLM의 영역이다

# ── Track 1: API 호출 패턴 ─────────────────────────────────────────
AXIOS_PATTERN = re.compile(
    r'axios\.(get|post|put|delete|patch)\s*\(\s*[`\'"]([^`\'"]+)[`\'"]',
    re.IGNORECASE
)
HTTP_PATTERN = re.compile(
    r'\$http\.(get|post|put|delete|patch)\s*\(\s*[`\'"]([^`\'"]+)[`\'"]',
    re.IGNORECASE
)
FETCH_PATTERN = re.compile(
    r'fetch\s*\(\s*[`\'"]([^`\'"]+)[`\'"](?:\s*,\s*\{[^}]*method\s*:\s*[`\'"](\w+)[`\'"])?',
    re.IGNORECASE
)

# ── Track 2: 사용자 관찰 가능 출력 — raw 사실 추출 패턴 ──────────
#
# 여기서 패턴은 "swal이 불렸다", "v-if 조건이 있다" 같은 구조적 사실만 포착한다.
# 이 사실이 어떤 요구사항인지 해석하는 것은 LLM의 역할이다.

# 2-a. 사용자에게 직접 보이는 메시지 출력
#   $swal, $toast, $message, alert, confirm, $notify 등 호출
#   → "어떤 텍스트가 어떤 함수명 안에서 사용자에게 표시됐다"는 사실 추출
ALERT_CALL_PATTERN = re.compile(
    r'(\w+)\s*\([^{]*?\)\s*\{[^}]*?'          # 함수명 + 함수 시작
    r'|'
    r'(?<!\w)(\w+)\s*\(',                       # fallback: 함수명
    re.DOTALL
)

# 메시지 텍스트 직접 추출 (함수 문맥과 분리)
ALERT_MESSAGE_PATTERNS = [
    re.compile(r'\$swal\s*\(\s*\{[^}]*?title\s*:\s*[\'"]([^\'"]+)[\'"]', re.DOTALL),
    re.compile(r'\$swal\s*\(\s*[\'"]([^\'"]+)[\'"]'),
    re.compile(r'\$toast\s*\.\s*\w+\s*\(\s*[\'"]([^\'"]{2,100})[\'"]'),
    re.compile(r'(?<!\w)alert\s*\(\s*[\'"]([^\'"]{2,100})[\'"]'),
    re.compile(r'(?<!\w)confirm\s*\(\s*[\'"]([^\'"]{2,100})[\'"]'),
    re.compile(r'\$message\s*(?:\.\s*\w+)?\s*\(\s*[\'"]([^\'"]{2,100})[\'"]'),
    re.compile(r'\$notify\s*\(\s*\{[^}]*?message\s*:\s*[\'"]([^\'"]+)[\'"]', re.DOTALL),
]

# 2-a'. 메시지가 표시되는 함수의 앞 문맥(조건, if문 등)을 함께 추출
#   → "어떤 조건일 때 이 메시지가 나왔다"를 LLM이 해석할 수 있도록
def extract_alert_with_context(script_content, component):
    """alert/swal/toast 호출을 메시지 + 앞 문맥(최대 200자)과 함께 추출한다."""
    results = []
    seen = set()
    for pattern in ALERT_MESSAGE_PATTERNS:
        for m in pattern.finditer(script_content):
            msg = m.group(1).strip()
            if not msg or msg in seen or len(msg) < 2:
                continue
            seen.add(msg)
            # 앞 200자에서 if/condition 추출
            start = max(0, m.start() - 200)
            preceding = script_content[start:m.start()]
            results.append({
                "message": msg,
                "preceding_context": preceding.strip()[-150:],  # 마지막 150자만
                "component": component
            })
    return results

# 2-b. 조건부 렌더링 — v-if / v-show 조건
#   → "어떤 조건일 때 이 요소가 보인다/숨겨진다"는 사실 추출
#   LLM이 "이 조건이 비즈니스 규칙을 표현하는가"를 판단한다
CONDITIONAL_RENDER_PATTERN = re.compile(
    r'v-(?:if|show)\s*=\s*[\'"]([^\'"]{3,200})[\'"]'
)

# 2-c. 버튼/입력 비활성화 조건 — :disabled
#   → "어떤 조건일 때 이 컨트롤이 비활성화된다"는 사실 추출
DISABLED_PATTERN = re.compile(
    r':disabled\s*=\s*[\'"]([^\'"]{2,200})[\'"]'
)

# 2-d. 클릭 핸들러 — @click / v-on:click
#   → "이 버튼을 누르면 이 메서드가 불린다"는 사실 추출
#   버튼 레이블(앞 태그의 텍스트)과 함께 추출하면 LLM 해석에 도움
CLICK_HANDLER_PATTERN = re.compile(
    r'@click(?:\.[\w.]+)?\s*=\s*[\'"]([^\'"]{1,100})[\'"]'
)

# 2-e. 폴링 — setInterval
#   → "N ms마다 반복된다"는 사실 추출
POLLING_PATTERN = re.compile(
    r'setInterval\s*\([^,]+,\s*(\d+)\s*\)'
)

# 2-f. 로딩 상태 — this.loading = true/false
#   → "이 컴포넌트가 로딩 상태를 사용자에게 표시한다"는 사실 추출
LOADING_PATTERN = re.compile(
    r'this\.(?:loading|isLoading|isFetching|isPending)\s*=\s*(true|false)'
)

# 2-g. 라이프사이클 훅 — created/mounted에서 호출되는 메서드
LIFECYCLE_PATTERN = re.compile(
    r'(?:created|mounted)\s*\(\s*\)\s*\{([^}]{1,500})\}',
    re.DOTALL
)
THIS_METHOD_PATTERN = re.compile(r'this\.(\w+)\s*\(')

# ── role/권한 분기 패턴 ───────────────────────────────────────────
ROLE_GUARD_PATTERNS = [
    re.compile(r'v-if\s*=\s*[\'"]([^\'"]*(?:role|admin|auth|permission)[^\'"]*)[\'"]', re.IGNORECASE),
    re.compile(r'if\s*\([^)]*(?:role|isAdmin|hasPermission|auth)[^)]*\)', re.IGNORECASE),
    re.compile(r'(?:roles?|permissions?)\s*(?:===?|includes?)\s*[\'"](\w+)[\'"]'),
]

# UI 문자열 (버튼 레이블 등)
UI_STRING_PATTERNS = [
    re.compile(r'>\s*([가-힣a-zA-Z][가-힣a-zA-Z0-9\s]{2,30})\s*<'),
    re.compile(r'(?:label|placeholder|title)\s*[=:]\s*[\'"]([^\'"]{2,50})[\'"]'),
]


def extract_script_section(vue_content):
    match = re.search(r'<script(?:\s+setup)?\s*>(.*?)</script>', vue_content, re.DOTALL)
    return match.group(1) if match else ""

def extract_template_section(vue_content):
    match = re.search(r'<template>(.*?)</template>', vue_content, re.DOTALL)
    return match.group(1) if match else ""

def get_component_name(script_content, file_path):
    m = re.search(r'name\s*:\s*[\'"]([^\'"]+)[\'"]', script_content)
    if m:
        return m.group(1)
    return os.path.splitext(os.path.basename(file_path))[0]


# ── Track 1: API 호출 추출 ────────────────────────────────────────
def extract_api_calls(content):
    api_calls = []
    for m in AXIOS_PATTERN.finditer(content):
        url = re.sub(r'\$\{[^}]+\}', ':param', m.group(2))
        api_calls.append({"method": m.group(1).upper(), "url": url, "raw_url": m.group(2), "client": "axios"})
    for m in HTTP_PATTERN.finditer(content):
        url = re.sub(r'\$\{[^}]+\}', ':param', m.group(2))
        api_calls.append({"method": m.group(1).upper(), "url": url, "raw_url": m.group(2), "client": "vue-resource"})
    for m in FETCH_PATTERN.finditer(content):
        url = re.sub(r'\$\{[^}]+\}', ':param', m.group(1))
        method = m.group(2).upper() if m.group(2) else "GET"
        api_calls.append({"method": method, "url": url, "raw_url": m.group(1), "client": "fetch"})
    return api_calls


# ── Track 2: 사용자 관찰 가능 출력의 raw 사실 추출 ───────────────
def extract_observable_facts(script_content, template_content, component):
    """
    사용자 관찰 가능 출력의 구조적 사실만 추출한다.
    분류(어떤 종류의 요구사항인가)는 하지 않는다. LLM의 역할이다.
    """
    facts = {}

    # 2-a. 사용자에게 표시되는 메시지 (+ 앞 문맥)
    alert_facts = extract_alert_with_context(script_content, component)
    if alert_facts:
        facts["user_messages"] = alert_facts

    # 2-b. 조건부 렌더링 조건
    cond_renders = []
    seen = set()
    for m in CONDITIONAL_RENDER_PATTERN.finditer(template_content):
        cond = m.group(1).strip()
        if cond not in seen and len(cond) >= 3:
            seen.add(cond)
            cond_renders.append(cond)
    if cond_renders:
        facts["conditional_renders"] = cond_renders

    # 2-c. 비활성화 조건
    disabled_conds = []
    seen = set()
    for m in DISABLED_PATTERN.finditer(template_content):
        cond = m.group(1).strip()
        if cond not in seen and len(cond) >= 2:
            seen.add(cond)
            disabled_conds.append(cond)
    if disabled_conds:
        facts["disabled_conditions"] = disabled_conds

    # 2-d. 클릭 핸들러
    click_handlers = []
    seen = set()
    for m in CLICK_HANDLER_PATTERN.finditer(template_content):
        handler = m.group(1).strip()
        if handler not in seen:
            seen.add(handler)
            click_handlers.append(handler)
    if click_handlers:
        facts["click_handlers"] = click_handlers

    # 2-e. 폴링
    polling = []
    for m in POLLING_PATTERN.finditer(script_content):
        polling.append({"interval_ms": int(m.group(1))})
    if polling:
        facts["polling"] = polling

    # 2-f. 로딩 상태
    loading_vals = LOADING_PATTERN.findall(script_content)
    if "true" in loading_vals and "false" in loading_vals:
        facts["has_loading_state"] = True

    # 2-g. 라이프사이클 훅에서 호출되는 메서드
    lifecycle_calls = []
    for m in LIFECYCLE_PATTERN.finditer(script_content):
        body = m.group(1)
        methods = THIS_METHOD_PATTERN.findall(body)
        lifecycle_calls.extend(methods)
    if lifecycle_calls:
        facts["lifecycle_calls"] = list(dict.fromkeys(lifecycle_calls))  # 순서 유지 dedup

    return facts


def extract_ui_strings(template_content):
    strings = []
    seen = set()
    for pattern in UI_STRING_PATTERNS:
        for m in pattern.finditer(template_content):
            s = m.group(1).strip()
            if s and s not in seen and len(s) > 1:
                seen.add(s)
                strings.append(s)
    return strings

def extract_role_guards(content):
    guards = []
    seen = set()
    for pattern in ROLE_GUARD_PATTERNS:
        for m in pattern.finditer(content):
            cond = m.group(0).strip()
            if cond not in seen:
                seen.add(cond)
                guards.append(cond)
    return guards


# ── .vue 파일 처리 ─────────────────────────────────────────────────
def process_vue_file(file_path, base_dir):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    script = extract_script_section(content)
    template = extract_template_section(content)
    rel_path = os.path.relpath(file_path, base_dir)
    component_name = get_component_name(script, file_path)

    return {
        "file_path": rel_path,
        "component_name": component_name,
        "api_calls": extract_api_calls(script),               # Track 1 — 직접 HTTP 호출
        "vuex_dispatches": extract_vuex_dispatches(script),   # Track 1 — Vuex dispatch
        "observable_facts": extract_observable_facts(         # Track 2
            script, template, rel_path
        ),
        "ui_strings": extract_ui_strings(template),
        "role_guards": extract_role_guards(script + template)
    }


# ── Vuex store .js 처리 ───────────────────────────────────────────
def process_vuex_store(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    api_calls = extract_api_calls(content)
    if not api_calls:
        return None

    action_names = re.findall(
        r'(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{[^}]*axios\.', content
    )
    module_name = os.path.splitext(os.path.basename(file_path))[0]
    return {"file_path": file_path, "store_module": module_name, "actions": action_names, "api_calls": api_calls}


# ── Vuex dispatch 추출 ───────────────────────────────────────────
VUEX_DISPATCH_PATTERN = re.compile(
    r'\$store\.dispatch\s*\(\s*[\'"](\w+)[\'"]'
)

def extract_vuex_dispatches(script_content):
    """this.$store.dispatch('actionName', ...) 패턴을 추출한다."""
    dispatches = []
    seen = set()
    for m in VUEX_DISPATCH_PATTERN.finditer(script_content):
        action = m.group(1)
        if action not in seen:
            seen.add(action)
            dispatches.append(action)
    return dispatches


# ── Vue Router .js 처리 ──────────────────────────────────────────
def process_router_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # path 위치와 값을 모두 수집
    path_pattern = re.compile(r'path\s*:\s*[\'"]([^\'"]+)[\'"]')
    # lazy import 패턴: () => import('@/views/...')  또는 resolve => require(...)
    component_pattern = re.compile(
        r'component\s*:\s*(?:\(\s*\)\s*=>\s*import\s*\(\s*[\'"]([^\'"]+)[\'"]'
        r'|resolve\s*=>\s*\w+\(\[?[\'"]([^\'"]+)[\'"]'
        r'|(\w+)\s*(?:,|\n|\r))'
    )

    path_matches  = list(path_pattern.finditer(content))
    comp_matches  = list(component_pattern.finditer(content))

    routes = []
    for i, pm in enumerate(path_matches):
        path = pm.group(1)
        next_pos = path_matches[i + 1].start() if i + 1 < len(path_matches) else len(content)

        # 이 path 선언 이후 ~ 다음 path 선언 이전 구간에서 component 찾기
        comp_path = None
        for cm in comp_matches:
            if pm.start() < cm.start() < next_pos:
                # group(1): lazy import, group(2): require, group(3): 직접 참조
                raw = cm.group(1) or cm.group(2) or cm.group(3)
                if raw:
                    # @/ 제거 후 정규화
                    comp_path = raw.replace('@/', '').strip()
                break

        route = {"path": path}
        if comp_path:
            route["component_path"] = comp_path

        # requiresAuth 플래그
        segment = content[pm.start():next_pos]
        auth_m = re.search(r'requiresAuth\s*:\s*(true|false)', segment, re.IGNORECASE)
        if auth_m:
            route["requiresAuth"] = auth_m.group(1) == "true"

        # roles
        roles_m = re.search(r'roles\s*:\s*\[([^\]]+)\]', segment)
        if roles_m:
            route["roles"] = [r.strip().strip("'\"") for r in roles_m.group(1).split(",")]

        routes.append(route)

    return {"file_path": file_path, "routes": routes}


# ── 메인 ──────────────────────────────────────────────────────────
def main():
    frontend_dir = "./target_legacy_code/pati-client/src"
    output_dir   = "./vue_output"

    if not os.path.exists(frontend_dir):
        print(f"frontend 폴더 없음: {frontend_dir} — 건너뜀")
        return

    os.makedirs(output_dir, exist_ok=True)

    vue_results   = []
    vuex_results  = []
    route_results = []

    for root, _, files in os.walk(frontend_dir):
        for file in files:
            file_path = os.path.join(root, file)
            if file.endswith(".vue"):
                vue_results.append(process_vue_file(file_path, frontend_dir))
            elif file.endswith(".js"):
                if "store" in root.lower() or "module" in root.lower():
                    result = process_vuex_store(file_path)
                    if result:
                        vuex_results.append(result)
                elif "router" in root.lower() or file in ("index.js", "router.js"):
                    result = process_router_file(file_path)
                    if result.get("routes"):
                        route_results.append(result)

    # ── Track 1 출력 ──────────────────────────────────────────────
    vuex_api_map = {"actions": []}
    for store in vuex_results:
        for call in store["api_calls"]:
            vuex_api_map["actions"].append({
                "store_module": store["store_module"],
                "action_names": store["actions"],
                "http_method": call["method"],
                "url": call["url"],
                "file": store["file_path"]
            })
    with open(os.path.join(output_dir, "vuex_api_map.json"), 'w', encoding='utf-8') as f:
        json.dump(vuex_api_map, f, indent=4, ensure_ascii=False)

    # routes.json — component_path 포함
    routes_output = {"routes": [r for rs in route_results for r in rs["routes"]]}
    with open(os.path.join(output_dir, "routes.json"), 'w', encoding='utf-8') as f:
        json.dump(routes_output, f, indent=4, ensure_ascii=False)

    # component → route 경로 역매핑 (component_path의 마지막 세그먼트로 매칭)
    component_to_routes = {}
    for rs in route_results:
        for route in rs["routes"]:
            comp_path = route.get("component_path")
            if not comp_path:
                continue
            # 정규화: src/ 제거, 슬래시 정규화
            normalized = comp_path.replace("src/", "").lstrip("/")
            if normalized not in component_to_routes:
                component_to_routes[normalized] = []
            component_to_routes[normalized].append(route["path"])

    # component_map — api_calls, vuex_dispatches, route_paths 모두 포함
    component_map = []
    for v in vue_results:
        comp_file = v["file_path"]   # e.g. "views/academic_info/rule/Rule.vue"
        route_paths = component_to_routes.get(comp_file, [])
        entry = {
            "component": comp_file,
            "component_name": v["component_name"],
            "route_paths": route_paths,
            "vuex_dispatches": v["vuex_dispatches"],
            "api_calls": v["api_calls"],
            "role_guards": v["role_guards"]
        }
        if entry["api_calls"] or entry["vuex_dispatches"] or entry["route_paths"]:
            component_map.append(entry)
    with open(os.path.join(output_dir, "component_map.json"), 'w', encoding='utf-8') as f:
        json.dump({"components": component_map}, f, indent=4, ensure_ascii=False)

    # ── Track 2 출력: observable_facts.json ───────────────────────
    #   "이 컴포넌트에서 관찰된 raw 사실들" — LLM이 해석할 원료
    observable_map = [
        {"component": v["file_path"], "component_name": v["component_name"],
         "observable_facts": v["observable_facts"]}
        for v in vue_results if v["observable_facts"]
    ]
    with open(os.path.join(output_dir, "observable_facts.json"), 'w', encoding='utf-8') as f:
        json.dump({"components": observable_map}, f, indent=4, ensure_ascii=False)

    # ── 파이프라인 호환: client_behaviors.json ────────────────────
    #   기존 파이프라인(slice/derive)이 읽는 파일. observable_facts를 그대로 담는다.
    with open(os.path.join(output_dir, "client_behaviors.json"), 'w', encoding='utf-8') as f:
        json.dump({"components": observable_map}, f, indent=4, ensure_ascii=False)

    # ── 통계 ──────────────────────────────────────────────────────
    total_api = sum(len(v["api_calls"]) for v in vue_results)
    total_dispatch = sum(len(v["vuex_dispatches"]) for v in vue_results)
    total_routed = sum(1 for v in vue_results if component_to_routes.get(v["file_path"]))
    total_msg = sum(len(v["observable_facts"].get("user_messages", [])) for v in vue_results)
    total_cond = sum(len(v["observable_facts"].get("conditional_renders", [])) for v in vue_results)
    total_disabled = sum(len(v["observable_facts"].get("disabled_conditions", [])) for v in vue_results)
    total_click = sum(len(v["observable_facts"].get("click_handlers", [])) for v in vue_results)
    total_polling = sum(len(v["observable_facts"].get("polling", [])) for v in vue_results)

    print(f"\n=== Vue 분석 완료 ===")
    print(f".vue 파일:              {len(vue_results)}개")
    print(f"Vuex store:             {len(vuex_results)}개")
    print(f"Router 파일:            {len(route_results)}개")
    print(f"\n[Track 1 — API 호출]")
    print(f"  컴포넌트 직접 API 호출: {total_api}개")
    print(f"  컴포넌트 Vuex dispatch: {total_dispatch}개 (route-linked: {total_routed}개 컴포넌트)")
    print(f"  Vuex store API 호출:    {len(vuex_api_map['actions'])}개")
    print(f"  Routes:                 {len(routes_output['routes'])}개 (component_path 연결: {sum(1 for r in routes_output['routes'] if r.get('component_path'))}개)")
    print(f"\n[Track 2 — 관찰 가능 출력 raw 사실]")
    print(f"  사용자 메시지:        {total_msg}개  (alert/swal/toast + 앞 문맥)")
    print(f"  조건부 렌더링:        {total_cond}개  (v-if/v-show 조건)")
    print(f"  비활성화 조건:        {total_disabled}개  (:disabled)")
    print(f"  클릭 핸들러:          {total_click}개  (@click)")
    print(f"  폴링:                 {total_polling}개  (setInterval)")
    print(f"\n출력 파일:")
    print(f"  vue_output/vuex_api_map.json")
    print(f"  vue_output/routes.json")
    print(f"  vue_output/component_map.json")
    print(f"  vue_output/observable_facts.json   ← Track 2 (raw 사실, LLM 해석용)")
    print(f"  vue_output/client_behaviors.json   ← 파이프라인 호환 (observable_facts 동일)")


if __name__ == "__main__":
    main()
