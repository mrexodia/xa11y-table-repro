# Reference captures

These captures are intentionally versioned so an xa11y maintainer can inspect
the platform inconsistency without reproducing every environment first.

They were generated with:

- PySide6 6.11.1
- xa11y 0.11.0
- Python 3.12.11 on Windows
- Python 3.10.12 and Qt/AT-SPI under Ubuntu 22.04 WSL2 on Linux

Command:

```shell
uv run xa11y-table-dump --expect-table-cells
```

## Summary

| Native Qt control | Windows UIA | Linux AT-SPI2 |
| --- | --- | --- |
| QTableWidget cells | 15 × `table_row` | 15 × `table_cell` |
| QTableView cells | 15 × `table_row` | 15 × `table_cell` |
| Headerless QTableView cells | 15 × `table_row` | 15 × `table_cell` |

Windows reports every known cell as UIA control type `50029` (`DataItem`), and
xa11y maps that control type to `table_row`. Linux reports the equivalent
objects with AT-SPI role `cell`, which xa11y maps to `table_cell`.

The headerless view exposes another platform difference:

- Windows omits the hidden `Name`, `Value`, and `Notes` column headers.
- Linux still exposes those header names through AT-SPI.

The macOS reference capture is pending.

Each platform directory contains:

- `application.txt` and `application.json` for the application tree.
- A concise text tree for each Qt table.
- `report.json` with the full normalized snapshots and native raw fields.

PID files and process logs are generated locally but ignored because they are
not stable reproduction evidence.
