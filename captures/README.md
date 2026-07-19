# Reference captures

These captures are intentionally versioned so an xa11y maintainer can inspect
the platform inconsistency without reproducing every environment first.

They were generated with:

- PySide6 6.11.1
- xa11y 0.11.0
- Python 3.12.11 on Windows
- Python 3.10.12 and Qt/AT-SPI under Ubuntu 22.04 WSL2 on Linux
- Python 3.14.0 on macOS 15.6

Command:

```shell
uv run xa11y-table-dump --expect-table-cells
```

## Summary

| Native Qt control | Windows UIA | Linux AT-SPI2 | macOS AX |
| --- | --- | --- | --- |
| QTableWidget cells | 15 × `table_row` | 15 × `table_cell` | 15 × `table_cell` |
| QTableView cells | 15 × `table_row` | 15 × `table_cell` | 15 × `table_cell` |
| Headerless QTableView cells | 15 × `table_row` | 15 × `table_cell` | 15 × `table_cell` |

Windows reports every known cell as UIA control type `50029` (`DataItem`), and
xa11y maps that control type to `table_row`. The direct UIA capture proves that
45/45 DataItems support GridItem and TableItem, have the expected unique
runtime IDs and zero-based coordinates, use 1x1 spans, identify their containing
table, and return the matching column header. Linux reports the equivalent
objects with AT-SPI role `cell`, which xa11y maps to `table_cell`.

Table hierarchy and headers expose additional platform differences:

- Windows exposes flat UIA DataItem cells; xa11y's tree contains visible
  headers and omits hidden headers, while native TablePattern/TableItem still
  return all semantic header associations.
- Linux exposes flat AT-SPI cells and retains header names even when hidden.
- macOS synthesizes five direct `AXRow` and three direct `AXColumn` objects;
  cells are nested below rows. xa11y's current snapshots contain no header
  names for those columns, even when the visual headers are present. All 24
  nodes in each captured table subtree share the table's `AXIdentifier`, so
  xa11y's `stable_id` is stable here but not unique.

Each platform directory contains:

- `application.txt` and `application.json` for the application tree.
- A concise text tree for each Qt table.
- `report.json` with the full normalized snapshots and native raw fields.
- `native-probe.json` with direct UIA GridItem/TableItem evidence on Windows,
  direct `AXHeader` and attribute-list evidence on macOS, or the reason no
  supplementary probe is needed on Linux. The macOS native probe is pending a
  fresh run with Accessibility permission.

PID files and process logs are generated locally but ignored because they are
not stable reproduction evidence.
