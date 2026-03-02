from src.Database import Database
import os
from datetime import datetime
import logging
from configparser import ConfigParser
from glob import glob

if __name__ == "__main__":
    start_datetime = datetime.now()
    cwd = os.path.dirname(os.path.abspath(__file__))
    log_file = os.path.join(cwd, 'logs', f"{start_datetime.strftime('%Y-%m-%dT%H:%M:%S')}.log")

    logging.basicConfig(filename=log_file, filemode='a', level=logging.INFO)

    log_files = glob(os.path.join(cwd, 'logs', '*.log'))

    for f in log_files:
        file_day = int(os.path.basename(f).split('T')[0].split('-')[-1])
        if file_day != start_datetime.day:
            os.remove(f)

    conf = ConfigParser()
    conf.read('config.ini')
    notion_token = conf['GLOBAL']['NOTION_TOKEN']
    apple_calendar = conf['GLOBAL']['APPLE_CALENDAR']
    for key, database_id in conf['DATABASES'].items():
        logging.info(f"Start database {key}")
        db = Database(database_id, notion_token, apple_calendar, folder=os.path.join(cwd, 'databases'))
        db.run()
        logging.info(f"End database {key}")
