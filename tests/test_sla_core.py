import json
import unittest
from datetime import datetime

from app.config_validation import json_object
from app.rule_engine import evaluate
from app.sla_engine import _add_working_minutes


class CalendarCursor:
    def __init__(self, timezone="UTC", holiday=None):
        self.sql = ""
        self.timezone = timezone
        self.holiday = holiday

    def execute(self, sql, params=None):
        self.sql = sql

    def fetchall(self):
        if "sla_working_hours" in self.sql:
            return [(day, 0, 1440, self.timezone) for day in range(7)]
        if "sla_holidays" in self.sql and self.holiday:
            return [(self.holiday, None, "N")]
        return []


class RuleCursor:
    def cursor(self):
        return self

    def execute(self, *args):
        pass

    def fetchall(self):
        return [
            ("GLOBAL", "P2", "{}", json.dumps({"duration_minutes": 10}), None, None, None, 1),
            ("CORPORATE", "P2", "{}", json.dumps({"duration_minutes": 20}), "corporate", "CORP-1", None, 1),
        ]


class SlaCoreTests(unittest.TestCase):
    def test_json_configuration_requires_object(self):
        self.assertEqual(json_object("", "conditions"), "{}")
        self.assertEqual(json.loads(json_object('{"priority":"P1"}', "actions"))["priority"], "P1")
        with self.assertRaises(ValueError):
            json_object("[]", "actions")

    def test_timezone_calendar_adds_working_minutes(self):
        start = datetime(2026, 9, 15, 9, 0)
        due = _add_working_minutes(CalendarCursor("UTC"), start, 60, "Operations")
        self.assertAlmostEqual((due - start).total_seconds(), 3600, delta=1)

    def test_holiday_is_skipped(self):
        start = datetime(2026, 9, 15, 9, 0)
        due = _add_working_minutes(CalendarCursor("UTC", start.date()), start, 60, "Operations")
        self.assertEqual(due.date().isoformat(), "2026-09-16")

    def test_specific_rule_overrides_global_rule(self):
        result = evaluate(RuleCursor(), "BOOKING_CREATED", {"corporate_id": "CORP-1"}, "Operations")
        self.assertEqual(result["actions"]["duration_minutes"], 20)
        self.assertEqual(result["rules"][-1]["scope"], "corporate")


if __name__ == "__main__":
    unittest.main()
