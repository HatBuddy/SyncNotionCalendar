# Notion Database Setup

This document describes the exact Notion database structure required for SyncNotionCalendar to work.

---

## Database name

The database can be named anything — it is referenced by its **ID**, not its name. The ID is taken from the database's URL and entered in `config.ini`.

To find the database ID:
1. Open the database in Notion (full-page view)
2. Copy the URL — it looks like: `https://www.notion.so/your-workspace/1d72019e55e180b9b334c0f8b4d695d7?v=...`
3. The 32-character hex string before the `?` is the database ID

---

## Required properties

The following properties **must exist with these exact names and types**. The names are case-sensitive.

| Property name | Notion type | Required? | Notes |
|---|---|---|---|
| `Name` | Title | Yes | The built-in page title property. Do not rename it. |
| `Date` | Date | Yes | Must have a start date set. The "End date" option should be enabled for multi-day or ranged events. |
| `URL` | URL | Yes | Can be left empty per event, but the column must exist. |
| `Description` | Text | Yes | Can be left empty per event, but the column must exist. |
| `Flight Code` | Text | No | Flight number(s) of a flight, e.g. `CI833`. Synced into the Calendar notes. Omit the column entirely if you do not track flights. |

> The `Name` property is Notion's default title field that every database already has. Do not rename it to anything else.

---

## Property behaviour

### Name
- Maps to the **event title** in Apple Calendar.
- Rows with an empty `Name` are **skipped** and not synced; a warning naming the page id is written to the log.

### Date
- Maps to the **start and end datetime** of the Calendar event.
- Rows with no date set are **skipped** with a warning; they do not fail the run, so a trip can be typed in before its dates are known.
- **All-day events:** set a date with no time component in Notion. The sync tool detects these automatically and creates them as all-day events in Calendar.
- **Timed events:** set a date and time in Notion (e.g. `Jan 15, 2025 2:30 PM`).
- **Multi-day events:** enable "End date" in the Date property and set both a start and end date.
- **Time zones:** Notion stores a timed date with the offset of the zone it was entered in (a flight typed in Bangkok local time arrives as `13:20:00.000+07:00`). That offset is the source of truth: the sync converts it to UTC for its state file and renders it in the time zone the Mac is set to when the event is written, so the event lands on the correct instant no matter where the sync runs from. Apple Calendar then displays it in whatever zone the device is on — a `13:20+07:00` departure reads 13:20 on a machine in Bangkok and 22:20 the previous day on a machine in Seattle. Bare dates (all-day) carry no instant and are never shifted. The state file keeps the Notion timestamp verbatim in `start_notion` / `end_notion` next to the UTC values, so the departure time can be checked against a ticket without converting anything by hand.
- If no end date is set, timed events default to **start + 1 hour**; all-day events span a single day.

### URL
- Maps to the **URL field** of the Calendar event.
- Leave empty if not needed; the column must still exist in the database.

### Description
- Maps to the **notes/description field** of the Calendar event.
- The whole text is synced as plain text (formatting is not preserved); line breaks are kept.
- Leave empty if not needed; the column must still exist in the database.

### Flight Code
- Prepended to the Calendar **notes/description** as `Flight: <code>`, e.g. `Flight: CI833`.
- When `Description` is also filled, the flight line comes first, then a blank line, then the description.
- Extra whitespace is collapsed, so `KL  1819 ` is synced as `KL 1819`.
- Optional: the column can be absent, and rows can leave it empty.

---

## What gets synced

| Notion field | Apple Calendar field |
|---|---|
| `Name` | Title |
| `Date` (start) | Start date/time |
| `Date` (end) | End date/time |
| `URL` | URL |
| `Flight Code` + `Description` | Notes |

Sync is **one-way: Notion → Apple Calendar**. Changes made directly in Apple Calendar are not written back to Notion.

---

## Sync behaviour

| Notion action | Calendar result |
|---|---|
| Add a row with a date | New event created |
| Change the title, start date, or end date | Event deleted and re-created with updated details |
| Delete a row | Event deleted |
| Change only `URL`, `Description` or `Flight Code` | Event deleted and re-created with updated details |

> Modifications are only detected when Notion's built-in `Last edited time` changes **and** one of the synced fields (title, dates, URL, description, flight code) differs from what was last synced. Editing a row in Notion without changing any synced field leaves the Calendar event untouched.

---

## config.ini setup

After creating the database, add its ID to `config.ini`:

```ini
[GLOBAL]
notion_token = your_notion_integration_token
apple_calendar = Your Calendar Name

[DATABASES]
db_1 = your_database_id_here
; Add more databases as needed:
; db_2 = another_database_id
```

- `notion_token` — the secret token from your Notion integration (starts with `ntn_` or `secret_`)
- `apple_calendar` — the **exact name** of the calendar in the Apple Calendar app (case-sensitive)
- Each key under `[DATABASES]` can be named anything; only the value (the database ID) matters

---

## Notion integration setup

The Notion integration must have access to the database:

1. Go to [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations) and create an integration
2. Copy the integration token into `config.ini` as `notion_token`
3. Open your Notion database → click `...` (top right) → **Connections** → add your integration
