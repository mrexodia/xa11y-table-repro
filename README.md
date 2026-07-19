# xa11y native Qt table role reproducer

This standalone project demonstrates how xa11y classifies cells from Qt's
**built-in** accessibility implementation on Windows, macOS, and Linux. It does
not contain custom `QAccessibleInterface` code.

The GUI uses [PySide6](https://pypi.org/project/PySide6/), the official current
Qt for Python binding, and displays three populated native tables:

- `QTableWidget`
- `QTableView` backed by `QStandardItemModel`
- The same `QTableView` with horizontal and vertical headers hidden

Every cell has a unique name such as `W0C0: Alpha` or `V3C2: fourth row`, making
it unambiguous that the element is an individual cell rather than a row
container.

## Setup

Python 3.10 or newer and [uv](https://docs.astral.sh/uv/) are recommended.

```shell
cd xa11y-table
uv sync
```

The application and normalized probe are pinned to PySide6 6.11.1 and xa11y
0.11.0. Platform markers also install pywinauto on Windows and PyObjC's Quartz
bindings on macOS for the native relationship probes.

## Run the reproducer

Launch and inspect the application in one command:

```shell
uv run xa11y-table-dump
```

Captures are written to `captures/<platform>/`. The curated Windows and Linux
captures are intentionally versioned as reproduction evidence; rerunning the
script refreshes them.

Each platform directory contains:

- `application.txt` / `application.json`: complete normalized tree.
- One text tree for each table.
- `report.json`: normalized roles, names, states, bounds, and native `raw`
  properties for every element.
- `native-probe.json`: relationships queried directly through UIA or AX which
  xa11y's normalized model omits, or a note that no supplementary Linux probe
  is needed.
- Qt application stdout/stderr logs.

To turn the expected cross-platform role into an assertion:

```shell
uv run xa11y-table-dump --expect-table-cells
```

That command succeeds when all 45 known data cells normalize as `table_cell`.
With xa11y 0.11.0 it is expected to fail on Windows because the UIA backend
currently maps every `DataItem` to `table_row`. Missing column-header names are
recorded as platform observations but do not affect this cell-role assertion.

You can also launch or attach manually:

```shell
uv run xa11y-table-app
uv run xa11y-table-dump --attach-pid <PID> --keep-open
```

## Platform setup

### Windows

UI Automation normally requires no additional setup. Run both processes at the
same integrity level.

### macOS

Grant the Python interpreter printed by the following command Accessibility
permission under **System Settings → Privacy & Security → Accessibility**:

```shell
uv run python -c "import sys; print(sys.executable)"
```

On macOS 26, xa11y also requires **Screen & System Audio Recording** permission.

### Linux

Run in a desktop session with AT-SPI2 and force Qt accessibility on:

```shell
export QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1
uv run xa11y-table-dump
```

For CI/headless execution, `xa11y/setup-a11y@v1` starts Xvfb, D-Bus, and the
AT-SPI bridge before running the same command.

## Expected inconsistency

Qt's platform bridges expose the same native Qt cells differently:

- Windows: `QAccessible::Cell` becomes UIA `DataItem`. xa11y 0.11.0 maps the
  control type unconditionally to `table_row`.
- Linux: the corresponding AT-SPI role maps directly to `table_cell`.
- macOS: Qt synthesizes direct `AXRow` and `AXColumn` children for the table,
  with `AXCell`/`table_cell` objects nested under each row.

A UIA `DataItem` is not necessarily a row. The direct UIA probe verifies that
all 45 Qt cells implement both GridItem and TableItem, report the expected
zero-based row/column, have 1x1 spans, identify the table as their containing
grid and parent, and return the matching column header. A cross-platform
normalization should therefore use those patterns to distinguish cell DataItems
from actual row containers rather than relying on control type alone.

The macOS probe queries `AXUIElementCopyAttributeNames()` and `AXHeader` on the
`AXTable` and every `AXColumn`, then records the returned header object's role,
title, value, description, identifier, and children. This distinguishes a
missing Qt relationship from a relationship that xa11y simply does not query.
It requires a fresh capture on a permitted macOS host before that boundary can
be assigned conclusively.

## xa11y implementation guidance

### Windows DataItem normalization

xa11y 0.11.0's UIA backend currently maps `UIA_DataItemControlTypeId` directly
to `Role::TableRow` in `xa11y-windows/src/uia.rs`'s
`map_uia_control_type()`. The native capture demonstrates that Qt's DataItems
are cells, not row containers. A targeted implementation can add
`UIA_IsTableItemPatternAvailablePropertyId` to `BATCH_PROPERTIES`, then refine a
DataItem with that cached property set to `Role::TableCell` in
`build_snapshot_data()`. DataItems without TableItem remain `Role::TableRow`.
The regression tests should cover both values rather than replacing one
unconditional control-type mapping with another. GridItem's row, column,
spans, and containing grid provide additional fixture evidence, while
TableItem and its column-header association are the cell-specific signal.

### macOS header extraction

xa11y currently walks `AXChildren` but does not preserve an `AXHeader`
relationship in its normalized table model. Use `native-probe.json` from a
macOS run to decide the fix: follow and name the returned AX header when the
relationship exists, or report the result upstream to Qt when the direct API
returns `kAXErrorAttributeUnsupported` or no value. Keep visible-header
observations separate from the 45-cell role assertion.

### macOS identifiers are stable but not unique

The existing macOS snapshots show that all 24 elements in each Qt table subtree
(the table, five synthesized rows, three synthesized columns, and 15 cells)
share the table's `AXIdentifier`. Qt does this intentionally for synthesized
table elements, and xa11y copies `AXIdentifier` to `stable_id`. xa11y's contract
describes that value as stable for the same element, not globally unique, so
this is not by itself a separate role-normalization defect. Consumers must not
use `stable_id` alone as a subtree key. The native macOS probe records identifier
cardinality explicitly so a future contract change has concrete fixture data.

## Observed results

Local PySide6 6.11.1 / xa11y 0.11.0 captures currently show:

| Platform | Known cells | Normalized cell role |
| --- | ---: | --- |
| Windows UIA | 45/45 | `table_row` |
| Linux AT-SPI2 | 45/45 | `table_cell` |
| macOS AX | 45/45 | `table_cell` nested under `table_row` |

Header exposure also differs:

- Windows's normalized tree exposes the three visible headers and omits them
  when visually hidden. UIA TablePattern/TableItem still return the correct
  semantic column headers in both cases.
- Linux exposes `Name`, `Value`, and `Notes` even for the headerless view.
- macOS exposes three `AXColumn` objects for every table, but xa11y's current
  snapshots contain no header names for them, including when visual headers are
  present.

The reproducer records header behavior separately from the cell-role assertion.
