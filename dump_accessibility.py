from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from collections import Counter
from importlib.metadata import version
from pathlib import Path
from typing import Any

import xa11y

PROJECT_DIR = Path(__file__).resolve().parent
HEADERS = ("Name", "Value", "Notes")
ROWS = (
    ("Alpha", "10", "first row"),
    ("Bravo", "20", "second row"),
    ("Charlie", "30", "third row"),
    ("Delta", "40", "fourth row"),
    ("Echo", "50", "fifth row"),
)
TABLE_PREFIXES = {
    "QTableWidget example": "W",
    "QTableView example": "V",
    "QTableView no headers": "N",
}
TABLE_EXPECTED_HEADERS = {
    "QTableWidget example": HEADERS,
    "QTableView example": HEADERS,
    "QTableView no headers": (),
}
EXPECTED_CELL_NAMES = {
    table_name: tuple(
        f"{prefix}{row}C{column}: {value}"
        for row, values in enumerate(ROWS)
        for column, value in enumerate(values)
    )
    for table_name, prefix in TABLE_PREFIXES.items()
}


def bounds_dict(bounds: Any) -> dict[str, int] | None:
    if bounds is None:
        return None
    return {
        "x": bounds.x,
        "y": bounds.y,
        "width": bounds.width,
        "height": bounds.height,
    }


def element_data(element: Any) -> dict[str, Any]:
    return {
        "role": element.role,
        "name": element.name,
        "value": element.value,
        "description": element.description,
        "stable_id": element.stable_id,
        "bounds": bounds_dict(element.bounds),
        "actions": list(element.actions),
        "states": {
            "enabled": element.enabled,
            "visible": element.visible,
            "focused": element.focused,
            "selected": element.selected,
            "focusable": element.focusable,
        },
        "raw": dict(element.raw),
    }


def snapshot(element: Any, depth: int) -> dict[str, Any]:
    result = element_data(element)
    result["children"] = []
    if depth <= 0:
        return result
    children = element.children()
    result["child_count"] = len(children)
    result["children"] = [snapshot(child, depth - 1) for child in children]
    return result


def flatten(root: dict[str, Any]) -> list[dict[str, Any]]:
    result = [root]
    for child in root.get("children", []):
        result.extend(flatten(child))
    return result


