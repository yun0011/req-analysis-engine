import os
import json
import tree_sitter_go as tsgo
from tree_sitter import Language, Parser

def get_go_files(directory):
    go_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".go"):
                go_files.append(os.path.join(root, file))
    return go_files

def get_text(node, code_bytes):
    if node is None:
        return ""
    return code_bytes[node.start_byte:node.end_byte].decode('utf8')

def extract_strings(node, code_bytes):
    strings = []
    if node.type == 'interpreted_string_literal':
        strings.append(get_text(node, code_bytes).strip('"'))
    for child in node.children:
        strings.extend(extract_strings(child, code_bytes))
    return strings

# ── 라우터 패턴 판별 ──────────────────────────────────────────────
# go-json-rest: rest.Post, rest.Get, rest.Put, rest.Delete, rest.Options
# gin:          r.GET, r.POST, v1.GET, ...
# gorilla/mux:  mux.HandleFunc, router.HandleFunc
# echo:         e.GET, e.POST
# net/http:     http.HandleFunc
ROUTER_PATTERNS = [
    "rest.Post", "rest.Get", "rest.Put", "rest.Delete", "rest.Patch",
    "rest.Options", "rest.Head",
    "HandleFunc",
    ".GET(", ".POST(", ".PUT(", ".DELETE(", ".PATCH(", ".OPTIONS(",
]

def is_router_call(call_text):
    for p in ROUTER_PATTERNS:
        if p in call_text:
            return True
    return False

# ── DB 접근 패턴 판별 ─────────────────────────────────────────────
# http 클라이언트 호출은 DB 접근이 아님 (기존 코드의 버그 수정)
DB_PATTERNS   = ["db.", ".Query", ".QueryRow", ".Exec", ".Prepare", "tx."]
HTTP_CLIENT   = ["http.NewRequest", "http.Get(", "http.Post(", "http.Client",
                 "client.Do", ".Do(req"]

def is_db_call(full_call):
    for p in HTTP_CLIENT:
        if p in full_call:
            return False
    for p in DB_PATTERNS:
        if p in full_call:
            return True
    return False

# ── 에러 생성 패턴 판별 ───────────────────────────────────────────
def is_error_call(call_text):
    return ("errors.New" in call_text or
            "fmt.Errorf" in call_text or
            "errors.Errorf" in call_text)

# ── 함수 바디 분석 ────────────────────────────────────────────────
def analyze_function_body(node, code_bytes):
    if node is None:
        return [], [], [], []

    calls, db_access, errors, routers = [], [], [], []

    if node.type == 'call_expression':
        func_node = node.child_by_field_name('function')
        call_text = get_text(func_node, code_bytes)
        full_call = get_text(node, code_bytes)

        if is_router_call(call_text):
            routers.append(full_call)
        elif is_db_call(full_call):
            db_access.append(full_call)
        elif is_error_call(call_text):
            errors.extend(extract_strings(node, code_bytes))
        else:
            calls.append(call_text)

    for child in node.children:
        c, d, e, r = analyze_function_body(child, code_bytes)
        calls.extend(c); db_access.extend(d)
        errors.extend(e); routers.extend(r)

    return calls, db_access, errors, routers

# ── Struct 필드 파싱 ──────────────────────────────────────────────
def extract_struct_fields(struct_type_node, code_bytes):
    fields = []
    for child in struct_type_node.children:
        if child.type == 'field_declaration_list':
            for field in child.children:
                if field.type == 'field_declaration':
                    names = []
                    field_type = ""
                    tag = ""
                    prev_was_name = False
                    for fc in field.children:
                        if fc.type == 'field_identifier':
                            names.append(get_text(fc, code_bytes))
                            prev_was_name = True
                        elif fc.type in ('raw_string_literal', 'interpreted_string_literal'):
                            tag = get_text(fc, code_bytes).strip('`"')
                        elif prev_was_name and fc.type not in (',', '\n', ' '):
                            field_type = get_text(fc, code_bytes)
                    for name in names:
                        entry = {"name": name, "type": field_type}
                        if tag:
                            entry["tag"] = tag
                        fields.append(entry)
    return fields

# ── Import 추출 ───────────────────────────────────────────────────
def extract_imports(root_node, code_bytes):
    imports = []
    for child in root_node.children:
        if child.type == 'import_declaration':
            for imp in child.children:
                if imp.type == 'import_spec_list':
                    for spec in imp.children:
                        if spec.type == 'import_spec':
                            path_node = spec.child_by_field_name('path')
                            if path_node:
                                imports.append(get_text(path_node, code_bytes).strip('"'))
                elif imp.type == 'import_spec':
                    path_node = imp.child_by_field_name('path')
                    if path_node:
                        imports.append(get_text(path_node, code_bytes).strip('"'))
    return imports

