import unittest
from unittest.mock import patch

from src.CalendarClient import CalendarClient


class AppleScriptResult:
    def __init__(self, out="", err=""):
        self.out = out
        self.err = err


class CalendarClientTests(unittest.TestCase):
    def test_applescript_escape_handles_quotes_backslashes_and_newlines(self):
        client = CalendarClient("Work")

        escaped = client.applescript_escape('Hello "World"\nC:\\Temp')

        self.assertEqual(escaped, 'Hello \\"World\\" C:\\\\Temp')

    def test_applescript_escape_truncates_long_values(self):
        client = CalendarClient("Work")

        escaped = client.applescript_escape("x" * 5, max_length=3)

        self.assertEqual(escaped, "xxx...")

    def test_applescript_multiline_keeps_line_breaks(self):
        client = CalendarClient("Work")

        self.assertEqual(
            client.applescript_multiline("Flight: CI833\n\nSeat 32A"),
            '"Flight: CI833" & return & "" & return & "Seat 32A"',
        )

    def test_applescript_multiline_treats_literal_backslash_n_as_break(self):
        client = CalendarClient("Work")

        self.assertEqual(
            client.applescript_multiline("one\\ntwo"),
            '"one" & return & "two"',
        )

    def test_applescript_multiline_escapes_quotes_and_backslashes(self):
        client = CalendarClient("Work")

        self.assertEqual(
            client.applescript_multiline('say "hi" C:\\Temp'),
            '"say \\"hi\\" C:\\\\Temp"',
        )

    def test_add_event_writes_multiline_description(self):
        client = CalendarClient("Work")

        with patch(
            "src.CalendarClient.applescript.run",
            return_value=AppleScriptResult(out="calendar-event-1"),
        ) as run:
            client.add_event(
                "Flight TPE -> BKK",
                "2025-01-15",
                "2025-01-15",
                "09:00:00",
                "10:00:00",
                "",
                "Flight: CI833\n\nSeat 32A",
            )

        command = run.call_args.args[0]
        self.assertIn(
            'set description of newEvent to "Flight: CI833" & return & "" '
            '& return & "Seat 32A"',
            command,
        )
        self.assertNotIn('set url of newEvent', command)

    def test_add_event_creates_all_day_event_and_returns_id(self):
        client = CalendarClient("Work")

        with patch(
            "src.CalendarClient.applescript.run",
            return_value=AppleScriptResult(out="calendar-event-1"),
        ) as run:
            event_id = client.add_event(
                "Planning",
                "2025-01-15",
                "2025-01-15",
                "00:00:00",
                "00:00:00",
                "https://example.com",
                'Note with "quotes"',
            )

        self.assertEqual(event_id, "calendar-event-1")
        command = run.call_args.args[0]
        self.assertIn('tell calendar "Work"', command)
        self.assertIn("allday event:true", command)
        self.assertIn('set url of newEvent to "https://example.com"', command)
        self.assertIn('"Note with \\"quotes\\""', command)

    def test_add_event_raises_when_applescript_reports_error(self):
        client = CalendarClient("Work")

        with patch(
            "src.CalendarClient.applescript.run",
            return_value=AppleScriptResult(err="Calendar failed"),
        ):
            with self.assertRaises(Exception) as raised:
                client.add_event(
                    "Planning",
                    "2025-01-15",
                    "2025-01-15",
                    "09:00:00",
                    "10:00:00",
                    "",
                    "",
                )

        self.assertEqual(str(raised.exception), "Failed to add event to Work calendar")

    def test_delete_event_runs_applescript(self):
        client = CalendarClient("Work")

        with patch(
            "src.CalendarClient.applescript.run",
            return_value=AppleScriptResult(),
        ) as run:
            client.delete_event("calendar-event-1")

        command = run.call_args.args[0]
        self.assertIn('tell calendar "Work"', command)
        self.assertIn('delete event id "calendar-event-1"', command)


if __name__ == "__main__":
    unittest.main()
