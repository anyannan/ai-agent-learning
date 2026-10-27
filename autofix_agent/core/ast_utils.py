"""AST 小工具：把调用还原成全限定名。

policy.py 与 guard.py 都要做"源码里有没有出现 X"的判定，
共用同一套名字解析，避免两处判定对同一个写法给出不同结论。
"""

import ast


def dotted(node):
    """把 Name / Attribute 链还原成点号路径，如 ast.literal_eval。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def import_bindings(tree) -> dict:
    """收集本地名 → 全限定名，用于把 safe_calc 还原成 corp_sec.safe_calc。"""
    bindings = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                bindings[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                head = alias.asname or alias.name.split(".")[0]
                bindings[head] = alias.name if alias.asname else head
    return bindings


def resolve(name: str, bindings: dict) -> str:
    head, _, tail = name.partition(".")
    if head in bindings:
        resolved = bindings[head]
        return f"{resolved}.{tail}" if tail else resolved
    return name


def name_matches(call: str, target: str) -> bool:
    call = call.removeprefix("builtins.")
    return call == target or call.endswith("." + target)


def call_sites(tree, bindings=None):
    """返回 [(全限定名, 行号)]。"""
    bindings = bindings if bindings is not None else import_bindings(tree)
    sites = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = dotted(node.func)
            if name:
                sites.append((resolve(name, bindings), node.lineno))
    return sites
