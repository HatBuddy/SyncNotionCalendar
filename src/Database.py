from datetime import datetime, timedelta
from typing import List, Tuple
import pandas as pd
import os
from .notionClient import NotionClient
from .CalendarClient import CalendarClient
import logging

class Database():
    """This class stores event already added to Calendar. It performs also updates : add new cards, modify cards, delete cards.
    """
    def __init__(self,id:str,notion_token:str,apple_calendar:str,folder=os.getcwd()) -> None:
        """Constructor

        Args:
            id (str): id of the database (corresponds to the notion database id)
            folder (str, optional): folder in which the database is stored. Defaults to os.getcwd().
        """
        self.notion_client = NotionClient(notion_token)
        self.calendar_client = CalendarClient(apple_calendar)
        self._path = f"{os.path.join(folder,id)}.csv"
        self.id = id
        
        if os.path.exists(self._path):
            self.df = pd.read_csv(self._path,index_col='id',parse_dates=['last_edit','start_date','end_date'])
        else:
            self.df = self._empty()
            self.save()

    def _empty(self) -> pd.DataFrame:
        """Returns an empty DataFrame with the right columns and index

        Returns:
            pd.DataFrame: dataframe
        """
        df = pd.DataFrame(columns=[
                'id',
                'last_edit',
                'start_date',
                'end_date',
                'title',
                'event_id'
            ]).set_index('id')
        return df

    def save(self)->None:
        """Saves the database as a .csv file
        """
        self.df.to_csv(self._path)

    def _get_card_for_calendar(self, card_serie: pd.Series) -> Tuple:
        """Returns args to create an event

        Args:
            card_serie (pd.Series): series that corresponds to a Notion card

        Returns:
            Tuple: (title, start_date, end_date, start_time, end_time, url_str, description_str)
        """
        # Get title with empty string as fallback
        title = getattr(card_serie, 'title', 'Untitled Event')
        
        # Get current time for fallback values
        now = datetime.now()
        default_date = now.strftime('%Y-%m-%d')
        default_time = '00:00:00'
        
        # Handle start date and time
        try:
            if pd.isna(getattr(card_serie, 'start_date', None)):
                start_date = default_date
                start_time = default_time
            else:
                start_str = str(card_serie.start_date)
                if ' ' in start_str and start_str != 'NaT' and 'NaT' not in start_str:
                    start_date, start_time = start_str.split(' ')[:2]
                    # Validate time format
                    try:
                        datetime.strptime(start_time, '%H:%M:%S')
                    except ValueError:
                        start_time = default_time
                else:
                    start_date = start_str if start_str != 'NaT' else default_date
                    start_time = default_time
                
                # Validate date format
                try:
                    datetime.strptime(start_date, '%Y-%m-%d')
                except ValueError:
                    start_date = default_date
        except Exception as e:
            logging.warning(f"Error parsing start date for '{title}': {e}. Using default values.")
            start_date = default_date
            start_time = default_time
        
        # Handle end date and time
        try:
            if pd.isna(getattr(card_serie, 'end_date', None)):
                # If no end date, use start date + 1 hour
                end_date = start_date
                try:
                    start_dt = datetime.strptime(f"{start_date} {start_time}", '%Y-%m-%d %H:%M:%S')
                    end_dt = start_dt + timedelta(hours=1)
                    end_date = end_dt.strftime('%Y-%m-%d')
                    end_time = end_dt.strftime('%H:%M:%S')
                except:
                    end_time = '23:59:59'
            else:
                end_str = str(card_serie.end_date)
                if ' ' in end_str and end_str != 'NaT' and 'NaT' not in end_str:
                    end_date, end_time = end_str.split(' ')[:2]
                    # Validate time format
                    try:
                        datetime.strptime(end_time, '%H:%M:%S')
                    except ValueError:
                        end_time = '23:59:59'
                else:
                    end_date = end_str if end_str != 'NaT' else start_date
                    # For all-day events, if end time is 00:00:00, subtract one day from the end date
                    if ' ' in end_str and end_str.endswith('00:00:00'):
                        try:
                            end_date_dt = datetime.strptime(end_date, '%Y-%m-%d')
                            end_date_dt = end_date_dt - timedelta(days=1)
                            end_date = end_date_dt.strftime('%Y-%m-%d')
                        except:
                            pass
                    end_time = '23:59:59'  # Default to end of day if no time provided
                
                # Validate date format
                try:
                    datetime.strptime(end_date, '%Y-%m-%d')
                except ValueError:
                    end_date = start_date
        except Exception as e:
            logging.warning(f"Error parsing end date for '{title}': {e}. Using start date + 1 hour.")
            end_date = start_date
            end_time = '23:59:59'
        
        # Get URL and description with empty string as fallback
        url_str = str(getattr(card_serie, 'url', '')).strip()
        description_str = str(getattr(card_serie, 'description', '')).strip()
        
        return (title, start_date, end_date, start_time, end_time, url_str, description_str)

    def get_live(self)->pd.DataFrame:
        """Get a database corresponding to the actual state in Notion app
        Some events could have been added, deleted, modified

        Returns:
            pd.DataFrame: live database
        """
        current_cards = self.notion_client.get_live_cards(self.id)
        current_as_dict = list(map(lambda card : card.to_dict(),current_cards))
        if len(current_as_dict) > 0:
            return pd.DataFrame(current_as_dict).set_index('id')
        else:
            return self._empty()

    def get_outdated(self)->List:
        """Returns a list of index that correspond to finished events in the database 

        Returns:
            List: list of index
        """
        outdated = list(self.df[self.df.end_date.dt.date < datetime.now().date()].index)
        logging.info(f"{len(outdated)} outdated events found")
        for id in outdated:
            logging.info(f"{id} is outdated")
        return outdated


    def get_deleted(self,current=None)->List:
        """Returns a list of index of events deleted from the Notion app

        Args:
            current (pd.DataFrame, optional): live databese. Defaults to None.

        Returns:
            List: list of index
        """
        if current is None:
            current = self.get_live()
        stored = self.df
        index = list(set(stored.index) - set(current.index))
        logging.info(f"{len(index)} events have been deleted on Notion")
        for id in index:
            logging.info(f"{id} has been deleted on Notion")
        return index

    
    def remove_events(self,list_id:List)->None:
        """Removes events from the database

        Args:
            list_id (List): list of id
        """
        for id in list_id:
            event_id = self.df.loc[id,'event_id']
            self.calendar_client.delete_event(event_id)
            self.df = self.df.drop(id)
            logging.info(f"card {id} has been deleted from the database")
        self.save()
        

    def get_modified(self,current=None)->List:
        """Returns a list of index of events that have been modified from the Notion app.
        An event is said to be modified when : last_edit has changed and either start datetime, end datetime or title has changed too

        Args:
            current (pd.DataFrame, optional): live database. Defaults to None.

        Returns:
            List: list of id
        """
        if current is None:
            current = self.get_live()
        stored = self.df
        _joined = stored.join(current,lsuffix='_stored')


        _filter = _joined.last_edit_stored != _joined.last_edit
        _filter = _filter & ((_joined.title != _joined.title_stored) | (_joined.start_date != _joined.start_date_stored) | (_joined.end_date != _joined.end_date_stored))
        _filter = _filter & (~ pd.isnull(_joined.last_edit)) & (~ pd.isnull(_joined.last_edit_stored))

        
        filtered_df = _joined[_filter]
        index = list(filtered_df.index)
        logging.info(f"{len(index)} events have been modified on Notion")
        for id in index:
            logging.info(f"{id} has been modified on Notion")
        return index


    def modify_events(self,list_id:List,current=None)->None:
        """Update the even in the database and in the Calendar app

        Args:
            list_id (List): list of events that have been modified from Notion app.
            current (pd.DataFrame, optional): live database. Defaults to None.
        """
        if current is None:
            current = self.get_live()
        for id in list_id:
            modified_event = current.loc[id].copy()
            self.calendar_client.delete_event(self.df.loc[id,'event_id'])
            new_event_id = self.calendar_client.add_event(*self._get_card_for_calendar(modified_event))
            modified_event['event_id'] = new_event_id
            self.df.loc[id] = modified_event
            logging.info(f"{id} has been updated on the databese")
            self.save()

    

    def get_new(self,current=None)->List:
        """Returns index of newly created events on Notion

        Args:
            current (pd.DataFrame, optional): live database. Defaults to None.

        Returns:
            List: list of new event id
        """
        if current is None:
            current = self.get_live()
        stored = self.df
        set_index = set(current.index) - set(stored.index)
        index = list(set_index)
        logging.info(f"{len(index)} events have been added on Notion")
        for id in index:
            logging.info(f"{id} has been added on Notion")
        return index

    def add_events(self, list_id: List, current=None) -> None:
        """Adds newly added events on the database and create an event on Calendar

        Args:
            list_id (List): list of index
            current (pd.DataFrame, optional): live database. Defaults to None.
        """
        if not list_id:  # If no events to add, return early
            return
            
        if current is None:
            current = self.get_live()
            
        to_add = current.loc[list_id]
        success_count = 0
        error_count = 0
        
        for id, s in to_add.iterrows():
            try:
                # Skip if event already exists with same title and dates
                existing_event = self.df[
                    (self.df.title == s.title) & 
                    (self.df.start_date == s.start_date) & 
                    (self.df.end_date == s.end_date)
                ]
                
                if not existing_event.empty:
                    logging.info(f"Skipping duplicate: Event '{s.title}' on {s.start_date} already exists in database.")
                    continue
                    
                if id in self.df.index:
                    logging.info(f"Skipping: Event ID {id} already exists in database.")
                    continue
                
                # Get calendar event details with proper error handling
                try:
                    event_details = self._get_card_for_calendar(s)
                except Exception as e:
                    logging.error(f"Error processing event '{getattr(s, 'title', 'Untitled')}' (ID: {id}): {str(e)}")
                    error_count += 1
                    continue
                
                # Add event to calendar
                try:
                    event_id = self.calendar_client.add_event(*event_details)
                    if not event_id:
                        raise ValueError("Failed to get event ID from calendar")
                        
                    # Update the series with the event ID
                    s['event_id'] = event_id
                    
                    # Add to our dataframe
                    self.df.loc[id] = s
                    success_count += 1
                    logging.info(f"Added event '{s.title}' (ID: {id}) to calendar with event ID: {event_id}")
                    
                    # Save after each successful addition
                    self.save()
                    
                except Exception as e:
                    logging.error(f"Failed to add event '{getattr(s, 'title', 'Untitled')}' (ID: {id}) to calendar: {str(e)}")
                    error_count += 1
                    
            except Exception as e:
                logging.error(f"Unexpected error processing event ID {id}: {str(e)}")
                error_count += 1
        
        # Log summary
        if success_count > 0 or error_count > 0:
            logging.info(f"Add events summary: {success_count} added, {error_count} failed, {len(list_id) - success_count - error_count} skipped (duplicates or already exists)")

    def run(self):
        live = self.get_live()

        # # Remove outdated events
        # if self.df.shape[0] > 0:
        #     id_outdated = self.get_outdated()
        #     self.remove_events(id_outdated)
        
        # Add new events
        id_news = self.get_new(current=live)
        self.add_events(id_news,current=live)

        # Remove deleted events
        id_deleted = self.get_deleted(current=live)
        self.remove_events(id_deleted)

        # Modify modified events
        id_modified = self.get_modified(current=live)
        self.modify_events(id_modified,current=live)