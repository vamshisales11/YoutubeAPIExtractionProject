#now that we have json data and schema, tables created, next we need to insert/load data into these tables

import json
from datetime import date
import logging

logger = logging.getLogger(__name__)

def load_data():
    # file_path = f"./data/YT_data_{date.today()}.json"
    file_path = f"/opt/airflow/data/video_data_{date.today()}.json"
    
    try:
        logger.info(f"Processing file: YT_data_({date.today()})")

        with open(file_path, "r", encoding="utf-8") as raw_data:
            data = json.load(raw_data)

        return data
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        raise
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON format in file: {file_path}")
        raise
    

##hree data is loaded into python object, next we will look into insert, updates and deletes