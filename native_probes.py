from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from typing import Any


def probe_native_tables(
    pid: int,
    table_names: Iterable[str],
    expected_cells: dict[str, tuple[str, ...]],
    expected_headers: tuple[str, ...],
) -> dict[str, Any]:
    """Capture table relationships that xa11y's normalized snapshot omits."""
    table_names = tuple(table_names)
    if sys.platform == "win32":
        return _probe_windows(pid, table_names, expected_cells, expected_headers)
    if sys.platform == "darwin":
        return _probe_macos(pid, table_names, expected_cells, expected_headers)
    return {
        "platform": sys.platform,
        "supported": False,
        "reason": "The normalized AT-SPI capture already identifies table cells and headers.",
    }


def _runtime_id(element: Any) -> list[int] | None:
    try:
        runtime_id = element.element_info.runtime_id
        return [int(part) for part in runtime_id] if runtime_id else None
    except Exception:
        return None


def _wrap_uia_element(element: Any) -> Any:
    from pywinauto.controls.uiawrapper import UIAWrapper
    from pywinauto.uia_element_info import UIAElementInfo

    return UIAWrapper(UIAElementInfo(element))


def _uia_array(array: Any) -> list[Any]:
    return [
        _wrap_uia_element(array.GetElement(index)) for index in range(int(array.Length))
    ]


def _uia_element_summary(element: Any) -> dict[str, Any]:
    return {
        "name": element.element_info.name,
        "control_type": element.element_info.control_type,
    }


def _probe_windows_cell(element: Any) -> dict[str, Any]:
    result = _uia_element_summary(element)
    result.update(
        {
            "_runtime_id": _runtime_id(element),
            "grid_item_supported": False,
            "table_item_supported": False,
            "column_headers": [],
        }
    )

    try:
        grid_item = element.iface_grid_item
        containing_grid = _wrap_uia_element(grid_item.CurrentContainingGrid)
        result.update(
            {
                "grid_item_supported": True,
                "row": int(grid_item.CurrentRow),
                "column": int(grid_item.CurrentColumn),
                "row_span": int(grid_item.CurrentRowSpan),
                "column_span": int(grid_item.CurrentColumnSpan),
                "containing_grid": _uia_element_summary(containing_grid),
            }
        )
    except Exception as exc:
        result["grid_item_error"] = str(exc)

    try:
        table_item = element.iface_table_item
        headers = _uia_array(table_item.GetCurrentColumnHeaderItems())
        result.update(
            {
                "table_item_supported": True,
                "column_headers": [_uia_element_summary(header) for header in headers],
            }
        )
    except Exception as exc:
        result["table_item_error"] = str(exc)

    try:
        parent = element.parent()
        result["parent"] = _uia_element_summary(parent) if parent else None
    except Exception as exc:
        result["parent_error"] = str(exc)
    return result


