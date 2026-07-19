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

Dependencies are pinned to:

- PySide6 6.11.1
- xa11y 0.11.0

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
- Qt application stdout/stderr logs.

To turn the expected cross-platform role into an assertion:

```shell
uv run xa11y-table-dump --expect-table-cells
```

That command should succeed when all 45 known data cells normalize as
`table_cell`. With xa11y 0.11.0 it is expected to fail on Windows because the
UIA backend currently maps every `DataItem` to `table_row`.

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
- Linux: the corresponding AT-SPI role maps to `table_cell`.
- macOS: the corresponding `AXCell` maps to `table_cell`.

A UIA `DataItem` is not necessarily a row. Qt's cell also implements GridItem
and TableItem patterns with concrete row/column and header relationships. A
cross-platform normalization should therefore use those patterns to distinguish
cell DataItems from actual row containers rather than relying on control type
alone.

## Observed results

Local PySide6 6.11.1 / xa11y 0.11.0 captures currently show:

| Platform | Known cells | Normalized cell role |
| --- | ---: | --- |
| Windows UIA | 45/45 | `table_row` |
| Linux AT-SPI2 | 45/45 | `table_cell` |

The no-header case also exposes a platform difference: Windows omits the three
hidden column-header names from xa11y's tree, while Linux AT-SPI2 still returns
`Name`, `Value`, and `Notes`. The reproducer records this separately from the
cell-role assertion so it can be evaluated on macOS as well.