def stop_process(process: subprocess.Popen[bytes], app_pid: int) -> None:
    if sys.platform == "win32" and app_pid != process.pid:
        subprocess.run(
            ["taskkill", "/PID", str(app_pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    elif process.poll() is None:
        process.terminate()

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Launch the native PySide6 table application and dump its "
            "accessibility tree through xa11y."
        )
    )
    parser.add_argument(
        "--app",
        type=Path,
        default=PROJECT_DIR / "qt_table_app.py",
        help="Qt application script to launch.",
    )
    parser.add_argument(
        "--attach-pid",
        type=int,
        help="Attach to an already-running reproducer instead of launching it.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT_DIR / "captures" / platform.system().lower(),
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument(
        "--expect-table-cells",
        action="store_true",
        help=(
            "Exit non-zero if any known data cell is normalized to a role "
            "other than table_cell."
        ),
    )
    parser.add_argument("--keep-open", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    process: subprocess.Popen[bytes] | None = None
    pid = 0
    stdout_handle = None
    stderr_handle = None
    try:
        if args.attach_pid is None:
            app_script = args.app.resolve()
            if not app_script.is_file():
                raise FileNotFoundError(app_script)
            stdout_handle = (args.out / "qt-app.stdout.log").open("wb")
            stderr_handle = (args.out / "qt-app.stderr.log").open("wb")
            pid_file = args.out / "qt-app.pid"
            pid_file.unlink(missing_ok=True)
            environment = os.environ.copy()
            environment["XA11Y_TABLE_PID_FILE"] = str(pid_file.resolve())
            if sys.platform.startswith("linux"):
                environment.setdefault("QT_LINUX_ACCESSIBILITY_ALWAYS_ON", "1")
            process = subprocess.Popen(
                [sys.executable, str(app_script)],
                cwd=app_script.parent,
                env=environment,
                stdout=stdout_handle,
                stderr=stderr_handle,
            )
            pid = process.pid
            deadline = time.monotonic() + args.timeout
            while not pid_file.exists():
                if process.poll() is not None:
                    raise RuntimeError(
                        f"Qt app exited during startup with {process.returncode}"
                    )
                if time.monotonic() >= deadline:
                    raise TimeoutError("Timed out waiting for the Qt app PID file")
                time.sleep(0.05)
            pid = int(pid_file.read_text(encoding="ascii"))
            print(f"Launched Qt table app (PID {pid}, wrapper PID {process.pid})")
        else:
            pid = args.attach_pid
            print(f"Attaching to PID {pid}")

        app = xa11y.App.by_pid(pid, timeout=args.timeout)
        print(f"Attached to {app.name!r} (PID {app.pid})")
        time.sleep(0.3)

        (args.out / "application.txt").write_text(
            app.dump(max_depth=args.depth), encoding="utf-8"
        )
        (args.out / "application.json").write_text(
            json.dumps(app.tree(max_depth=args.depth), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        table_reports = []
        failures = []
        for table_name in TABLE_PREFIXES:
            locator = app.locator(f'table[name="{table_name}"]')
            table = locator.wait_visible(timeout=10.0)
            tree = snapshot(table, args.depth)
            nodes = flatten(tree)
            by_name = {
                node["name"]: node for node in nodes if node.get("name") is not None
            }

            expected_cells = EXPECTED_CELL_NAMES[table_name]
            missing_cells = [name for name in expected_cells if name not in by_name]
            cells = [by_name[name] for name in expected_cells if name in by_name]
            role_counts = Counter(cell["role"] for cell in cells)
            misclassified = [
                {"name": cell["name"], "role": cell["role"], "raw": cell["raw"]}
                for cell in cells
                if cell["role"] != "table_cell"
            ]
            expected_headers = TABLE_EXPECTED_HEADERS[table_name]
            found_headers = [name for name in HEADERS if name in by_name]
            missing_headers = [name for name in expected_headers if name not in by_name]
            unexpected_headers = [
                name for name in found_headers if name not in expected_headers
            ]

            print(f"\n=== {table_name} ===")
            print(f"Known cells found: {len(cells)}/{len(expected_cells)}")
            print(f"Known cell roles: {dict(role_counts)}")
            print(f"Direct children: {tree.get('child_count', 0)}")
            for cell in cells:
                print(
                    f"  {cell['name']!r}: role={cell['role']} "
                    f"raw={cell['raw']}"
                )

            if missing_cells:
                failures.append(f"{table_name}: missing cells {missing_cells}")
            if missing_headers:
                failures.append(f"{table_name}: missing headers {missing_headers}")
            if unexpected_headers:
                print(
                    f"Visible headers despite headers being hidden: "
                    f"{unexpected_headers}"
                )
            if args.expect_table_cells and misclassified:
                failures.append(
                    f"{table_name}: {len(misclassified)} cells were not table_cell"
                )

            safe_name = table_name.lower().replace(" ", "-")
            (args.out / f"{safe_name}.txt").write_text(
                table.dump(max_depth=args.depth), encoding="utf-8"
            )
            table_reports.append(
                {
                    "name": table_name,
                    "expected_cell_count": len(expected_cells),
                    "found_cell_count": len(cells),
                    "known_cell_role_counts": dict(role_counts),
                    "missing_cells": missing_cells,
                    "expected_headers": list(expected_headers),
                    "found_headers": found_headers,
                    "missing_headers": missing_headers,
                    "unexpected_headers": unexpected_headers,
                    "misclassified_cells": misclassified,
                    "tree": tree,
                }
            )

        if process is not None and process.poll() is not None:
            failures.append(f"Qt app exited unexpectedly with {process.returncode}")

        report = {
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "python": platform.python_version(),
                "pyside6": version("PySide6"),
                "xa11y": version("xa11y"),
            },
            "tables": table_reports,
            "failures": failures,
        }
        (args.out / "report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        print(f"\nWrote captures to {args.out}")
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1 if failures else 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    finally:
        if process is not None and not args.keep_open:
            stop_process(process, pid)
        if stdout_handle is not None:
            stdout_handle.close()
        if stderr_handle is not None:
            stderr_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