def _probe_windows(
    pid: int,
    table_names: Iterable[str],
    expected_cells: dict[str, tuple[str, ...]],
    expected_headers: tuple[str, ...],
) -> dict[str, Any]:
    from pywinauto import Desktop

    windows = Desktop(backend="uia").windows(process=pid)
    if not windows:
        raise RuntimeError(f"UIA could not find a window for PID {pid}")
    root = windows[0]
    descendants = root.descendants()
    tables_by_name = {
        element.element_info.name: element
        for element in descendants
        if element.element_info.control_type in {"Table", "DataGrid"}
    }
    elements_by_name: dict[str, list[Any]] = {}
    for element in descendants:
        name = element.element_info.name
        if name:
            elements_by_name.setdefault(name, []).append(element)

    table_results = []
    for table_name in table_names:
        result: dict[str, Any] = {
            "name": table_name,
            "found": table_name in tables_by_name,
            "cells": [],
        }
        table = tables_by_name.get(table_name)
        if table is None:
            result["error"] = "Table was not found through UIA"
            table_results.append(result)
            continue

        result.update(_uia_element_summary(table))
        try:
            grid = table.iface_grid
            result["grid_pattern"] = {
                "row_count": int(grid.CurrentRowCount),
                "column_count": int(grid.CurrentColumnCount),
            }
        except Exception as exc:
            result["grid_pattern_error"] = str(exc)
        try:
            table_pattern = table.iface_table
            result["table_pattern"] = {
                "column_headers": [
                    _uia_element_summary(header)
                    for header in _uia_array(table_pattern.GetCurrentColumnHeaders())
                ],
                "row_headers": [
                    _uia_element_summary(header)
                    for header in _uia_array(table_pattern.GetCurrentRowHeaders())
                ],
            }
        except Exception as exc:
            result["table_pattern_error"] = str(exc)

        for cell_name in expected_cells[table_name]:
            matches = elements_by_name.get(cell_name, [])
            if not matches:
                result["cells"].append(
                    {"name": cell_name, "found": False, "error": "Cell not found"}
                )
                continue
            cell = _probe_windows_cell(matches[0])
            cell["found"] = True
            coordinate = re.match(r"^[WVN](\d+)C(\d+):", cell_name)
            if coordinate:
                expected_row = int(coordinate.group(1))
                expected_column = int(coordinate.group(2))
                cell.update(
                    {
                        "expected_row": expected_row,
                        "expected_column": expected_column,
                        "coordinate_matches": (
                            cell.get("row") == expected_row
                            and cell.get("column") == expected_column
                        ),
                        "expected_column_header": expected_headers[expected_column],
                        "column_header_matches": (
                            len(cell.get("column_headers", [])) == 1
                            and cell["column_headers"][0].get("name")
                            == expected_headers[expected_column]
                        ),
                    }
                )
            result["cells"].append(cell)

        cells = [cell for cell in result["cells"] if cell.get("found")]
        expected_count = len(expected_cells[table_name])
        expected_column_count = len(expected_headers)
        expected_row_count = expected_count // expected_column_count
        grid_pattern = result.get("grid_pattern", {})
        table_pattern = result.get("table_pattern", {})
        result["determination"] = {
            "expected_cells": expected_count,
            "table_grid_size_matches": (
                grid_pattern.get("row_count") == expected_row_count
                and grid_pattern.get("column_count") == expected_column_count
            ),
            "table_column_headers_match": (
                [
                    header.get("name")
                    for header in table_pattern.get("column_headers", [])
                ]
                == list(expected_headers)
            ),
            "table_row_header_count_matches": (
                len(table_pattern.get("row_headers", [])) == expected_row_count
            ),
            "found_cells": len(cells),
            "data_item_cells": sum(
                cell.get("control_type") == "DataItem" for cell in cells
            ),
            "grid_item_cells": sum(
                bool(cell.get("grid_item_supported")) for cell in cells
            ),
            "table_item_cells": sum(
                bool(cell.get("table_item_supported")) for cell in cells
            ),
            "cells_with_one_column_header": sum(
                len(cell.get("column_headers", [])) == 1 for cell in cells
            ),
            "cells_with_matching_coordinates": sum(
                bool(cell.get("coordinate_matches")) for cell in cells
            ),
            "cells_with_matching_column_header": sum(
                bool(cell.get("column_header_matches")) for cell in cells
            ),
            "cells_with_matching_containing_grid": sum(
                (cell.get("containing_grid") or {}).get("name") == table_name
                and (cell.get("containing_grid") or {}).get("control_type")
                in {"Table", "DataGrid"}
                for cell in cells
            ),
            "cells_with_matching_parent": sum(
                (cell.get("parent") or {}).get("name") == table_name
                and (cell.get("parent") or {}).get("control_type")
                in {"Table", "DataGrid"}
                for cell in cells
            ),
            "cells_with_unit_spans": sum(
                cell.get("row_span") == 1 and cell.get("column_span") == 1
                for cell in cells
            ),
            "distinct_runtime_ids": len(
                {
                    tuple(cell["_runtime_id"])
                    for cell in cells
                    if cell.get("_runtime_id")
                }
            ),
        }
        required_counts = (
            "found_cells",
            "data_item_cells",
            "grid_item_cells",
            "table_item_cells",
            "cells_with_one_column_header",
            "cells_with_matching_coordinates",
            "cells_with_matching_column_header",
            "cells_with_matching_containing_grid",
            "cells_with_matching_parent",
            "cells_with_unit_spans",
            "distinct_runtime_ids",
        )
        required_flags = (
            "table_grid_size_matches",
            "table_column_headers_match",
            "table_row_header_count_matches",
        )
        result["determination"]["evidence_complete"] = all(
            result["determination"][key] == expected_count for key in required_counts
        ) and all(result["determination"][key] for key in required_flags)
        for cell in cells:
            cell.pop("_runtime_id", None)
        table_results.append(result)

    probe_failures = [
        f"{table['name']}: incomplete UIA cell relationship evidence"
        for table in table_results
        if not table.get("determination", {}).get("evidence_complete", False)
    ]
    return {
        "platform": "windows",
        "api": "Microsoft UI Automation",
        "probe": "pywinauto",
        "supported": True,
        "tables": table_results,
        "failures": probe_failures,
    }


