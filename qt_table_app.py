from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QLabel,
    QMainWindow,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

HEADERS = ("Name", "Value", "Notes")
ROWS = (
    ("Alpha", "10", "first row"),
    ("Bravo", "20", "second row"),
    ("Charlie", "30", "third row"),
    ("Delta", "40", "fourth row"),
    ("Echo", "50", "fifth row"),
)


def configure_table(table: QTableView, accessible_name: str) -> None:
    table.setAccessibleName(accessible_name)
    table.setAccessibleDescription(
        "A populated native Qt table used to compare xa11y role classification."
    )
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QTableView.SelectionBehavior.SelectItems)
    table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
    table.setMinimumHeight(170)


def create_table_widget() -> QTableWidget:
    table = QTableWidget(len(ROWS), len(HEADERS))
    configure_table(table, "QTableWidget example")
    table.setHorizontalHeaderLabels(HEADERS)
    table.setVerticalHeaderLabels([f"Row {index}" for index in range(len(ROWS))])
    for row, values in enumerate(ROWS):
        for column, value in enumerate(values):
            table.setItem(row, column, QTableWidgetItem(f"W{row}C{column}: {value}"))
    table.resizeColumnsToContents()
    table.setCurrentCell(0, 0)
    return table


def create_table_view(
    accessible_name: str = "QTableView example",
    cell_prefix: str = "V",
    show_headers: bool = True,
) -> QTableView:
    table = QTableView()
    configure_table(table, accessible_name)

    model = QStandardItemModel(len(ROWS), len(HEADERS), table)
    model.setHorizontalHeaderLabels(HEADERS)
    model.setVerticalHeaderLabels([f"Row {index}" for index in range(len(ROWS))])
    for row, values in enumerate(ROWS):
        for column, value in enumerate(values):
            model.setItem(
                row,
                column,
                QStandardItem(f"{cell_prefix}{row}C{column}: {value}"),
            )
    table.setModel(model)
    table.horizontalHeader().setVisible(show_headers)
    table.verticalHeader().setVisible(show_headers)
    table.resizeColumnsToContents()
    table.setCurrentIndex(model.index(0, 0))
    return table


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("xa11y Qt Table Reproducer")
        self.setAccessibleName("xa11y Qt Table Reproducer")
        self.resize(900, 850)

        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.addWidget(
            QLabel(
                "All controls use Qt's built-in accessibility implementation. "
                "Each data item below is a table cell, not a row container."
            )
        )

        widget_group = QGroupBox("QTableWidget")
        widget_layout = QVBoxLayout(widget_group)
        self.table_widget = create_table_widget()
        widget_layout.addWidget(self.table_widget)
        layout.addWidget(widget_group)

        view_group = QGroupBox("QTableView + QStandardItemModel")
        view_layout = QVBoxLayout(view_group)
        self.table_view = create_table_view()
        view_layout.addWidget(self.table_view)
        layout.addWidget(view_group)

        no_headers_group = QGroupBox("QTableView with visual headers hidden")
        no_headers_layout = QVBoxLayout(no_headers_group)
        self.table_view_no_headers = create_table_view(
            accessible_name="QTableView no headers",
            cell_prefix="N",
            show_headers=False,
        )
        no_headers_layout.addWidget(self.table_view_no_headers)
        layout.addWidget(no_headers_group)

        self.setCentralWidget(root)


def main() -> int:
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_LINUX_ACCESSIBILITY_ALWAYS_ON", "1")

    application = QApplication(sys.argv)
    application.setApplicationName("xa11y-table-reproducer")
    window = MainWindow()
    window.show()
    pid = os.getpid()
    if pid_file := os.environ.get("XA11Y_TABLE_PID_FILE"):
        Path(pid_file).write_text(str(pid), encoding="ascii")
    print(f"READY pid={pid}", flush=True)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
