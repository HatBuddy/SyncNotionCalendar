import os
import configparser
from pathlib import Path
import logging
import sys


class Configuration:
    def __init__(self) -> None:
        self.databases_id = []
        self.notion_token = None
        self.calendar_name = None
        self.config = configparser.ConfigParser()
        self.config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.ini')
        
    def load_config(self):
        """Load configuration from config.ini file"""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(
                "No config.ini file found. Please create one with your configuration."
            )
        
        self.config.read(self.config_path)
        
        # Load required values
        if 'GLOBAL' in self.config:
            self.notion_token = self.config['GLOBAL'].get('NOTION_TOKEN')
            self.calendar_name = self.config['GLOBAL'].get('APPLE_CALENDAR')
        
        # Load database IDs
        if 'DATABASES' in self.config:
            self.databases_id = [db_id for db_id in self.config['DATABASES'].values() if db_id.strip()]
        
        # Validate required values
        if not self.notion_token:
            raise ValueError("NOTION_TOKEN is not set in config.ini")
        if not self.calendar_name:
            raise ValueError("APPLE_CALENDAR is not set in config.ini")
        if not self.databases_id:
            raise ValueError("No valid database IDs found in config.ini")

    def create_conf_file(self, path):
        """Create config.ini from environment variables"""
        self.config["GLOBAL"] = {
            "NOTION_TOKEN": self.notion_token,
            "APPLE_CALENDAR": self.calendar_name
        }
        self.config["DATABASES"] = {}
        for i, db_id in enumerate(self.databases_id):
            if db_id:  # Only add non-empty database IDs
                self.config["DATABASES"][f"DB_{i+1}"] = db_id
                
        with open(path, "w") as f:
            self.config.write(f)

    def run(self, path):
        """Load configuration from config.ini"""
        try:
            self.load_config()
            print("\nConfiguration loaded from config.ini")
        except Exception as e:
            print(f"\nError: {str(e)}")
            print("\nPlease make sure you have a valid config.ini file with the required settings.")
            exit(1)

if __name__ == "__main__":
    path = sys.argv[1]
    c = Configuration()
    c.run(path)




