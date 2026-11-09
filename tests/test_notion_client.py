import unittest
from datetime import datetime
from unittest.mock import patch

from src.notionClient import Card, NotionClient


def notion_page(
    page_id="page-1",
    title="Task",
    start="2025-01-15",
    end=None,
    url="https://example.com",
    description="A useful note",
    last_edited_time="2025-01-14T10:20:30.000Z",
    flight_code="",
    include_flight_code=True,
):
    properties = {
        "Name": {"title": [{"plain_text": title}]},
        "Date": {"date": {"start": start, "end": end}},
        "URL": {"url": url},
        "Description": {
            "rich_text": (
                [{"plain_text": description}] if description else []
            )
        },
    }
    if include_flight_code:
        properties["Flight Code"] = {
            "rich_text": (
                [{"plain_text": flight_code}] if flight_code else []
            )
        }
    return {
        "id": page_id,
        "last_edited_time": last_edited_time,
        "properties": properties,
    }


class FakeResponse:
    def __init__(self, payload, ok=True, text=""):
        self._payload = payload
        self.ok = ok
        self.text = text

    def json(self):
        return self._payload


class CardTests(unittest.TestCase):
    def test_card_parses_date_only_page(self):
        card = Card(notion_page(end=None, description=""))

        self.assertEqual(
            card.to_dict(),
            {
                "id": "page-1",
                "last_edit": datetime(2025, 1, 14, 10, 20, 30),
                "start_date": datetime(2025, 1, 15, 0, 0, 0),
                "end_date": datetime(2025, 1, 15, 0, 0, 0),
                "title": "Task",
                "url": "https://example.com",
                "description": "",
                "flight_code": "",
                "all_day": True,
            },
        )

    def test_card_parses_timed_page_with_end_date(self):
        card = Card(
            notion_page(
                start="2025-01-15T09:30:00.000-08:00",
                end="2025-01-15T10:45:00.000-08:00",
            )
        )

        # stored as naive UTC: 09:30-08:00 is 17:30 UTC
        self.assertEqual(card.start_date, datetime(2025, 1, 15, 17, 30, 0))
        self.assertEqual(card.end_date, datetime(2025, 1, 15, 18, 45, 0))
        self.assertEqual(card.description, "A useful note")

    def test_card_keeps_the_departure_zone_offset_as_the_instant(self):
        # Notion carries the zone the time was entered in; dropping it moved
        # the event by hours.
        card = Card(notion_page(start="2026-11-15T13:20:00.000+07:00"))

        self.assertEqual(card.start_date, datetime(2026, 11, 15, 6, 20, 0))

    def test_card_converts_each_offset_to_the_same_utc_instant(self):
        bangkok = Card(notion_page(start="2026-11-15T13:20:00.000+07:00")).start_date
        tokyo = Card(notion_page(start="2026-11-15T15:20:00.000+09:00")).start_date
        seattle = Card(notion_page(start="2026-11-14T22:20:00.000-08:00")).start_date

        self.assertEqual(bangkok, tokyo)
        self.assertEqual(bangkok, seattle)

    def test_card_stores_last_edit_in_utc(self):
        card = Card(notion_page(last_edited_time="2025-04-17T23:22:00.000Z"))

        self.assertEqual(card.last_edited_time, datetime(2025, 4, 17, 23, 22, 0))

    def test_card_leaves_bare_dates_unshifted(self):
        card = Card(notion_page(start="2026-11-15"))

        self.assertEqual(card.start_date, datetime(2026, 11, 15, 0, 0, 0))

    def test_card_marks_bare_date_as_all_day(self):
        self.assertTrue(Card(notion_page(start="2025-01-15")).all_day)

    def test_card_marks_timestamped_date_as_timed(self):
        card = Card(notion_page(start="2025-01-15T00:00:00.000-08:00"))

        self.assertFalse(card.all_day)

    def test_card_parses_flight_code(self):
        card = Card(notion_page(title="Flight TPE -> BKK", flight_code="CI833"))

        self.assertEqual(card.flight_code, "CI833")
        self.assertEqual(card.to_dict()["flight_code"], "CI833")

    def test_card_normalises_flight_code_whitespace(self):
        card = Card(notion_page(flight_code="\u00a0KL  1819 "))

        self.assertEqual(card.flight_code, "KL 1819")

    def test_card_without_flight_code_property_defaults_to_empty(self):
        card = Card(notion_page(include_flight_code=False))

        self.assertEqual(card.flight_code, "")

    def test_card_joins_all_rich_text_chunks(self):
        page = notion_page()
        page["properties"]["Description"]["rich_text"] = [
            {"plain_text": "first "},
            {"plain_text": "second"},
        ]
        page["properties"]["Flight Code"]["rich_text"] = [
            {"plain_text": "CI21, "},
            {"plain_text": "CI791"},
        ]

        card = Card(page)

        self.assertEqual(card.description, "first second")
        self.assertEqual(card.flight_code, "CI21, CI791")

    def test_card_handles_missing_url_property(self):
        page = notion_page()
        del page["properties"]["URL"]

        self.assertEqual(Card(page).url, "")


class NotionClientTests(unittest.TestCase):
    def test_get_live_cards_fetches_all_pages(self):
        responses = [
            FakeResponse(
                {
                    "results": [notion_page(page_id="page-1")],
                    "has_more": True,
                    "next_cursor": "cursor-2",
                }
            ),
            FakeResponse(
                {
                    "results": [notion_page(page_id="page-2", title="Next")],
                    "has_more": False,
                    "next_cursor": None,
                }
            ),
        ]
        calls = []

        def fake_post(url, headers, json):
            calls.append({"url": url, "headers": headers, "json": json.copy()})
            return responses.pop(0)

        with patch("src.notionClient.requests.post", side_effect=fake_post):
            cards = NotionClient("secret-token").get_live_cards("database-id")

        self.assertEqual([card._id for card in cards], ["page-1", "page-2"])
        self.assertEqual(calls[0]["json"], {})
        self.assertEqual(calls[1]["json"], {"start_cursor": "cursor-2"})
        self.assertEqual(
            calls[0]["url"],
            "https://api.notion.com/v1/databases/database-id/query",
        )
        self.assertEqual(calls[0]["headers"]["Authorization"], "Bearer secret-token")

    def test_get_live_cards_raises_on_api_error(self):
        response = FakeResponse({}, ok=False, text="Notion said no")

        with patch("src.notionClient.requests.post", return_value=response):
            with self.assertRaises(Exception) as raised:
                NotionClient("secret-token").get_live_cards("database-id")

        self.assertEqual(str(raised.exception), "Notion said no")


if __name__ == "__main__":
    unittest.main()
