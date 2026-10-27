"""执行前静态防护：把代码交给解释器之前，先看它想干什么。

定位说清楚：**这不是安全边界，是拦"手滑"的护栏。**
它能挡住模型随手写出的 `shutil.rmtree` / `subprocess` / socket，
挡不住刻意绕过（`__import__("os").system`、字符串拼接出模块名、exec 生成代码都可能绕）。
所以它只做一件事：命中可疑构造就拒绝执行并转人工 —— 宁可误杀，不做赌注。

刻意**不**拦 eval / exec / compile：那属于"修复不符合规范"，由 core/policy.py 判
violated 并打回重试，语义是"能改好"，比在这里一律转人工更合适。

语法错误也不拦：交给运行时暴露成测试失败，走可重试的路径。
"""

import ast
from dataclasses import dataclass, field
from pathlib import Path

from core.ast_utils import call_sites, import_bindings

OK = "ok"
BLOCKED = "blocked"

# 直觉上"测试脚本不需要"的模块：出现即为可疑
DANGEROUS_IMPORTS = {
    "subprocess",
    "socket",
    "ctypes",
    "multiprocessing",
    "pty",
    "fcntl",
    "winreg",
    "resource",
    "shutil",
    "importlib",
    "pickle",
    "shelve",
    "requests",
    "httpx",
    "urllib",
}

# 只拦具体调用路径，不整模块封禁（os 本身是合理依赖，os.remove 不是）
DANGEROUS_CALLS = {
    "os.system",
    "os.popen",
    "os.remove",
    "os.unlink",
    "os.rmdir",
    "os.removedirs",
    "os.rename",
    "os.replace",
    "os.chdir",
    "os.kill",
    "os.fork",
    "os.execv",
    "os.execve",
    "os.putenv",
    "__import__",
}


@dataclass
class GuardResult:
    status: str = OK
    violations: list = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.status == BLOCKED

    def summary(self) -> str:
        if not self.blocked:
            return "执行前检查通过"
        return "执行前安全检查未通过：\n" + "\n".join(f"- {v}" for v in self.violations)


def scan_source(source: str, filename: str = "<source>") -> list:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # 语法错误不是安全问题的证据，交给运行时去报
        return []

    violations = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else ([node.module] if node.module else [])
            )
            for name in names:
                root = name.split(".")[0] if name else ""
                if root in DANGEROUS_IMPORTS:
                    violations.append(f"{filename}:{node.lineno} 导入了被禁止的模块 {root}")

    for call, lineno in call_sites(tree, import_bindings(tree)):
        for target in DANGEROUS_CALLS:
            if call == target or call.endswith("." + target):
                violations.append(f"{filename}:{lineno} 调用了被禁止的 {target}")
                break

    return violations


def guard_file(path) -> list:
    try:
        source = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        return [f"{path}: 无法读取（{e}）"]
    return scan_source(source, Path(path).name)


def guard_sandbox(sandbox_dir) -> GuardResult:
    """扫沙箱内所有 .py（不递归）。

    为什么要扫全部而不是只扫测试脚本：测试脚本 `import demo` 会执行 demo 的
    顶层代码，只拦测试脚本等于只锁了正门、窗户开着。
    """
    root = Path(sandbox_dir)
    violations = []
    for path in sorted(root.glob("*.py")):
        violations.extend(guard_file(path))
    if violations:
        return GuardResult(BLOCKED, violations)
    return GuardResult(OK)
