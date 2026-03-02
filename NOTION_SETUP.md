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

> The `Name` property is Notion's default title field that every database already has. Do not rename it to anything else.

---

## Property behaviour

### Name
- Maps to the **event title** in Apple Calendar.
- Events with an empty `Name` are **silently skipped** and not synced.

### Date
- Maps to the **start and end datetime** of the Calendar event.
- Events with no date set will cause a sync error — every row must have a start date.
- **All-day events:** set a date with no time component in Notion. The sync tool detects these automatically and creates them as all-day events in Calendar.
- **Timed events:** set a date and time in Notion (e.g. `Jan 15, 2025 2:30 PM`).
- **Multi-day events:** enable "End date" in the Date property and set both a start and end date.
- If no end date is set, timed events default to **start + 1 hour**; all-day events span a single day.

### URL
- Maps to the **URL field** of the Calendar event.
- Leave empty if not needed; the column must still exist in the database.

### Description
- Maps to the **notes/description field** of the Calendar event.
- Only the first block of text is synced (plain text only — formatting is not preserved).
- Leave empty if not needed; the column must still exist in the database.

---

## What gets synced

| Notion field | Apple Calendar field |
|---|---|
| `Name` | Title |
| `Date` (start) | Start date/time |
| `Date` (end) | End date/time |
| `URL` | URL |
| `Description` | Notes |

Sync is **one-way: Notion → Apple Calendar**. Changes made directly in Apple Calendar are not written back to Notion.

---

## Sync behaviour

| Notion action | Calendar result |
|---|---|
| Add a row with a date | New event created |
| Change the title, start date, or end date | Event deleted and re-created with updated details |
| Delete a row | Event deleted |
| Change only `URL` or `Description` | No update (these fields do not trigger a re-sync) |

> Modifications are only detected when Notion's built-in `Last edited time` changes **and** the title or dates differ. Changing only the URL or description updates `Last edited time` in Notion but will not re-sync the Calendar event.

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
