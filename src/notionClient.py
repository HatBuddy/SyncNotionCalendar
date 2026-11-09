import requests
from typing import Dict, List
from datetime import datetime, timezone
import logging


class Card:
    """This class represents a Notion card as a dict thanks to the `to_dict` method
    """

    def __init__(self, page: Dict) -> None:
        """Constructor
        Data stored :
        - page id
        - page title
        - datetime of last edit
        - start datetime
        - end datetime : if not provided set to start datetime
        - Description
        - Flight Code
        - Url

        Args:
            page (Dict): dict from API call result
        """
        # Initialize with default values
        self._id = None
        self.title = None
        self.last_edited_time = None
        self.start_date = None
        self.end_date = None
        self.url = ""
        self.description = ""
        self.flight_code = ""
        self.all_day = False
        self.start_notion = ""
        self.end_notion = ""

        try:
            self._id = page['id']
            properties = page.get('properties') or {}
            title = (properties.get('Name') or {}).get('title') or []
            if (len(title)>0):
                self.title = title[0].get('plain_text')
                self.last_edited_time = self._convert_datetime(page.get('last_edited_time'))
                # A row whose Date is still empty has `date: null`; that is a row
                # waiting to be filled in, not a reason to fail the run.
                date_prop = (properties.get('Date') or {}).get('date') or {}
                start_raw = date_prop.get('start')
                # Notion sends a bare date for all-day entries and a full
                # timestamp for timed ones; that is the only reliable signal.
                self.all_day = 'T' not in (start_raw or 'T')
                self.start_date = self._convert_datetime(start_raw)
                end_raw = date_prop.get('end')
                end_date = self._convert_datetime(end_raw)
                # Kept verbatim so the state file stays readable: these show the
                # time as entered in Notion, with the zone it belongs to.
                self.start_notion = start_raw or ""
                self.end_notion = end_raw or self.start_notion
                if end_date is None:
                    self.end_date = self.start_date
                else:
                    self.end_date = end_date
                self.url = self._url(properties, 'URL')
                self.description = self._rich_text(properties, 'Description')
                # Flights store their flight number in a dedicated property
                self.flight_code = self._normalize_spaces(self._rich_text(properties, 'Flight Code'))
        except Exception as e:
            logging.error(f"Failed to parse Notion card {self._id}: {e}")
            raise

    @staticmethod
    def _rich_text(properties: Dict, name: str) -> str:
        """Returns the plain text of a rich_text property, or "" when absent/empty

        Args:
            properties (Dict): `properties` dict of a Notion page
            name (str): name of the property

        Returns:
            str: concatenation of every text chunk of the property
        """
        prop = properties.get(name) or {}
        chunks = prop.get('rich_text') or []
        return ''.join(chunk.get('plain_text') or '' for chunk in chunks)

    @staticmethod
    def _url(properties: Dict, name: str) -> str:
        """Returns the value of a url property, or "" when absent/empty

        Args:
            properties (Dict): `properties` dict of a Notion page
            name (str): name of the property

        Returns:
            str: url
        """
        prop = properties.get(name) or {}
        return prop.get('url') or ""

    @staticmethod
    def _normalize_spaces(text: str) -> str:
        """Collapses every run of whitespace (including non-breaking spaces) into a single space

        Args:
            text (str): text to normalize

        Returns:
            str: normalized text
        """
        return ' '.join(text.split())

    @property
    def is_syncable(self) -> bool:
        """Whether this card can become a Calendar event.

        A card with no start date cannot be placed on a calendar, and one with
        no title would become an event named "None", so both are skipped rather
        than guessed at.

        Returns:
            bool: True when the card has both a title and a start date
        """
        return bool(self.title) and self.start_date is not None

    def to_dict(self) -> Dict:
        """Returns a representation of the card object as a Dict

        Returns:
            Dict: dict
        """
        _dict = {
            'id': self._id,
            'last_edit': self.last_edited_time,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'start_notion': self.start_notion,
            'end_notion': self.end_notion,
            'title': self.title,
            'url': self.url,
            'description': self.description,
            'flight_code': self.flight_code,
            'all_day': self.all_day
        }
        return _dict

    def __repr__(self) -> str:
        return f"id : {self._id}\ntitle : {self.title}\nstart : {self.start_date}\nend : {self.end_date}\nlast edit : {self.last_edited_time}\nurl : {self.url}\ndescription : {self.description}\nflight code : {self.flight_code}\nall day : {self.all_day}"

    def _convert_datetime(self, notion_datetime: str) -> datetime:
        """Helper function to normalize datetimes to naive UTC.

        Notion sends timestamps with the offset of the time zone the date was
        entered in, e.g. `2026-11-15T13:20:00.000+07:00`. Dropping that offset
        would move the event by hours, so the instant is converted to UTC and
        stored without a tzinfo. Storing UTC also keeps the state file stable
        when the machine running the sync changes time zone.

        Bare dates (all-day entries) carry no instant and are left untouched.

        Args:
            notion_datetime (str): datetime

        Returns:
            datetime: naive datetime, in UTC for timestamps
        """
        if notion_datetime is None:
            return notion_datetime
        if 'T' not in notion_datetime:
            return datetime.strptime(f'{notion_datetime} 00:00:00', '%Y-%m-%d %H:%M:%S')
        parsed = datetime.fromisoformat(notion_datetime.replace('Z', '+00:00'))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed.replace(microsecond=0)


class NotionClient:
    """This class handles calls to the notion API
    """

    def __init__(self, token) -> None:
        """Constructor of the NotionClient object
        It stores the API key as well as some constant parameters needed in API calls
        """
        self._key = token
        self._headers = {
            'Authorization': f'Bearer {self._key}',
            'Notion-Version': '2021-08-16',
        }
        self._base_url = "https://api.notion.com/v1/"

    def get_live_cards(self, database_id: str) -> List[Card]:
        """API call that returns a list of card where the property date is specified.
        Outdated cards are not returned

        Args:
            database_id (str): id of notion database

        Raises:
            Exception: if the API call failed

        Returns:
            List[Card]: list of cards
        """
        has_more = True
        _list_page = []
        start_cursor = None
        _url = f"{self._base_url}databases/{database_id}/query"
        payload = {}
        while has_more:
            if start_cursor:
                payload['start_cursor'] = start_cursor
            q = requests.post(_url, headers=self._headers, json=payload)
            if not q.ok:
                logging.error(f'while fetching cards on Notion : {q.text}')
                raise Exception(q.text)
            try:
                data = q.json()
                _list_page += data['results']
            except Exception as e:
                logging.error(f'while fetching cards on Notion : {q.text}')
                raise Exception(q.text) from e
            has_more = data['has_more']
            start_cursor = data['next_cursor']
        _list_card = []
        for page in _list_page:
            try:
                card = Card(page)
            except Exception as e:
                # One unparseable page must not cost every other event
                logging.error(f"skipping Notion page {page.get('id')}: {e}")
                continue
            if not card.is_syncable:
                reason = 'no title' if not card.title else 'no date set'
                logging.warning(f"skipping Notion page {card._id} ('{card.title}'): {reason}")
                continue
            _list_card.append(card)
        return _list_card