# ── Const 추출 (도메인 상태값, 열거형) ───────────────────────────
def extract_consts(root_node, code_bytes):
    consts = []
    for child in root_node.children:
        if child.type == 'const_declaration':
            for spec in child.children:
                if spec.type == 'const_spec':
                    names = []
                    type_name = ""
                    values = []
                    for sc in spec.children:
                        if sc.type == 'identifier':
                            names.append(get_text(sc, code_bytes))
                        elif sc.type == 'type_identifier':
                            type_name = get_text(sc, code_bytes)
                        elif sc.type == 'expression_list':
                            for vc in sc.children:
                                v = get_text(vc, code_bytes).strip()
                                if v and v != ',':
                                    values.append(v.strip('"'))
                    for i, name in enumerate(names):
                        entry = {"name": name}
                        if type_name:
                            entry["type"] = type_name
                        if i < len(values):
                            entry["value"] = values[i]
                        consts.append(entry)
    return consts

# ── Interface 추출 ────────────────────────────────────────────────
def extract_interfaces(root_node, code_bytes):
    interfaces = []
    for child in root_node.children:
        if child.type == 'type_declaration':
            for spec in child.children:
                if spec.type == 'type_spec':
                    type_node = spec.child_by_field_name('type')
                    if type_node and type_node.type == 'interface_type':
                        iface_name = get_text(spec.child_by_field_name('name'), code_bytes)
                        methods = []
                        for m in type_node.children:
                            if m.type == 'method_spec':
                                method_name = get_text(m.child_by_field_name('name'), code_bytes)
                                params = get_text(m.child_by_field_name('parameters'), code_bytes)
                                result = get_text(m.child_by_field_name('result'), code_bytes)
                                methods.append({
                                    "name": method_name,
                                    "signature": f"{method_name}{params} {result}".strip()
                                })
                        interfaces.append({"name": iface_name, "methods": methods})
    return interfaces

# ── 코드 요소 재귀 추출 ───────────────────────────────────────────
def extract_code_elements(node, code_bytes):
    structs = []
    functions = []

    if node.type == 'type_declaration':
        for child in node.children:
            if child.type == 'type_spec':
                type_node = child.child_by_field_name('type')
                if type_node and type_node.type == 'struct_type':
                    struct_name = get_text(child.child_by_field_name('name'), code_bytes)
                    fields = extract_struct_fields(type_node, code_bytes)
                    structs.append({
                        "name": struct_name,
                        "fields": fields,
                        "body": get_text(type_node, code_bytes)
                    })

    elif node.type in ['function_declaration', 'method_declaration']:
        func_name = get_text(node.child_by_field_name('name'), code_bytes)
        params = get_text(node.child_by_field_name('parameters'), code_bytes)
        result = get_text(node.child_by_field_name('result'), code_bytes)

        receiver = ""
        if node.type == 'method_declaration':
            receiver = get_text(node.child_by_field_name('receiver'), code_bytes) + " "

        body_node = node.child_by_field_name('body')
        calls, db, errors, routers = analyze_function_body(body_node, code_bytes)

        functions.append({
            "function_name": func_name,
            "signature": f"func {receiver}{func_name}{params} {result}".strip(),
            "entry_points": list(set(routers)),
            "calls": list(set(calls)),
            "db_access": list(set(db)),
            "error_messages": list(set(errors))
        })

    for child in node.children:
        s, f = extract_code_elements(child, code_bytes)
        structs.extend(s)
        functions.extend(f)

    return structs, functions

# ── 메인 ──────────────────────────────────────────────────────────
def main():
    GO_LANGUAGE = Language(tsgo.language())
    parser = Parser()
    parser.language = GO_LANGUAGE

    target_dir = "./target_legacy_code"
    output_dir = "./analysis_output"

    go_files = get_go_files(target_dir)
    print(f"발견된 Go 파일: {len(go_files)}개")

    for file_path in go_files:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
            code_bytes = bytes(code, "utf8")

        tree = parser.parse(code_bytes)
        root = tree.root_node

        structs_data, functions_data = extract_code_elements(root, code_bytes)
        imports_data   = extract_imports(root, code_bytes)
        consts_data    = extract_consts(root, code_bytes)
        interfaces_data = extract_interfaces(root, code_bytes)

        relative_path = os.path.relpath(file_path, target_dir)
        save_path = os.path.join(output_dir, relative_path) + ".json"
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        file_data = {
            "file_path": file_path,
            "imports": imports_data,
            "consts": consts_data,
            "interfaces": interfaces_data,
            "structs": structs_data,
            "functions": functions_data
        }

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(file_data, f, indent=4, ensure_ascii=False)

        print(f"저장 완료: {save_path}")

    print(f"\n완료. 총 {len(go_files)}개 파일 처리됨.")

if __name__ == "__main__":
    main()
