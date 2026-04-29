from airflow import DAG
import pendulum
from datetime import timedelta, datetime
from api.video_stats import get_playlist_id, get_video_ids, extract_video_data, save_to_json
from datawarehouse.dwh import staging_table, core_table



# Define the local timezone
local_tz = pendulum.timezone("America/Toronto")

#default args for the DAG
default_args = {
    "owner": "dataengineers",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "email": "vamshisales11@gmail.com",
    #'retries': 1,
    #'retry_delay': timedelta(minutes=5),
    "max_active_runs": 1,
    "dagrun_timeout": timedelta(hours=1),
    "start_date": datetime(2026, 1, 1, tzinfo=local_tz), 
     
    # Remove the # to make this active:
    #"end_date": datetime(2030, 12, 31, tzinfo=local_tz), 
}


with DAG(
    dag_id="produce_json",
    default_args=default_args,
    description="A DAG to extract video data from YouTube API and save it as JSON",
    schedule='0 14 * * *',
    catchup=False
) as dag:
    #define tasks
    playlistId = get_playlist_id()
    video_ids = get_video_ids(playlistId)
    extracted_data = extract_video_data(video_ids)
    save_to_json_task = save_to_json(extracted_data)

    #define dependencies
    playlistId >> video_ids >> extracted_data >> save_to_json_task




with DAG(
    dag_id="update_db",
    default_args=default_args,
    description="A DAG to process json file and insert data into staging and core",
    schedule='0 15 * * *',
    catchup=False
) as dag:
    #define tasks
    update_staging = staging_table()
    update_core = core_table()

    #define dependencies
    
    #define dependencies
    update_staging >> update_core