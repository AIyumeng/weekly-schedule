from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
# 2026-03-02 是第 1 周的周一。
SEMESTER_START_DATE = date(2026, 3, 2)


def load_classes(path: Path) -> tuple[str, list[dict[str, Any]], int, int]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    semester = data.get("semester", "未知学期")
    courses = data.get("courses", [])
    if not isinstance(courses, list):
        raise ValueError("classes.json 中的 courses 必须是数组")

    max_week = 1
    max_section = 1
    for course in courses:
        weeks = course.get("weeks", {})
        start = int(weeks.get("start", 1))
        end = int(weeks.get("end", start))
        max_week = max(max_week, start, end)

        sections = course.get("sections", [])
        if sections:
            max_section = max(max_section, max(int(s) for s in sections))

    return semester, courses, max_week, max_section


def course_in_week(course: dict[str, Any], week: int) -> bool:
    weeks = course.get("weeks", {})
    start = int(weeks.get("start", 1))
    end = int(weeks.get("end", start))
    return start <= week <= end


def color_for_name(name: str) -> QColor:
    digest = hashlib.md5(name.encode("utf-8")).digest()
    hue = digest[0] % 180
    sat = 70 + digest[1] % 40
    val = 230
    return QColor.fromHsv(hue, sat, val)


def format_course_block(course: dict[str, Any]) -> str:
    name = str(course.get("name", "未命名课程"))
    location = str(course.get("location", "未知地点"))
    cls = str(course.get("class", ""))
    teachers = "/".join(str(t) for t in course.get("teachers", [])) or "未知教师"

    parts = [name, location]
    if cls:
        parts.append(cls)
    parts.append(teachers)

    course_type = course.get("type")
    if course_type:
        parts.append(str(course_type))

    return "\n".join(parts)


def infer_week(target_date: date) -> int:
    delta_days = (target_date - SEMESTER_START_DATE).days
    if delta_days < 0:
        return 1
    return delta_days // 7 + 1


class TimetableWindow(QMainWindow):
    def __init__(self, json_path: Path):
        super().__init__()

        self.semester, self.courses, self.max_week, self.max_section = load_classes(json_path)

        self.setWindowTitle("我的课程表")
        self.resize(1200, 720)

        root = QWidget()
        root_layout = QVBoxLayout(root)

        toolbar = QHBoxLayout()
        self.semester_label = QLabel(f"学期：{self.semester}")
        self.week_label = QLabel("")
        self.today_label = QLabel("")
        self.count_label = QLabel("")

        self.prev_week_button = QPushButton("←")
        self.prev_week_button.clicked.connect(lambda: self.change_week(-1))
        self.next_week_button = QPushButton("→")
        self.next_week_button.clicked.connect(lambda: self.change_week(1))

        current_week = infer_week(date.today())
        self.current_week = min(max(current_week, 1), self.max_week)

        toolbar.addWidget(self.semester_label)
        toolbar.addSpacing(16)
        toolbar.addWidget(self.prev_week_button)
        toolbar.addSpacing(16)
        toolbar.addWidget(self.week_label)
        toolbar.addSpacing(16)
        toolbar.addWidget(self.next_week_button)
        toolbar.addSpacing(24)
        toolbar.addWidget(self.today_label)
        toolbar.addStretch()
        toolbar.addWidget(self.count_label)

        self.table = QTableWidget(self.max_section, 7)
        self.table.setHorizontalHeaderLabels(WEEKDAY_NAMES)
        self.table.setVerticalHeaderLabels([f"第 {i} 节" for i in range(1, self.max_section + 1)])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setWordWrap(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        root_layout.addLayout(toolbar)
        root_layout.addWidget(self.table)
        self.setCentralWidget(root)

        self.render_timetable()

    def change_week(self, delta: int) -> None:
        new_week = self.current_week + delta
        self.current_week = min(max(new_week, 1), self.max_week)
        self.render_timetable()

    def render_timetable(self) -> None:
        today = date.today()
        today_week = infer_week(today)
        today_weekday = today.isoweekday()
        week = self.current_week

        self.week_label.setText(f"第 {week} 周 / 共 {self.max_week} 周")
        self.today_label.setText(f"今天：{today:%Y-%m-%d}（{WEEKDAY_NAMES[today_weekday - 1]}）")

        active_courses = [c for c in self.courses if course_in_week(c, week)]

        cell_courses: dict[tuple[int, int], list[dict[str, Any]]] = {}

        for course in active_courses:
            weekday = int(course.get("weekday", 0))
            if not 1 <= weekday <= 7:
                continue

            sections = [int(s) for s in course.get("sections", [])]
            for section in sections:
                if not 1 <= section <= self.max_section:
                    continue
                cell_courses.setdefault((section - 1, weekday - 1), []).append(course)

        for row in range(self.max_section):
            for col in range(7):
                item = QTableWidgetItem("")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(QColor("#111111"))

                courses_here = cell_courses.get((row, col), [])
                is_today_cell = week == today_week and col == today_weekday - 1
                if len(courses_here) == 1:
                    course = courses_here[0]
                    item.setText(format_course_block(course))
                    item.setBackground(color_for_name(str(course.get("name", ""))))
                elif len(courses_here) > 1:
                    item.setText("\n------\n".join(format_course_block(c) for c in courses_here))
                    item.setBackground(QColor("#ffd9d9"))
                else:
                    item.setBackground(QColor("#ffffff" if not is_today_cell else "#fff4cc"))

                if is_today_cell:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

                self.table.setItem(row, col, item)

        for col in range(7):
            header = self.table.horizontalHeaderItem(col)
            if header is None:
                continue
            header.setBackground(QColor("#f0f0f0"))
            header.setForeground(QColor("#111111"))
            header_font = header.font()
            header_font.setBold(False)
            header.setFont(header_font)

        if week == today_week:
            today_header = self.table.horizontalHeaderItem(today_weekday - 1)
            if today_header is not None:
                today_header.setBackground(QColor("#ffd666"))
                header_font = today_header.font()
                header_font.setBold(True)
                today_header.setFont(header_font)

        self.prev_week_button.setEnabled(week > 1)
        self.next_week_button.setEnabled(week < self.max_week)
        self.count_label.setText(f"本周课程记录：{len(active_courses)}")


def main() -> int:
    json_path = Path("classes.json")
    if not json_path.exists():
        print("未找到 classes.json，请在项目目录下运行。", file=sys.stderr)
        return 1

    app = QApplication(sys.argv)
    try:
        window = TimetableWindow(json_path)
    except Exception as exc:  # pragma: no cover
        QMessageBox.critical(None, "加载失败", f"读取 classes.json 失败：\n{exc}")
        return 1

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