AX_ERROR_NAMES = {
    0: "kAXErrorSuccess",
    -25200: "kAXErrorFailure",
    -25201: "kAXErrorIllegalArgument",
    -25202: "kAXErrorInvalidUIElement",
    -25203: "kAXErrorInvalidUIElementObserver",
    -25204: "kAXErrorCannotComplete",
    -25205: "kAXErrorAttributeUnsupported",
    -25206: "kAXErrorActionUnsupported",
    -25207: "kAXErrorNotificationUnsupported",
    -25208: "kAXErrorNotImplemented",
    -25209: "kAXErrorNotificationAlreadyRegistered",
    -25210: "kAXErrorNotificationNotRegistered",
    -25211: "kAXErrorAPIDisabled",
    -25212: "kAXErrorNoValue",
    -25213: "kAXErrorParameterizedAttributeUnsupported",
    -25214: "kAXErrorNotEnoughPrecision",
}


def _ax_error_name(error: int) -> str:
    return AX_ERROR_NAMES.get(error, "unknown AXError")


def _ax_copy(element: Any, attribute: str) -> tuple[int, Any]:
    import ApplicationServices as app_services

    error, value = app_services.AXUIElementCopyAttributeValue(element, attribute, None)
    return int(error), value


def _ax_attribute_names(element: Any) -> dict[str, Any]:
    import ApplicationServices as app_services

    error, names = app_services.AXUIElementCopyAttributeNames(element, None)
    error = int(error)
    return {
        "error": error,
        "error_name": _ax_error_name(error),
        "names": sorted(str(name) for name in (names or [])),
    }


def _ax_simple_value(element: Any, attribute: str) -> dict[str, Any]:
    error, value = _ax_copy(element, attribute)
    result: dict[str, Any] = {
        "error": error,
        "error_name": _ax_error_name(error),
    }
    if error == 0 and value is not None:
        if isinstance(value, (str, int, float, bool)):
            result["value"] = value
        else:
            result["value_repr"] = repr(value)
    return result


def _ax_element_summary(element: Any) -> dict[str, Any]:
    result = {"attributes": _ax_attribute_names(element)}
    for attribute in (
        "AXRole",
        "AXSubrole",
        "AXTitle",
        "AXDescription",
        "AXValue",
        "AXIdentifier",
        "AXIndex",
        "AXHidden",
    ):
        result[attribute] = _ax_simple_value(element, attribute)
    return result


