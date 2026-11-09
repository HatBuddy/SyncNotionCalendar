import contextlib
import os
import tempfile
import time
import unittest
from datetime import datetime

import pandas as pd

from src.Database import Database


@contextlib.contextmanager
def local_timezone(name):
    """Pins the process time zone so conversions are machine independent."""
    previous = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()


def stored_frame(rows):
    return pd.DataFrame(rows).set_index("id")


def live_frame(rows):
    return pd.DataFrame(rows).set_index("id")


def stored_row(
    page_id,
    title="Task",
    event_id="calendar-event",
    last_edit=datetime(2025, 1, 1, 9, 0, 0),
    start=datetime(2025, 1, 2, 9, 0, 0),
    end=datetime(2025, 1, 2, 10, 0, 0),
    description=None,
    flight_code=None,
):
    row = {
        "id": page_id,
        "last_edit": last_edit,
        "start_date": start,
        "end_date": end,
        "title": title,
        "event_id": event_id,
    }
    if description is not None:
        row["description"] = description
    if flight_code is not None:
        row["flight_code"] = flight_code
    return row


def live_row(
    page_id,
    title="Task",
    all_day=False,
    last_edit=datetime(2025, 1, 1, 9, 0, 0),
    start=datetime(2025, 1, 2, 9, 0, 0),
    end=datetime(2025, 1, 2, 10, 0, 0),
    url="https://example.com",
    description="Notes",
    flight_code="",
):
    return {
        "id": page_id,
        "last_edit": last_edit,
        "start_date": start,
        "end_date": end,
        "title": title,
        "url": url,
        "description": description,
        "flight_code": flight_code,
        "all_day": all_day,
    }


class FakeCalendarClient:
    def __init__(self, event_ids=None, delete_succeeds=True):
        self.event_ids = list(event_ids or [])
        self.added = []
        self.deleted = []
        self.delete_succeeds = delete_succeeds

    def add_event(self, *args):
        self.added.append(args)
        return self.event_ids.pop(0) if self.event_ids else "new-calendar-event"

    def delete_event(self, event_id):
        self.deleted.append(event_id)
        return self.delete_succeeds


