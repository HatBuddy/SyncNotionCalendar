import applescript
import logging


class CalendarClient:
    """Class that handles applescript requests to Calendar app
    """

    def __init__(self, calendar_name: str) -> None:
        """Constructor

        Args:
            calendar_name (str): calendar name
        """
        self.name = calendar_name

    def __repr__(self) -> str:
        return f"calendar {self.name}"

    def applescript_escape(self, s: str, max_length: int = 900) -> str:
        """Escape a string for safe use in AppleScript double-quoted strings.
        Converts both literal '\\n' and real newlines to a space, and truncates if too long."""
        if not isinstance(s, str):
            s = str(s)
        # Truncate long descriptions for testing (AppleScript/Calendar may have limits)
        if len(s) > max_length:
            s = s[:max_length] + "..."
        # Replace literal backslash-n, real newlines, and carriage returns with a space
        s = s.replace('\\n', ' ').replace('\n', ' ').replace('\r', '')
        return s.replace('\\', '\\\\').replace('"', '\\"')

    def add_event(self, title: str, start_date: str, end_date: str, start_time: str, end_time: str
        , url_str: str, description_str: str) -> str:
        """Adds an event to Calendar
        Summary is set to `title` and we define the start datetime and end datetime with the provided arguments

        Args:
            title (str): title of notion card. Will be used for the calendar summary
            start_date (str) : format `%Y-%m-%d`
            end_date (str) : format `%Y-%m-%d`
            start_time (str) : format `%H:%M:%S`
            end_time (str) : format `%H:%M:%S`
            url_str (str) : url of the event
            description_str (str) : description of the event
        
        Returns:
            str : Id of the newly created event
        """
        from datetime import datetime
        # Parse and format start date
        start_dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M:%S")
        start_applescript = start_dt.strftime('%A, %B %d, %Y at %I:%M:%S %p')
        set_start_date = f'set theStartDate to date "{start_applescript}"\n'
        cmd = set_start_date

        # Adjust end date for inclusivity
        is_all_day = (start_time == "00:00:00" and end_time == "00:00:00")
        if is_all_day:
            # For all-day events, add one day to the end date to make it inclusive
            from datetime import timedelta
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            end_time_str = "00:00:00"
            end_dt = datetime.combine(end_dt.date(), datetime.strptime(end_time_str, "%H:%M:%S").time())
        else:
            # For timed events, if end_time is '00:00:00', set it to '23:59:59' to include the full end date
            if end_time == "00:00:00":
                end_time = "23:59:59"
            end_dt = datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M:%S")
        end_applescript = end_dt.strftime('%A, %B %d, %Y at %I:%M:%S %p')
        set_end_date = f'set theEndDate to date "{end_applescript}"\n'
        cmd += set_end_date

        # Build AppleScript for event creation, only including url/description if present
        is_all_day = (start_time == "00:00:00" and end_time == "00:00:00")
        cmd += f"""
        tell application "Calendar"
            tell calendar "{self.applescript_escape(self.name)}"
"""
        if is_all_day:
            cmd += f"                set newEvent to make new event with properties {{summary:\"{self.applescript_escape(title)}\", start date:theStartDate, end date:theEndDate, allday event:true}}\n"
        else:
            cmd += f"                set newEvent to make new event with properties {{summary:\"{self.applescript_escape(title)}\", start date:theStartDate, end date:theEndDate}}\n"
        # Only add url if not None or empty
        if url_str:
            cmd += f"                set url of newEvent to \"{self.applescript_escape(url_str)}\"\n"
        # Only add description if not None or empty
        if description_str:
            cmd += f'                set description of newEvent to "{self.applescript_escape(description_str)}"\n'
        # Add code to return the event ID
        cmd += """
                set eventId to id of newEvent
                return eventId
            end tell
            save
        end tell
        """
        # Log variables used in the AppleScript for debugging
        logging.debug(f"Adding event - calendar: {self.name}, title: {title}, dates: {start_date} to {end_date}")
        logging.debug("AppleScript command:\n" + cmd)
        
        try:
            r = applescript.run(cmd)
            
            if r.err:
                logging.error(f"AppleScript error while adding '{title}': {r.err}")
                logging.debug(f"AppleScript output: {r.out}")
                raise Exception(f"Failed to add event to {self.name} calendar")
            
            # If no error, return event_id if present
            event_id = None
            if r.out:
                event_id = r.out.strip().split()[-1]
                logging.info(f"Successfully added '{title}' to {self.name} calendar, event_id: {event_id}")
            else:
                logging.warning(f"Added '{title}' to {self.name} calendar but no event_id was returned")
            
            return event_id
            
        except Exception as e:
            logging.error(f"Unexpected error while adding event '{title}': {str(e)}")
            raise

    def delete_event(self, id: str) -> None:
        """Remove event with id from Calendar

        Args:
            id (str) : id of the event to remove
        """
        cmd = f"""
        tell application "Calendar"
            tell calendar "{self.name}"
            delete event id "{id}"
            save
            end tell
        end tell
        """
        r = applescript.run(cmd)
        if r.err:
            logging.error(f"failed to delete event {id}. Applescript error : {r.err}")
            # raise Exception(r.err)
        else:
            logging.info(f"event {id} removed")
