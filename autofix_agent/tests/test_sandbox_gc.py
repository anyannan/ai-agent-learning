"""沙箱回收测试。

没有回收点的保留策略 = 磁盘慢慢被吃满。这类问题不会立刻报错，
只会在某天写文件失败时暴露。
"""

import os
import time

from core.sandbox_gc import sweep_stale_sandboxes


def _make_dir(root, name, age_hours):
    path = root / name
    path.mkdir()
    (path / "demo.py").write_text("x = 1\n", encoding="utf-8")
    old = time.time() - age_hours * 3600
    os.utime(path, (old, old))
    return path


def test_sweep_removes_stale_run_dirs(tmp_path):
    stale = _make_dir(tmp_path, "20260101_000000_abcdef", age_hours=48)
    fresh = _make_dir(tmp_path, "20260101_000000_ffffff", age_hours=1)

    removed = sweep_stale_sandboxes(max_age_hours=24, root=tmp_path)

    assert removed == 1
    assert not stale.exists()
    assert fresh.exists()


def test_sweep_leaves_unrelated_files_alone(tmp_path):
    """sandbox/ 下人为放的文件不能动，只清我们自己的时间戳目录。"""
    handcrafted = tmp_path / "demo.py"
    handcrafted.write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "notes").mkdir()

    assert sweep_stale_sandboxes(max_age_hours=0, root=tmp_path) == 0
    assert handcrafted.exists()
    assert (tmp_path / "notes").exists()


def test_sweep_missing_root_is_noop(tmp_path):
    assert sweep_stale_sandboxes(root=tmp_path / "nope") == 0