class DatabaseTests(unittest.TestCase):
    def make_database(self, folder):
        database = Database("database-id", "token", "Work", folder=folder)
        database.calendar_client = FakeCalendarClient()
        return database

    def test_get_new_deleted_and_modified_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            database.df = stored_frame(
                [
                    stored_row("unchanged"),
                    stored_row("modified", title="Old"),
                    stored_row("deleted"),
                ]
            )
            current = live_frame(
                [
                    live_row("unchanged"),
                    live_row(
                        "modified",
                        title="New",
                        last_edit=datetime(2025, 1, 1, 10, 0, 0),
                    ),
                    live_row("new"),
                ]
            )

            self.assertEqual(set(database.get_new(current=current)), {"new"})
            self.assertEqual(set(database.get_deleted(current=current)), {"deleted"})
            self.assertEqual(set(database.get_modified(current=current)), {"modified"})

    def test_add_events_creates_calendar_event_and_persists_state(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            database.calendar_client = FakeCalendarClient(["calendar-event-1"])
            current = live_frame([live_row("page-1", title="Planning")])

            database.add_events(["page-1"], current=current)

            self.assertEqual(len(database.calendar_client.added), 1)
            self.assertEqual(database.calendar_client.added[0][0], "Planning")
            self.assertIn("page-1", database.df.index)
            self.assertEqual(database.df.loc["page-1", "event_id"], "calendar-event-1")

            persisted = pd.read_csv(
                os.path.join(folder, "database-id.csv"),
                index_col="id",
            )
            self.assertEqual(persisted.loc["page-1", "event_id"], "calendar-event-1")

    def test_remove_events_deletes_calendar_event_and_drops_state(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            database.df = stored_frame(
                [stored_row("page-1", event_id="calendar-event-1")]
            )

            database.remove_events(["page-1"])

            self.assertEqual(database.calendar_client.deleted, ["calendar-event-1"])
            self.assertNotIn("page-1", database.df.index)

    def test_modify_events_replaces_calendar_event_and_updates_state(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            database.calendar_client = FakeCalendarClient(["calendar-event-2"])
            database.df = stored_frame(
                [stored_row("page-1", title="Old", event_id="calendar-event-1")]
            )
            current = live_frame(
                [
                    live_row(
                        "page-1",
                        title="New",
                        last_edit=datetime(2025, 1, 1, 10, 0, 0),
                    )
                ]
            )

            database.modify_events(["page-1"], current=current)

            self.assertEqual(database.calendar_client.deleted, ["calendar-event-1"])
            self.assertEqual(database.calendar_client.added[0][0], "New")
            self.assertEqual(database.df.loc["page-1", "title"], "New")
            self.assertEqual(database.df.loc["page-1", "event_id"], "calendar-event-2")

    def test_get_card_for_calendar_formats_datetime_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            card = pd.Series(
                {
                    "title": "Planning",
                    "start_date": datetime(2025, 1, 2, 9, 30, 0),
                    "end_date": datetime(2025, 1, 2, 10, 45, 0),
                    "url": "https://example.com",
                    "description": "Notes",
                }
            )

            with local_timezone("UTC"):
                args = database._get_card_for_calendar(card)

            self.assertEqual(
                args,
                (
                    "Planning",
                    "2025-01-02",
                    "2025-01-02",
                    "09:30:00",
                    "10:45:00",
                    "https://example.com",
                    "Notes",
                    False,
                ),
            )

    def test_modify_events_does_not_re_add_when_the_delete_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            database.calendar_client = FakeCalendarClient(delete_succeeds=False)
            database.df = stored_frame(
                [stored_row("page-1", title="Old", event_id="calendar-event-1")]
            )
            current = live_frame(
                [live_row("page-1", title="New", last_edit=datetime(2025, 1, 1, 10, 0, 0))]
            )

            database.modify_events(["page-1"], current=current)

            # a second copy of the event would otherwise be created
            self.assertEqual(database.calendar_client.added, [])
            self.assertEqual(database.df.loc["page-1", "title"], "Old")
            self.assertEqual(database.df.loc["page-1", "event_id"], "calendar-event-1")

    def test_remove_events_keeps_the_row_when_the_delete_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            database.calendar_client = FakeCalendarClient(delete_succeeds=False)
            database.df = stored_frame(
                [stored_row("page-1", event_id="calendar-event-1")]
            )

            database.remove_events(["page-1"])

            # the event is still on the calendar, so the row must survive to retry
            self.assertIn("page-1", database.df.index)

    def test_get_card_for_calendar_renders_utc_in_the_machine_zone(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            # 06:20 UTC is the 13:20+07:00 departure Notion holds
            card = pd.Series(
                {
                    "title": "Flight BKK -> TFU",
                    "start_date": datetime(2026, 11, 15, 6, 20, 0),
                    "end_date": datetime(2026, 11, 15, 8, 50, 0),
                    "url": "",
                    "description": "",
                    "all_day": False,
                }
            )

            with local_timezone("Asia/Bangkok"):
                in_bangkok = database._get_card_for_calendar(card)
            with local_timezone("America/Los_Angeles"):
                in_seattle = database._get_card_for_calendar(card)

            # Same instant, rendered in whichever zone the Mac is set to
            self.assertEqual(in_bangkok[1:5], ("2026-11-15", "2026-11-15", "13:20:00", "15:50:00"))
            # the flight crosses midnight once rendered in Pacific
            self.assertEqual(in_seattle[1:5], ("2026-11-14", "2026-11-15", "22:20:00", "00:50:00"))

    def test_get_card_for_calendar_never_shifts_all_day_events(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            card = pd.Series(
                {
                    "title": "Scuba Diving Mallorca",
                    "start_date": datetime(2026, 9, 16, 0, 0, 0),
                    "end_date": datetime(2026, 9, 16, 0, 0, 0),
                    "url": "",
                    "description": "",
                    "all_day": True,
                }
            )

            for zone in ("Asia/Bangkok", "America/Los_Angeles", "UTC"):
                with local_timezone(zone):
                    args = database._get_card_for_calendar(card)
                self.assertEqual(args[1:5], ("2026-09-16", "2026-09-16", "00:00:00", "00:00:00"), zone)

    def test_get_card_for_calendar_passes_notion_all_day_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            midnight_timed = pd.Series(
                {
                    "title": "Red eye",
                    "start_date": datetime(2025, 1, 2, 0, 0, 0),
                    "end_date": datetime(2025, 1, 2, 0, 0, 0),
                    "url": "",
                    "description": "",
                    "all_day": False,
                }
            )
            all_day = midnight_timed.copy()
            all_day["all_day"] = True

            # A midnight-to-midnight timed event must not become an all-day event
            self.assertFalse(database._get_card_for_calendar(midnight_timed)[7])
            self.assertTrue(database._get_card_for_calendar(all_day)[7])

    def test_get_card_for_calendar_falls_back_to_midnight_heuristic(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            legacy = pd.Series(
                {
                    "title": "Old row",
                    "start_date": datetime(2025, 1, 2, 0, 0, 0),
                    "end_date": datetime(2025, 1, 2, 0, 0, 0),
                    "url": "",
                    "description": "",
                }
            )

            self.assertTrue(database._get_card_for_calendar(legacy)[7])

    def test_get_card_for_calendar_prepends_flight_code_to_description(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            card = pd.Series(
                {
                    "title": "Flight TPE -> BKK",
                    "start_date": datetime(2025, 1, 2, 9, 30, 0),
                    "end_date": datetime(2025, 1, 2, 10, 45, 0),
                    "url": "",
                    "description": "Seat 32A",
                    "flight_code": "CI833",
                }
            )

            description = database._get_card_for_calendar(card)[6]

            self.assertEqual(description, "Flight: CI833\n\nSeat 32A")

    def test_get_card_for_calendar_uses_flight_code_when_description_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            card = pd.Series(
                {
                    "title": "Flight TPE -> BKK",
                    "start_date": datetime(2025, 1, 2, 9, 30, 0),
                    "end_date": datetime(2025, 1, 2, 10, 45, 0),
                    "url": "",
                    "description": "",
                    "flight_code": "CI833",
                }
            )

            self.assertEqual(
                database._get_card_for_calendar(card)[6], "Flight: CI833"
            )

    def test_get_card_for_calendar_handles_missing_flight_code(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            card = pd.Series(
                {
                    "title": "Planning",
                    "start_date": datetime(2025, 1, 2, 9, 30, 0),
                    "end_date": datetime(2025, 1, 2, 10, 45, 0),
                    "url": "",
                    "description": "Notes",
                }
            )

            self.assertEqual(database._get_card_for_calendar(card)[6], "Notes")

    def test_get_card_for_calendar_ignores_nan_placeholders(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            card = pd.Series(
                {
                    "title": "Planning",
                    "start_date": datetime(2025, 1, 2, 9, 30, 0),
                    "end_date": datetime(2025, 1, 2, 10, 45, 0),
                    "url": float("nan"),
                    "description": float("nan"),
                    "flight_code": float("nan"),
                }
            )

            args = database._get_card_for_calendar(card)

            self.assertEqual(args[5], "")
            self.assertEqual(args[6], "")

    def test_get_modified_detects_flight_code_and_description_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            database.df = stored_frame(
                [
                    stored_row("flight", description="", flight_code=""),
                    stored_row("note", description="Old", flight_code=""),
                    stored_row("untouched", description="Notes", flight_code=""),
                ]
            )
            database.df["url"] = "https://example.com"
            current = live_frame(
                [
                    live_row(
                        "flight",
                        description="",
                        flight_code="CI833",
                        last_edit=datetime(2025, 1, 1, 10, 0, 0),
                    ),
                    live_row(
                        "note",
                        description="New",
                        last_edit=datetime(2025, 1, 1, 10, 0, 0),
                    ),
                    live_row(
                        "untouched",
                        description="Notes",
                        last_edit=datetime(2025, 1, 1, 10, 0, 0),
                    ),
                ]
            )

            self.assertEqual(
                set(database.get_modified(current=current)), {"flight", "note"}
            )

    def test_notion_timestamps_are_stored_but_do_not_trigger_resync(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            current = live_frame([live_row("page-1")])
            current["start_notion"] = "2026-11-15T13:20:00.000+07:00"
            current["end_notion"] = "2026-11-15T15:50:00.000+07:00"

            database.add_events(["page-1"], current=current)

            persisted = pd.read_csv(
                os.path.join(folder, "database-id.csv"), index_col="id"
            )
            self.assertEqual(
                persisted.loc["page-1", "start_notion"],
                "2026-11-15T13:20:00.000+07:00",
            )

            # a readable-only column must not make the event look modified
            current.loc["page-1", "start_notion"] = "2026-11-15T14:20:00.000+08:00"
            current.loc["page-1", "last_edit"] = datetime(2025, 6, 1, 9, 0, 0)
            self.assertEqual(database.get_modified(current=current), [])

    def test_get_modified_detects_url_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            database.df = stored_frame(
                [stored_row("page-1", description="Notes", flight_code="")]
            )
            database.df["url"] = "https://old.example.com"
            current = live_frame(
                [
                    live_row(
                        "page-1",
                        url="https://new.example.com",
                        last_edit=datetime(2025, 1, 1, 10, 0, 0),
                    )
                ]
            )

            self.assertEqual(database.get_modified(current=current), ["page-1"])

    def test_get_modified_handles_legacy_state_without_new_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            database.df = stored_frame([stored_row("page-1")])
            current = live_frame(
                [live_row("page-1", flight_code="CI833")]
            )

            self.assertEqual(database.get_modified(current=current), [])

    def test_existing_state_file_gains_new_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            legacy = pd.DataFrame(
                [
                    {
                        "id": "page-1",
                        "last_edit": datetime(2025, 1, 1, 9, 0, 0),
                        "start_date": datetime(2025, 1, 2, 9, 0, 0),
                        "end_date": datetime(2025, 1, 2, 10, 0, 0),
                        "title": "Task",
                        "event_id": "calendar-event-1",
                    }
                ]
            ).set_index("id")
            legacy.to_csv(os.path.join(folder, "database-id.csv"))

            database = self.make_database(folder)

            self.assertIn("description", database.df.columns)
            self.assertIn("flight_code", database.df.columns)
            self.assertEqual(database.df.loc["page-1", "event_id"], "calendar-event-1")
            self.assertEqual(
                database._get_card_for_calendar(database.df.loc["page-1"])[6], ""
            )

    def test_add_events_persists_description_and_flight_code(self):
        with tempfile.TemporaryDirectory() as folder:
            database = self.make_database(folder)
            database.calendar_client = FakeCalendarClient(["calendar-event-1"])
            current = live_frame(
                [
                    live_row(
                        "page-1",
                        title="Flight TPE -> BKK",
                        description="",
                        flight_code="CI833",
                    )
                ]
            )

            database.add_events(["page-1"], current=current)

            self.assertEqual(
                database.calendar_client.added[0][6], "Flight: CI833"
            )
            self.assertEqual(database.df.loc["page-1", "flight_code"], "CI833")

            persisted = pd.read_csv(
                os.path.join(folder, "database-id.csv"), index_col="id"
            )
            self.assertEqual(persisted.loc["page-1", "flight_code"], "CI833")


if __name__ == "__main__":
    unittest.main()
