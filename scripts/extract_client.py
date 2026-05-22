#!/usr/bin/env python3
"""
Phase 1 확장 — pati-client 정적 분석
출력: vue_output/ 하위 5개 파일
  routes.json          — 라우트 → 컴포넌트 → 권한 (비트마스크 디코딩 포함)
  api_map.json         — client.js 메서드 → HTTP method + URL
  component_map.json   — 컴포넌트 → 호출한 Client 메서드 → EP-ID → FR-ID
  client_behaviors.json — 폴링 / 조건 분기 / 자동 로딩 / 비가역성 패턴
  client_only_reqs.json — 백엔드 FR에 없는 클라이언트 전용 요구사항
"""

import os
import re
import json

BASE           = "/Users/sds/Documents/Personal_Github/req-analysis-engine"
CLIENT_ROOT    = f"{BASE}/target_legacy_code/pati-client/src"
OUT_DIR        = f"{BASE}/vue_output"
REQ_DIR        = f"{BASE}/.req-analysis"
TRANSLATOR_JS  = f"{CLIENT_ROOT}/plugins/translator.js"

os.makedirs(OUT_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────
# 권한 비트마스크 디코딩
# ─────────────────────────────────────────────────────────────
PERM_BITS = {1: "Admin", 2: "Employee", 4: "Professor", 8: "Student"}

# translator.js $funcName → 도메인 이름 매핑
TRANSLATOR_FUNC_TO_DOMAIN = {
    'termStatusKR':  'TermStatus',
    'semesterKR':    'Semester',
    'gradeKR':       'Grade',
    'gradeENG':      'GradeEnglish',
    'gradeStatusKR': 'StudentStatus',
    'statusKR':      'RequestStatus',
    'categoryKR':    'LectureCategory',
    'categoryENG':   'LectureCategoryEnglish',
}

def decode_perm(mask: int) -> list[str]:
    return [role for bit, role in sorted(PERM_BITS.items()) if mask & bit]


# ─────────────────────────────────────────────────────────────
# 0. translator.js 파싱 → display label 매핑
# ─────────────────────────────────────────────────────────────

def parse_translator_js(path: str) -> dict:
    """
    plugins/translator.js의 Vue.prototype.$funcName switch 문에서
    value→label 매핑을 추출한다.
    반환: { 'termStatusKR': {'READY': '준비 중', ...}, ... }
    """
    try:
        with open(path, encoding='utf-8') as f:
            src = f.read()
    except FileNotFoundError:
        return {}

    labels = {}
    # Vue.prototype.$funcName으로 분할
    blocks = re.split(r'Vue\.prototype\.\$', src)
    for block in blocks[1:]:
        name_m = re.match(r'(\w+)', block)
        if not name_m:
            continue
        func_name = name_m.group(1)
        # case "VAL":\n      return "LABEL"; 패턴
        pairs = re.findall(
            r"case\s+['\"]([^'\"]+)['\"]\s*:\s*\n\s*return\s+['\"]([^'\"]+)['\"]",
            block
        )
        if pairs:
            labels[func_name] = {v: label for v, label in pairs}

    return labels


# ─────────────────────────────────────────────────────────────
# 1. api/client.js 파싱 → api_map.json
# ─────────────────────────────────────────────────────────────

def parse_client_js(path: str) -> dict:
    """
    class Client { methodName(params) { ... axios.post('/url') } }
    → { method_name: {http_method, url, params} }
    """
    with open(path) as f:
        src = f.read()

    api_map = {}

    # 각 메서드 블록 추출: 메서드명( params ) { ... }
    # 중첩 중괄호 카운팅으로 body 범위 결정
    method_header = re.compile(
        r'(?:async\s+)?(\w+)\s*\(([^)]*)\)\s*\{', re.MULTILINE
    )

    for m in method_header.finditer(src):
        method_name = m.group(1)
        if method_name in ('constructor', 'class', 'if', 'for', 'while', 'switch'):
            continue

        params_raw = m.group(2).strip()
        params = [p.strip() for p in params_raw.split(',') if p.strip()]

        # body 추출 (중괄호 매칭)
        start = m.end() - 1  # '{' 위치
        depth = 0
        body_start = start
        body_end = start
        for i in range(start, min(start + 3000, len(src))):
            if src[i] == '{':
                depth += 1
            elif src[i] == '}':
                depth -= 1
                if depth == 0:
                    body_end = i
                    break

        body = src[body_start:body_end + 1]

        # axios 호출 탐지
        axios_m = re.search(
            r'axios\.(get|post|put|delete|patch)\s*\(\s*[\'"`]([^\'"`]+)[\'"`]',
            body, re.IGNORECASE
        )
        if axios_m:
            api_map[method_name] = {
                "client_method": method_name,
                "http_method": axios_m.group(1).upper(),
                "url": axios_m.group(2),
                "params": params,
            }

        # URL 반환 패턴 (downloadDrive처럼 URL 문자열 반환)
        elif 'return `' in body or "return '" in body:
            url_m = re.search(r'return\s+[\'"`]([^\'"`;]+/api/[^\'"`;]+)[\'"`]', body)
            if url_m:
                api_map[method_name] = {
                    "client_method": method_name,
                    "http_method": "GET",
                    "url": re.sub(r'\$\{[^}]+\}', ':param', url_m.group(1)),
                    "params": params,
                }

    return api_map


# ─────────────────────────────────────────────────────────────
# 2. router/index.js 파싱 → routes.json
# ─────────────────────────────────────────────────────────────

def parse_router(path: str) -> list[dict]:
    with open(path) as f:
        src = f.read()

    routes = []

    # 각 route 객체: { path: '...', ... }
    # path: 로 시작하는 객체 블록을 중괄호 카운팅으로 추출
    route_start = re.compile(r'\{\s*\n?\s*path\s*:')
    for m in route_start.finditer(src):
        start = m.start()
        depth = 0
        end = start
        for i in range(start, min(start + 2000, len(src))):
            if src[i] == '{':
                depth += 1
            elif src[i] == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break

        block = src[start:end + 1]

        # path 추출
        path_m = re.search(r"path\s*:\s*['\"]([^'\"]+)['\"]", block)
        if not path_m:
            continue
        route_path = path_m.group(1)

        # name 추출
        name_m = re.search(r"name\s*:\s*['\"]([^'\"]+)['\"]", block)
        name = name_m.group(1) if name_m else None

        # component 파일 경로 추출
        comp_m = re.search(r"import\s*\(\s*['\"](@/[^'\"]+)['\"]", block)
        component_file = comp_m.group(1).replace('@/', 'src/') if comp_m else None

        # meta 블록 추출
        meta_m = re.search(r'meta\s*:\s*\{([^}]+)\}', block)
        meta_str = meta_m.group(1) if meta_m else ''

        # needsPermission 비트마스크
        perm_m = re.search(r'needsPermission\s*:\s*(\d+)', meta_str)
        perm_mask = int(perm_m.group(1)) if perm_m else None

        # 특수 가드
        needs_graduated     = bool(re.search(r'needsGraduated\s*:\s*true', meta_str))
        needs_not_graduated = bool(re.search(r'needsNotGraduated\s*:\s*true', meta_str))

        routes.append({
            "path": route_path,
            "name": name,
            "component_file": component_file,
            "requires_auth": 'requireAuth' in block,
            "permission_bitmask": perm_mask,
            "required_roles": decode_perm(perm_mask) if perm_mask else [],
            "needs_graduated": needs_graduated,
            "needs_not_graduated": needs_not_graduated,
        })

    return routes


# ─────────────────────────────────────────────────────────────
# 3. 각 Vue 컴포넌트 파싱
# ─────────────────────────────────────────────────────────────

def split_sfc(src: str) -> tuple[str, str]:
    """<template>과 <script> 블록 분리."""
    tmpl_m = re.search(r'<template>([\s\S]*?)</template>', src)
    script_m = re.search(r'<script>([\s\S]*?)</script>', src)
    template = tmpl_m.group(1) if tmpl_m else ''
    script   = script_m.group(1) if script_m else ''
    return template, script


def extract_client_calls(script: str) -> list[str]:
    """Client.methodName( 호출 추출."""
    return list(dict.fromkeys(
        re.findall(r'Client\.(\w+)\s*\(', script)
    ))

def extract_this_method_calls(script: str) -> list[str]:
    """this.methodName( 호출 추출 (간접 Client 호출 감지용)."""
    raw = re.findall(r'this\.(\w+)\s*\(', script)
    # Vue 내장 / 라이프사이클 / store 접근자 제외
    skip = {'$store', '$router', '$swal', '$error', '$emit', '$refs',
            '$moment', '$base64Decode', '$asciiDecode', '$categoryKR',
            '$semesterKR', '$termStatusKR', 'go', 'push', 'replace',
            'showLoading', 'close'}
    return list(dict.fromkeys(m for m in raw if m not in skip))


def extract_dispatch_calls(script: str) -> list[str]:
    """this.$store.dispatch('actionName') 추출."""
    return list(dict.fromkeys(
        re.findall(r"dispatch\s*\(\s*['\"](\w+)['\"]", script)
    ))


def extract_lifecycle_calls(script: str) -> dict:
    """created() / mounted() 에서 호출되는 Client 메서드 및 dispatch 추출.
    직접 호출뿐 아니라 this.methodName() 간접 호출도 포함."""
    result = {}
    for hook in ('created', 'mounted'):
        hook_m = re.search(rf'{hook}\s*\(\s*\)\s*\{{', script)
        if not hook_m:
            continue
        start = hook_m.end() - 1
        depth = 0
        end = start
        for i in range(start, min(start + 1000, len(script))):
            if script[i] == '{':
                depth += 1
            elif script[i] == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        body = script[start:end + 1]
        direct_calls    = extract_client_calls(body)
        dispatches      = extract_dispatch_calls(body)
        indirect_calls  = extract_this_method_calls(body)  # this.loadList() 등
        if direct_calls or dispatches or indirect_calls:
            result[hook] = {
                "client_calls":       direct_calls,
                "dispatch_calls":     dispatches,
                "indirect_this_calls": indirect_calls,
            }
    return result


def extract_polling(script: str) -> list[dict]:
    """setInterval 패턴 탐지. 직접 Client 호출 및 this.method() 간접 호출 모두 감지."""
    pollings = []
    for m in re.finditer(r'setInterval\s*\(', script):
        paren_depth = 0
        body_end = m.start()
        for i in range(m.start(), min(m.start() + 3000, len(script))):
            if script[i] == '(':
                paren_depth += 1
            elif script[i] == ')':
                paren_depth -= 1
                if paren_depth == 0:
                    body_end = i
                    break

        full_call = script[m.start():body_end + 1]

        # delay
        delay_m = re.search(r',\s*(\d+)\s*\)\s*;?\s*$', full_call.strip())
        delay_ms = int(delay_m.group(1)) if delay_m else None

        # 직접 Client 호출 + 간접 this.method() 호출
        direct_api   = extract_client_calls(full_call)
        indirect_api = extract_this_method_calls(full_call)
        dispatch_api = extract_dispatch_calls(full_call)

        # 종료 조건: clearInterval 직전 if 조건 (계속 실행 조건)
        # 패턴: if (this.x == 'PENDING') { ...; return; }  clearInterval(...)
        continue_m = re.search(
            r'if\s*\(([^)]+)\)\s*\{[^}]*return[^}]*\}[^}]*clearInterval',
            full_call, re.DOTALL
        )
        # 역전시켜 "이 조건이 아닐 때 종료"로 표현
        if continue_m:
            raw_cond = continue_m.group(1).strip()
            termination = f"NOT ({raw_cond})"
        else:
            termination_m = re.search(r'if\s*\(([^)]+)\)[^{]*\{[^}]*clearInterval', full_call)
            termination = termination_m.group(1).strip() if termination_m else None

        # 성공 조건
        success_m = re.search(
            r'(?:isRegistration\w+|registration_id)\s*[!=]=+\s*\w+', full_call
        )
        success_cond = success_m.group(0).strip() if success_m else None

        pollings.append({
            "type": "polling",
            "interval_ms": delay_ms,
            "api_called_direct": direct_api,
            "api_called_indirect": indirect_api,  # this.getRequestStatusByID() 등
            "dispatch_called": dispatch_api,
            "termination_condition": termination,
            "success_condition": success_cond,
        })
    return pollings


def extract_conditional_api(script: str, template: str = "") -> list[dict]:
    """
    조건부 API 분기 탐지:
    1. script 내 if/else 블록에서 양쪽에 다른 Client/this 메서드 호출
    2. template @click 속성에서 삼항 연산자로 다른 메서드 호출
    """
    branches = []

    # ── template @click 삼항 연산자 ──────────────────────────
    # @click="cond ? methodA() : methodB()"
    click_ternary = re.compile(
        r'@click\s*=\s*"([^"]*(?:semester|term|type|status|SPRING|FALL)[^"]*)\?'
        r'\s*(\w+)\s*\(\)'
        r'\s*:\s*(\w+)\s*\(\)"',
        re.IGNORECASE
    )
    for m in click_ternary.finditer(template):
        branches.append({
            "type": "conditional_api",
            "pattern": "template_ternary",
            "condition": m.group(1).strip(),
            "true_branch_method": m.group(2),
            "false_branch_method": m.group(3),
            "source": "template",
        })

    # ── script 3항 연산자 ─────────────────────────────────────
    ternary = re.compile(
        r'([^\n;]+(?:semester|term|type|status|role|SPRING|FALL)[^\n;]*)\?'
        r'\s*(\w+)\s*\(\)'
        r'\s*:\s*(\w+)\s*\(\)',
        re.IGNORECASE
    )
    for m in ternary.finditer(script):
        branches.append({
            "type": "conditional_api",
            "pattern": "script_ternary",
            "condition": m.group(1).strip(),
            "true_branch_method": m.group(2),
            "false_branch_method": m.group(3),
            "source": "script",
        })

    # ── script if/else 블록 ───────────────────────────────────
    if_else = re.compile(
        r'if\s*\(([^)]*(?:SPRING|FALL|semester|type|status)[^)]*)\)\s*\{([^}]*)\}'
        r'\s*(?:else\s*\{([^}]*)\})?',
        re.IGNORECASE
    )
    for m in if_else.finditer(script):
        true_client  = re.findall(r'Client\.(\w+)\s*\(', m.group(2) or '')
        false_client = re.findall(r'Client\.(\w+)\s*\(', m.group(3) or '')
        true_this    = extract_this_method_calls(m.group(2) or '')
        false_this   = extract_this_method_calls(m.group(3) or '')
        if true_client or false_client or true_this or false_this:
            branches.append({
                "type": "conditional_api",
                "pattern": "if_else",
                "condition": m.group(1).strip(),
                "true_branch":  {"client": true_client, "this_methods": true_this},
                "false_branch": {"client": false_client, "this_methods": false_this},
                "source": "script",
            })

    return branches


def extract_confirmation_guards(script: str) -> list[dict]:
    """
    inputValidator 안의 '정확한 텍스트를 입력해야 하는' 비가역성 패턴 탐지.
    ex) value !== "종강하겠습니다."
    """
    guards = []
    # inputValidator 블록 추출
    for m in re.finditer(r'inputValidator\s*:\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{', script):
        start = m.end() - 1
        depth = 0
        end = start
        for i in range(start, min(start + 500, len(script))):
            if script[i] == '{':
                depth += 1
            elif script[i] == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        body = script[start:end + 1]

        # 비교 문자열 추출
        cmp_m = re.search(r'!==\s*[\'"]([^\'"]{2,50})[\'"]', body)
        if cmp_m:
            # 어떤 Client 메서드가 이 확인 이후에 호출되는지 (전후 컨텍스트에서 탐색)
            context_start = max(0, m.start() - 800)
            context = script[context_start: m.start() + 200]
            nearby_calls = extract_client_calls(context)

            guards.append({
                "type": "confirmation_guard",
                "required_text": cmp_m.group(1),
                "nearby_api_calls": nearby_calls,
            })

    return guards


def extract_disabled_guards(template: str) -> list[dict]:
    """:disabled 바인딩에서 도메인 상태 기반 가드 탐지.
    속성값이 따옴표를 포함할 수 있으므로 균형잡힌 따옴표 추출."""
    guards = []
    # :disabled="..." 에서 content 추출 (내부에 작은따옴표 포함 가능)
    for m in re.finditer(r':disabled\s*=\s*"((?:[^"\\]|\\.)*)"', template):
        cond = m.group(1)
        if any(kw in cond for kw in ('FINISHED', 'status', 'enabled', 'isAdmin', 'role', 'Admin')):
            guards.append({
                "type": "disabled_guard",
                "condition": cond,
            })
    return guards


def extract_select_options(template: str) -> list[dict]:
    """<select> 안의 <option> 정적 값 추출 — 도메인 상수."""
    results = []
    for sel_m in re.finditer(r'<select[^>]*>([\s\S]*?)</select>', template):
        block = sel_m.group(1)
        opts = re.findall(r'<option[^>]*value=[\'"]([^\'"]+)[\'"][^>]*>([^<]+)</option>', block)
        if opts:
            values = [{"value": v, "label": l.strip()} for v, l in opts if v]
            results.append({"options": values})
    return results


def extract_page_title(template: str) -> str | None:
    """<p class="title"> 또는 <p class="solo_title"> 에서 브레드크럼 텍스트 추출."""
    m = re.search(r'<p\s+class=[\'"](?:title|solo_title)[\'"][^>]*>([^<]+)</p>', template)
    return m.group(1).strip() if m else None


def extract_table_columns(template: str) -> list[str]:
    """<thead> 안의 <td> 텍스트에서 컬럼 헤더 추출 (빈 셀 제외)."""
    # v-if가 없는 첫 번째 <tr> 블록 우선 사용; 없으면 첫 tr
    thead_m = re.search(r'<thead>([\s\S]*?)</thead>', template)
    if not thead_m:
        return []
    thead = thead_m.group(1)

    # v-if가 없는 <tr>을 먼저 시도
    tr_blocks = list(re.finditer(r'<tr([^>]*)>([\s\S]*?)</tr>', thead))
    chosen_block = None
    for tr in tr_blocks:
        if 'v-if' not in tr.group(1):
            chosen_block = tr.group(2)
            break
    if chosen_block is None and tr_blocks:
        chosen_block = tr_blocks[0].group(2)
    if chosen_block is None:
        return []

    columns = []
    for td_m in re.finditer(r'<td[^>]*>([^<]*)</td>', chosen_block):
        text = td_m.group(1).strip()
        if text:
            columns.append(text)
    return columns


def extract_form_fields(template: str) -> list[dict]:
    """
    <tbody> 안의 <tr>에서 레이블 셀 + 입력 셀 쌍을 추출한다.
    패턴: <td>..label..</td><td><input|select|textarea ...></td>
    """
    fields = []
    tbody_m = re.search(r'<tbody>([\s\S]*?)</tbody>', template)
    if not tbody_m:
        return fields
    tbody = tbody_m.group(1)

    for tr_m in re.finditer(r'<tr[^>]*>([\s\S]*?)</tr>', tbody):
        row = tr_m.group(1)
        tds = re.findall(r'<td[^>]*>([\s\S]*?)</td>', row)
        for i in range(len(tds) - 1):
            next_td = tds[i + 1]
            if not ('<input' in next_td or '<select' in next_td or '<textarea' in next_td):
                continue
            # 레이블 텍스트: HTML 태그 제거
            label_text = re.sub(r'<[^>]+>', '', tds[i]).strip()
            if not label_text:
                continue
            vmodel_m = re.search(r'v-model\s*=\s*[\'"]([^\'"]+)[\'"]', next_td)
            itype_m  = re.search(r'type\s*=\s*[\'"]([^\'"]+)[\'"]', next_td)
            # 항상-비활성 필드 탐지: :disabled="true" / disabled (조건부 아닌 것)
            disabled_m = re.search(r':disabled\s*=\s*[\'"]([^\'"]+)[\'"]', next_td)
            if disabled_m:
                disabled_val = disabled_m.group(1).strip()
                # "true" 리터럴이거나 단순 변수(공백/연산자 없음)가 아닌 경우만 unconditional
                is_immutable = disabled_val == 'true'
            else:
                is_immutable = bool(re.search(r'\bdisabled\b(?!\s*=)', next_td) or
                                    re.search(r'\breadonly\b(?!\s*=)', next_td))
            fields.append({
                "label":      label_text,
                "v_model":    vmodel_m.group(1) if vmodel_m else None,
                "input_type": itype_m.group(1) if itype_m else (
                    "select" if '<select' in next_td else
                    "textarea" if '<textarea' in next_td else "text"
                ),
                "required":   bool(re.search(r'class=[\'"][^\'"]*(needs)[^\'"]* [\'"]', tds[i]) or
                                   '<span class="needs">*' in tds[i]),
                "immutable":  is_immutable,
            })
    return fields


def extract_vfor_fields(template: str) -> list[str]:
    """
    v-for 루프 변수에서 접근되는 데이터 필드 이름 추출.
    ex) v-for="l in lectureList" → l.id, l.name, ... → ['id', 'name', ...]
    """
    fields: set[str] = set()
    _skip = {'length', 'toString', 'valueOf', 'constructor', 'key', 'index'}

    for vfor_m in re.finditer(
        r'v-for\s*=\s*[\'"](?:\((\w+)(?:,\s*\w+)?\)|(\w+))\s+in\s+\w+[\'"]',
        template
    ):
        var = vfor_m.group(1) or vfor_m.group(2)
        if not var:
            continue
        for field_m in re.finditer(rf'\b{re.escape(var)}\.(\w+)', template):
            field = field_m.group(1)
            if field not in _skip:
                fields.add(field)

    return sorted(fields)


def process_vue_file(file_path: str, rel_path: str, api_map: dict) -> dict:
    with open(file_path, encoding='utf-8') as f:
        src = f.read()

    template, script = split_sfc(src)

    client_calls = extract_client_calls(script)
    dispatch_calls = extract_dispatch_calls(script)
    lifecycle = extract_lifecycle_calls(script)
    pollings = extract_polling(script)
    cond_apis = extract_conditional_api(script, template)
    confirm_guards = extract_confirmation_guards(script)
    disabled_guards = extract_disabled_guards(template)
    select_opts = extract_select_options(template)
    page_title = extract_page_title(template)
    table_columns = extract_table_columns(template)
    form_fields = extract_form_fields(template)
    vfor_fields = extract_vfor_fields(template)

    # Client 메서드 → URL 해석
    resolved_calls = []
    for method in client_calls:
        if method in api_map:
            resolved_calls.append({
                "client_method": method,
                "http_method": api_map[method]["http_method"],
                "url": api_map[method]["url"],
            })
        else:
            resolved_calls.append({"client_method": method})

    return {
        "file": rel_path,
        "client_calls": client_calls,
        "resolved_api_calls": resolved_calls,
        "store_dispatches": dispatch_calls,
        "lifecycle_auto_calls": lifecycle,
        "polling": pollings,
        "conditional_api_branches": cond_apis,
        "confirmation_guards": confirm_guards,
        "disabled_guards": disabled_guards,
        "domain_constants": select_opts,
        "page_title": page_title,
        "table_columns": table_columns,
        "form_fields": form_fields,
        "vfor_fields": vfor_fields,
    }


# ─────────────────────────────────────────────────────────────
# 4. store/index.js 파싱
# ─────────────────────────────────────────────────────────────

def parse_store(path: str, api_map: dict) -> dict:
    with open(path, encoding='utf-8') as f:
        src = f.read()

    # actions: 각 action → 호출하는 Client 메서드
    actions = {}
    action_pattern = re.compile(
        r'(?:async\s+)?(\w+)\s*\(\s*\{[^}]*\}\s*(?:,\s*[^)]+)?\)\s*\{', re.MULTILINE
    )
    for m in action_pattern.finditer(src):
        name = m.group(1)
        if name in ('login', 'logout', 'state', 'commit', 'dispatch', 'getters',
                    'rootState', 'rootGetters', 'if', 'for', 'while'):
            continue
        start = m.end() - 1
        depth = 0
        end = start
        for i in range(start, min(start + 1500, len(src))):
            if src[i] == '{':
                depth += 1
            elif src[i] == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        body = src[start:end + 1]
        calls = extract_client_calls(body)
        if calls:
            resolved = [{"client_method": c, "url": api_map.get(c, {}).get("url")} for c in calls]
            actions[name] = {"client_calls": calls, "resolved": resolved}

    # getters: 도메인 필터링 로직 탐지
    getters_with_filter = []
    getter_pattern = re.compile(
        r'(\w+)\s*\(\s*state\s*\)\s*\{[\s\S]{0,500}?if\s*\([^)]+\)\s*\{[\s\S]{0,200}?return\s+\w+',
    )
    for m in getter_pattern.finditer(src):
        name = m.group(1)
        if name in ('state', 'getters', 'if', 'for'):
            continue
        # 필터 조건 추출
        cond_m = re.search(r'if\s*\(([^)]+)\)', src[m.start():m.start() + 600])
        if cond_m:
            getters_with_filter.append({
                "getter": name,
                "filter_condition": cond_m.group(1).strip(),
            })

    # state 필드 (persistent via localStorage)
    state_m = re.search(r'state\s*:\s*\{([^}]+)\}', src)
    state_fields = re.findall(r'(\w+)\s*:', state_m.group(1)) if state_m else []
    state_fields = [f for f in state_fields if f not in ('isLogin', 'sessionID', 'user')]

    return {
        "actions": actions,
        "getters_with_domain_filter": getters_with_filter,
        "persistent_state_fields": state_fields,
    }


# ─────────────────────────────────────────────────────────────
# 5. EP-ID / FR-ID 매핑 로드
# ─────────────────────────────────────────────────────────────

def load_ep_fr_maps():
    """URL → EP-ID, EP-ID → FR-ID 매핑 빌드."""
    url_to_ep = {}
    try:
        with open(f"{REQ_DIR}/1_entry_points.json") as f:
            eps = json.load(f)["entry_points"]
        for ep in eps:
            route = ep.get("route", "")
            if route:
                # 정규화: /api/v1/... 형태로
                url_to_ep[route.lower()] = ep["ep_id"]
    except FileNotFoundError:
        pass

    ep_to_fr = {}
    try:
        with open(f"{REQ_DIR}/6_structured_spec.json") as f:
            spec = json.load(f)["structured_spec"]
        for domain in spec.get("domains", []):
            for fr in domain.get("features", []):
                for ref in fr.get("evidence_refs", []):
                    if re.match(r"EP-\d+", ref):
                        ep_id = re.match(r"(EP-\d+)", ref).group(1)
                        ep_to_fr.setdefault(ep_id, []).append(fr["id"])
    except FileNotFoundError:
        pass

    return url_to_ep, ep_to_fr


def resolve_fr(url: str, http_method: str, url_to_ep: dict, ep_to_fr: dict) -> dict:
    """URL → EP-ID → FR-ID 체이닝."""
    # entry_points는 method + route 형태 ex) "POST /api/v1/user/list"
    key = f"{http_method.upper()} {url}".lower()
    # url만으로도 매칭 시도
    ep_id = url_to_ep.get(key) or url_to_ep.get(url.lower())
    if not ep_id:
        # URL 부분 매치 시도
        for k, v in url_to_ep.items():
            if url.lower() in k:
                ep_id = v
                break
    fr_ids = ep_to_fr.get(ep_id, []) if ep_id else []
    return {"ep_id": ep_id, "fr_ids": fr_ids}


# ─────────────────────────────────────────────────────────────
# 6. client_only_reqs 생성
# ─────────────────────────────────────────────────────────────

def build_client_only_reqs(routes: list, components: list, store: dict,
                            url_to_ep: dict, ep_to_fr: dict) -> list[dict]:
    reqs = []
    req_id = 1

    # 6-a. 라우터 가드 → 요구사항
    guard_templates = {
        "needs_graduated": {
            "description": "졸업 상태인 학생만 해당 페이지에 접근할 수 있다",
            "actor": "graduated_student",
        },
        "needs_not_graduated": {
            "description": "재학/수료/제적 상태인 학생만 해당 페이지에 접근할 수 있다",
            "actor": "enrolled_student",
        },
    }
    for route in routes:
        for guard_key, tmpl in guard_templates.items():
            if route.get(guard_key):
                reqs.append({
                    "req_id": f"CL-{req_id:03d}",
                    "type": "access_guard",
                    "source": "router/index.js",
                    "route": route["path"],
                    "condition": guard_key,
                    "description": f"{route['path']} — {tmpl['description']}",
                    "actor": tmpl["actor"],
                    "backend_fr": None,  # audit 단계에서 연결
                })
                req_id += 1

    # 6-b. 컴포넌트 비가역성 확인 가드
    for comp in components:
        for cg in comp.get("confirmation_guards", []):
            nearby = cg.get("nearby_api_calls", [])
            fr_ids = []
            for method in nearby:
                url = ""
                http = "POST"
                # api_map에서 URL 가져오기
                for resolved in comp.get("resolved_api_calls", []):
                    if resolved["client_method"] == method:
                        url = resolved.get("url", "")
                        http = resolved.get("http_method", "POST")
                mapped = resolve_fr(url, http, url_to_ep, ep_to_fr)
                fr_ids.extend(mapped["fr_ids"])

            reqs.append({
                "req_id": f"CL-{req_id:03d}",
                "type": "irreversibility_guard",
                "source": comp["file"],
                "required_confirmation_text": cg["required_text"],
                "description": f"'{cg['required_text']}' 텍스트 입력 확인 후에만 작업을 진행할 수 있다",
                "nearby_api_calls": nearby,
                "related_fr_ids": list(dict.fromkeys(fr_ids)),
            })
            req_id += 1

    # 6-c. store getters 도메인 필터링 → 요구사항
    for getter in store.get("getters_with_domain_filter", []):
        reqs.append({
            "req_id": f"CL-{req_id:03d}",
            "type": "client_side_filter",
            "source": "store/index.js",
            "getter": getter["getter"],
            "filter_condition": getter["filter_condition"],
            "description": f"클라이언트는 '{getter['filter_condition']}' 조건으로 데이터를 필터링하여 표시한다",
            "backend_fr": None,
        })
        req_id += 1

    # 6-d. 폴링 흐름 → 요구사항
    for comp in components:
        for poll in comp.get("polling", []):
            api_calls = poll.get("api_called", [])
            reqs.append({
                "req_id": f"CL-{req_id:03d}",
                "type": "async_polling",
                "source": comp["file"],
                "interval_ms": poll["interval_ms"],
                "api_polled": api_calls,
                "termination_condition": poll["termination_condition"],
                "success_condition": poll["success_condition"],
                "description": (
                    f"{poll['interval_ms']}ms 간격으로 {api_calls}를 폴링하며 "
                    f"'{poll.get('termination_condition', '?')}' 조건이 충족될 때 종료한다"
                ),
                "backend_fr": None,
            })
            req_id += 1

    # 6-e. lifecycle 자동 로딩 → 요구사항 (applyingTerm 컨텍스트 등)
    for comp in components:
        lc = comp.get("lifecycle_auto_calls", {})
        for hook, calls in lc.items():
            dispatches = calls.get("dispatch_calls", [])
            for d in dispatches:
                if "Term" in d or "term" in d:
                    reqs.append({
                        "req_id": f"CL-{req_id:03d}",
                        "type": "auto_context",
                        "source": comp["file"],
                        "lifecycle_hook": hook,
                        "store_action": d,
                        "description": f"페이지 진입 시 '{d}' 액션을 자동 실행해 학기 컨텍스트를 설정한다",
                        "backend_fr": None,
                    })
                    req_id += 1

    return reqs


# ─────────────────────────────────────────────────────────────
# display_labels.json 빌더
# ─────────────────────────────────────────────────────────────

def build_display_labels(translator_labels: dict, components: list) -> dict:
    """
    translator.js 함수 매핑 + 컴포넌트 select 옵션을 통합해
    display_labels.json 내용 반환.
    """
    # 1. translator.js 함수 → 도메인 레이블
    labels: dict[str, dict] = {}
    for func_name, mapping in translator_labels.items():
        domain = TRANSLATOR_FUNC_TO_DOMAIN.get(func_name, func_name)
        labels[domain] = mapping

    # 2. 컴포넌트 select 옵션 집계 (signature로 중복 제거)
    seen_sigs: set[tuple] = set()
    select_option_groups: list[list[dict]] = []
    for comp in components:
        for opt_group in comp.get('domain_constants', []):
            options = opt_group.get('options', [])
            if not options:
                continue
            sig = tuple(sorted((o['value'], o['label']) for o in options if o.get('value')))
            if sig not in seen_sigs:
                seen_sigs.add(sig)
                select_option_groups.append(options)

    return {
        "labels": labels,
        "select_option_constants": select_option_groups,
        "source_summary": {
            "translator_functions": list(translator_labels.keys()),
            "components_with_select": sum(
                1 for c in components if c.get('domain_constants')
            ),
        },
    }


# ─────────────────────────────────────────────────────────────
# ui_structure.json 빌더
# ─────────────────────────────────────────────────────────────

def build_ui_structure(components: list) -> dict:
    """
    컴포넌트별 UI 구조 정보(페이지 제목, 테이블 컬럼, 폼 필드, 리스트 필드)를
    페이지 단위로 집계한다. 구조 정보가 하나도 없는 컴포넌트는 제외한다.
    """
    pages = []
    for comp in components:
        has_ui = (
            comp.get('page_title')
            or comp.get('table_columns')
            or comp.get('form_fields')
            or comp.get('vfor_fields')
        )
        if not has_ui:
            continue
        pages.append({
            "component":       comp["file"],
            "route":           comp.get("route"),
            "required_roles":  comp.get("required_roles", []),
            "breadcrumb":      comp.get("page_title"),
            "table_columns":   comp.get("table_columns", []),
            "form_fields":     comp.get("form_fields", []),
            "list_item_fields": comp.get("vfor_fields", []),
        })
    return {"pages": pages}


# ─────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────

def main():
    print("=== pati-client 정적 분석 시작 ===\n")

    # Step 0: translator.js 파싱 (display label 매핑)
    translator_labels = parse_translator_js(TRANSLATOR_JS)
    print(f"[0/7] translator.js: {len(translator_labels)}개 필터 함수 파싱")

    # Step 1: api/client.js 파싱
    client_js = f"{CLIENT_ROOT}/api/client.js"
    api_map = parse_client_js(client_js)
    print(f"[1/7] api/client.js: {len(api_map)}개 메서드 → URL 매핑")
    with open(f"{OUT_DIR}/api_map.json", "w") as f:
        json.dump({"methods": list(api_map.values())}, f, ensure_ascii=False, indent=2)

    # Step 2: router/index.js 파싱
    router_js = f"{CLIENT_ROOT}/router/index.js"
    routes = parse_router(router_js)
    print(f"[2/7] router/index.js: {len(routes)}개 라우트")
    with open(f"{OUT_DIR}/routes.json", "w") as f:
        json.dump({"routes": routes}, f, ensure_ascii=False, indent=2)

    # Step 3: store/index.js 파싱
    store_js = f"{CLIENT_ROOT}/store/index.js"
    store = parse_store(store_js, api_map)
    print(f"[3/7] store/index.js: {len(store['actions'])}개 action, "
          f"{len(store['getters_with_domain_filter'])}개 도메인 getter")

    # Step 4: 모든 Vue 컴포넌트 파싱
    components = []
    vue_root = CLIENT_ROOT
    all_vues = []
    for root, _, files in os.walk(vue_root):
        for fn in files:
            if fn.endswith(".vue"):
                all_vues.append(os.path.join(root, fn))

    for fp in sorted(all_vues):
        rel = os.path.relpath(fp, CLIENT_ROOT)
        result = process_vue_file(fp, rel, api_map)
        # 라우트 정보 연결 (component_file로 매칭)
        for route in routes:
            if route["component_file"] and rel in route["component_file"].replace("src/", ""):
                result["route"] = route["path"]
                result["required_roles"] = route["required_roles"]
                result["needs_graduated"] = route["needs_graduated"]
                result["needs_not_graduated"] = route["needs_not_graduated"]
                break
        components.append(result)

    print(f"[4/7] Vue 컴포넌트: {len(components)}개 처리")

    # EP/FR 매핑 로드
    url_to_ep, ep_to_fr = load_ep_fr_maps()

    # component_map.json: component → resolved API → FR-ID
    component_map = []
    for comp in components:
        if not comp["client_calls"] and not comp["store_dispatches"]:
            continue  # API 호출 없는 순수 UI 컴포넌트 제외
        entry = {
            "file": comp["file"],
            "route": comp.get("route"),
            "required_roles": comp.get("required_roles", []),
            "api_calls": [],
            "store_dispatches": comp["store_dispatches"],
            "has_polling": bool(comp["polling"]),
            "has_conditional_api": bool(comp["conditional_api_branches"]),
            "has_auto_load": bool(comp["lifecycle_auto_calls"]),
            "has_confirmation_guard": bool(comp["confirmation_guards"]),
        }
        for call in comp["resolved_api_calls"]:
            fr_info = {}
            if call.get("url"):
                fr_info = resolve_fr(
                    call["url"], call.get("http_method", "POST"),
                    url_to_ep, ep_to_fr
                )
            entry["api_calls"].append({**call, **fr_info})
        component_map.append(entry)

    with open(f"{OUT_DIR}/component_map.json", "w") as f:
        json.dump({"components": component_map}, f, ensure_ascii=False, indent=2)

    # Step 5: display_labels.json
    display_labels_data = build_display_labels(translator_labels, components)
    with open(f"{OUT_DIR}/display_labels.json", "w") as f:
        json.dump(display_labels_data, f, ensure_ascii=False, indent=2)
    label_domain_count = len(display_labels_data["labels"])
    select_group_count = len(display_labels_data["select_option_constants"])
    print(f"[5/7] display_labels.json: {label_domain_count}개 도메인 레이블, "
          f"{select_group_count}개 select 옵션 그룹")

    # Step 6: ui_structure.json
    ui_structure_data = build_ui_structure(components)
    with open(f"{OUT_DIR}/ui_structure.json", "w") as f:
        json.dump(ui_structure_data, f, ensure_ascii=False, indent=2)
    pages_with_cols  = sum(1 for p in ui_structure_data["pages"] if p["table_columns"])
    pages_with_form  = sum(1 for p in ui_structure_data["pages"] if p["form_fields"])
    pages_with_vfor  = sum(1 for p in ui_structure_data["pages"] if p["list_item_fields"])
    print(f"[6/7] ui_structure.json: {len(ui_structure_data['pages'])}개 페이지 "
          f"(테이블 헤더 {pages_with_cols}개, 폼 필드 {pages_with_form}개, "
          f"리스트 필드 {pages_with_vfor}개)")

    # client_behaviors.json
    behaviors = []
    for comp in components:
        for poll in comp["polling"]:
            behaviors.append({"component": comp["file"], **poll})
        for cond in comp["conditional_api_branches"]:
            behaviors.append({"component": comp["file"], **cond})
        for lc_hook, lc_data in comp["lifecycle_auto_calls"].items():
            behaviors.append({
                "component": comp["file"],
                "type": "auto_load",
                "lifecycle_hook": lc_hook,
                **lc_data,
            })
        for cg in comp["confirmation_guards"]:
            behaviors.append({"component": comp["file"], **cg})
        for dg in comp["disabled_guards"]:
            behaviors.append({"component": comp["file"], **dg})

    with open(f"{OUT_DIR}/client_behaviors.json", "w") as f:
        json.dump({"behaviors": behaviors}, f, ensure_ascii=False, indent=2)

    # client_only_reqs.json
    client_reqs = build_client_only_reqs(routes, components, store, url_to_ep, ep_to_fr)
    with open(f"{OUT_DIR}/client_only_reqs.json", "w") as f:
        json.dump({"requirements": client_reqs}, f, ensure_ascii=False, indent=2)

    # Step 7: FR에 ui_evidence 역방향 추가
    fr_ui_map: dict[str, list] = {}
    for comp in component_map:
        for call in comp["api_calls"]:
            for fr_id in call.get("fr_ids", []):
                fr_ui_map.setdefault(fr_id, []).append({
                    "component": comp["file"],
                    "route": comp.get("route"),
                    "required_roles": comp.get("required_roles", []),
                })

    # structured_spec.json 업데이트
    try:
        with open(f"{REQ_DIR}/6_structured_spec.json") as f:
            spec = json.load(f)
        for domain in spec["structured_spec"]["domains"]:
            for fr in domain["features"]:
                fr["ui_evidence"] = fr_ui_map.get(fr["id"], [])
        with open(f"{REQ_DIR}/6_structured_spec.json", "w") as f:
            json.dump(spec, f, ensure_ascii=False, indent=2)
        print(f"[7/7] 6_structured_spec.json에 ui_evidence 추가 완료")
    except FileNotFoundError:
        print("[7/7] 6_structured_spec.json 없음 — ui_evidence 추가 건너뜀")

    # 요약
    poll_count  = sum(1 for b in behaviors if b.get("type") == "polling")
    cond_count  = sum(1 for b in behaviors if b.get("type") == "conditional_api")
    auto_count  = sum(1 for b in behaviors if b.get("type") == "auto_load")
    conf_count  = sum(1 for b in behaviors if b.get("type") == "confirmation_guard")
    disabled_ct = sum(1 for b in behaviors if b.get("type") == "disabled_guard")

    print(f"\n=== 완료 ===")
    print(f"출력 디렉토리: {OUT_DIR}/")
    print(f"  api_map.json          — {len(api_map)}개 메서드")
    print(f"  routes.json           — {len(routes)}개 라우트")
    print(f"  component_map.json    — {len(component_map)}개 컴포넌트 (API 호출 있는 것)")
    print(f"  display_labels.json   — {label_domain_count}개 도메인 레이블 + {select_group_count}개 select 그룹")
    print(f"  ui_structure.json     — {len(ui_structure_data['pages'])}개 페이지")
    print(f"    테이블 헤더:          {pages_with_cols}개 페이지")
    print(f"    폼 필드:              {pages_with_form}개 페이지")
    print(f"    리스트 필드:          {pages_with_vfor}개 페이지")
    print(f"  client_behaviors.json — {len(behaviors)}개 행동 패턴")
    print(f"    polling:             {poll_count}개")
    print(f"    conditional_api:     {cond_count}개")
    print(f"    auto_load:           {auto_count}개")
    print(f"    confirmation_guard:  {conf_count}개")
    print(f"    disabled_guard:      {disabled_ct}개")
    print(f"  client_only_reqs.json — {len(client_reqs)}개 클라이언트 전용 요구사항")

    # FR 커버리지 (ui_evidence 있는 FR 수)
    covered = sum(1 for frs in fr_ui_map.values() if frs)
    print(f"\n  FR ↔ UI 연결: {covered}개 FR에 ui_evidence 추가됨")


if __name__ == "__main__":
    main()
