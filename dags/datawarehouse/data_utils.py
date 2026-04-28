from airflow.providers.postgres.hooks.postgres import PostgresHook
from psycopg2.extras import RealDictCursor

def get_conn_cursor():
    hook = PostgresHook(postgres_conn_id='postgres_default', database='elt_db')

    conn = hook.get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    
def close_conn_cursor(conn, cur):
    cur.close()
    conn.close()

    