def _ax_children(element: Any, attribute: str = "AXChildren") -> list[Any]:
    error, value = _ax_copy(element, attribute)
    if error != 0 or value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _ax_find_tables(root: Any, wanted: set[str]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    queue = [root]
    visited = 0
    while queue and wanted - found.keys() and visited < 10000:
        current = queue.pop(0)
        visited += 1
        role = _ax_simple_value(current, "AXRole").get("value")
        title = _ax_simple_value(current, "AXTitle").get("value")
        if role == "AXTable" and title in wanted:
            found[str(title)] = current
        queue.extend(_ax_children(current))
    return found


def _probe_ax_header(column: Any) -> dict[str, Any]:
    error, header = _ax_copy(column, "AXHeader")
    result: dict[str, Any] = {
        "error": error,
        "error_name": _ax_error_name(error),
        "attribute_list_contains_header": (
            "AXHeader" in _ax_attribute_names(column)["names"]
        ),
        "value_present": error == 0 and header is not None,
    }
    if error == 0 and header is not None:
        result["element"] = _ax_element_summary(header)
        result["children"] = [
            _ax_element_summary(child) for child in _ax_children(header)
        ]
    return result


def _ax_observed_names(probe: dict[str, Any]) -> list[str]:
    names: list[str] = []
    element = probe.get("element")
    if element:
        for attribute in ("AXTitle", "AXDescription", "AXValue"):
            value = element.get(attribute, {}).get("value")
            if isinstance(value, str) and value:
                names.append(value)
    for child in probe.get("children", []):
        for attribute in ("AXTitle", "AXDescription", "AXValue"):
            value = child.get(attribute, {}).get("value")
            if isinstance(value, str) and value:
                names.append(value)
    return names


def _probe_macos(
    pid: int,
    table_names: Iterable[str],
    expected_cells: dict[str, tuple[str, ...]],
    expected_headers: tuple[str, ...],
) -> dict[str, Any]:
    import ApplicationServices as app_services

    process_trusted = bool(app_services.AXIsProcessTrusted())
    app = app_services.AXUIElementCreateApplication(pid)
    wanted = set(table_names)
    tables = _ax_find_tables(app, wanted)
    table_results = []
    for table_name in table_names:
        result: dict[str, Any] = {
            "name": table_name,
            "found": table_name in tables,
            "expected_cell_count": len(expected_cells[table_name]),
        }
        table = tables.get(table_name)
        if table is None:
            result["error"] = "AXTable was not found"
            table_results.append(result)
            continue

        result["element"] = _ax_element_summary(table)
        result["table_header"] = _probe_ax_header(table)
        rows = _ax_children(table, "AXRows")
        columns = _ax_children(table, "AXColumns")
        result["row_count"] = len(rows)
        result["column_count"] = len(columns)
        result["columns"] = []
        for index, column in enumerate(columns):
            column_result = _ax_element_summary(column)
            column_result["index"] = index
            column_result["expected_header_name"] = expected_headers[index]
            column_result["header"] = _probe_ax_header(column)
            column_result["observed_header_names"] = _ax_observed_names(
                column_result["header"]
            )
            column_result["header_name_matches"] = (
                expected_headers[index] in (column_result["observed_header_names"])
            )
            result["columns"].append(column_result)

        cells = []
        result["rows"] = []
        for row_index, row in enumerate(rows):
            row_result = _ax_element_summary(row)
            row_result["index"] = row_index
            result["rows"].append(row_result)
            row_cells = _ax_children(row)
            for column_index, cell in enumerate(row_cells):
                cell_result = _ax_element_summary(cell)
                cell_result.update({"row": row_index, "column": column_index})
                cells.append(cell_result)
        result["cells"] = cells
        table_header_names = _ax_observed_names(result["table_header"])
        column_header_names = [
            name
            for column in result["columns"]
            for name in column["observed_header_names"]
        ]
        probed_elements = [
            result["element"],
            *result["rows"],
            *result["columns"],
            *cells,
        ]
        identifiers = [
            element["AXIdentifier"].get("value")
            for element in probed_elements
            if element["AXIdentifier"].get("value")
        ]
        expected_count = len(expected_cells[table_name])
        expected_column_count = len(expected_headers)
        expected_row_count = expected_count // expected_column_count
        result["determination"] = {
            "expected_rows": expected_row_count,
            "expected_columns": expected_column_count,
            "expected_cells": expected_count,
            "elements_with_identifier": len(identifiers),
            "distinct_identifiers": len(set(identifiers)),
            "identifier_values": sorted(set(identifiers)),
            "table_ax_header_attribute": result["table_header"][
                "attribute_list_contains_header"
            ],
            "table_ax_header_value": result["table_header"]["value_present"],
            "table_header_names": table_header_names,
            "column_header_names": column_header_names,
            "matching_expected_header_names": sum(
                name in table_header_names or name in column_header_names
                for name in expected_headers
            ),
            "columns_with_ax_header_attribute": sum(
                column["header"]["attribute_list_contains_header"]
                for column in result["columns"]
            ),
            "columns_with_ax_header_value": sum(
                column["header"]["value_present"] for column in result["columns"]
            ),
            "columns_with_matching_header_name": sum(
                column["header_name_matches"] for column in result["columns"]
            ),
            "cells_found_below_rows": len(cells),
        }
        result["determination"]["evidence_complete"] = (
            len(rows) == expected_row_count
            and len(columns) == expected_column_count
            and len(cells) == expected_count
        )
        table_results.append(result)

    probe_failures = [
        f"{table['name']}: incomplete AX table hierarchy evidence"
        for table in table_results
        if not table.get("determination", {}).get("evidence_complete", False)
    ]
    if not process_trusted:
        probe_failures.insert(
            0,
            "Python is not trusted by macOS Accessibility permissions",
        )
    return {
        "platform": "macos",
        "api": "macOS Accessibility API",
        "probe": "PyObjC ApplicationServices",
        "process_trusted": process_trusted,
        "supported": True,
        "tables": table_results,
        "failures": probe_failures,
    }
