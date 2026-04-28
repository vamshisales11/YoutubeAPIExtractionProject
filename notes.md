

# **YT_ELT Project: Complete Architecture & Connection Guide**

## **Project Overview**

This is a **data engineering ELT (Extract, Load, Transform)** pipeline that:
- **Extracts** YouTube channel data using the YouTube API
- **Loads** the raw data into a PostgreSQL staging database
- **Transforms** the data and moves it to a core schema
- **Orchestrates** everything using Airflow running in Docker containers
- **Tests** data quality throughout the process

---

## **The Big Picture: How Docker, Airflow & PostgreSQL Connect**

Think of this architecture like a factory assembly line running inside Docker containers:

```
┌─────────────────────────────────────────────────────────────────┐
│                    DOCKER COMPOSE NETWORK                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │           AIRFLOW CONTAINERS (Orchestration)               │ │
│  ├────────────────────────────────────────────────────────────┤ │
│  │                                                              │ │
│  │  Webserver (Port 8080)    Scheduler    Worker   Redis       │ │
│  │  UI Interface              Task Scheduler  Execute        Message │
│  │                                            Tasks           Queue  │
│  │                                                              │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              ▼                                    │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  POSTGRES CONTAINER (Database)                             │ │
│  ├────────────────────────────────────────────────────────────┤ │
│  │                                                              │ │
│  │  ┌─────────────────┐  ┌─────────────────┐                  │ │
│  │  │  STAGING Schema │  │   CORE Schema   │                  │ │
│  │  │  (Raw Data)     │  │  (Transformed)  │                  │ │
│  │  └─────────────────┘  └─────────────────┘                  │ │
│  │                                                              │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## **Connection Details Explained**

### **1. Docker Compose - The Orchestrator**

The `docker-compose.yaml` file defines **5 main containers**:

| Container | Purpose | Port | Role |
|-----------|---------|------|------|
| **postgres** | Database server | 5432 | Stores all data (3 databases) |
| **redis** | Message broker | 6379 | Distributes tasks between scheduler & workers |
| **airflow-webserver** | Web UI | 8080 | Dashboard to monitor DAGs |
| **airflow-scheduler** | Task scheduler | 8974 | Decides when to run DAGs |
| **airflow-worker** | Task executor | - | Executes the actual tasks |

**All containers share the same Docker network**, allowing them to communicate using container names (e.g., `postgres`, `redis`).

---

### **2. How Airflow Connects to PostgreSQL**

This is configured through **environment variables** in the `docker-compose.yaml`:

```yaml
# Airflow metadata database (tracks scheduler/task state)
AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://${METADATA_DATABASE_USERNAME}:${METADATA_DATABASE_PASSWORD}@postgres:5432/${METADATA_DATABASE_NAME}

# Celery backend database (stores task results)
AIRFLOW__CELERY__RESULT_BACKEND: db+postgresql://${CELERY_BACKEND_USERNAME}:${CELERY_BACKEND_PASSWORD}@postgres:5432/${CELERY_BACKEND_NAME}

# Connection to YOUR YouTube data database
AIRFLOW_CONN_POSTGRES_DB_YT_ELT: postgresql://${ELT_DATABASE_USERNAME}:${ELT_DATABASE_PASSWORD}@postgres:5432/${ELT_DATABASE_NAME}
```

**Key Point**: The connection uses `postgres` (container name), NOT `localhost`. This is how Docker networking works.

---

### **3. PostgreSQL Database Structure**

The single `postgres` container runs **3 separate databases**:

```sql
-- 1. Metadata Database (Airflow's own database)
airflow_db  -- Stores DAG runs, task state, user info

-- 2. Celery Backend Database (Task results storage)
celery_db   -- Stores results from worker tasks

-- 3. YouTube Data Database (YOUR data)
elt_db      -- Contains 2 schemas:
  ├── staging   -- Raw data from YouTube API
  └── core      -- Transformed/clean data
```

---

## **The Data Flow: Step-by-Step**

### **DAG 1: `produce_json` (Extract Phase)**

```python
# Runs daily at 14:00 UTC
Task 1: get_playlist_id() 
  ↓ Calls YouTube API using AIRFLOW_VAR_API_KEY and AIRFLOW_VAR_CHANNEL_HANDLE
  ↓ Returns playlist ID for the channel

Task 2: get_video_ids(playlist_id)
  ↓ Calls YouTube API for all video IDs in playlist
  ↓ Pagination handled (processes 50 videos per request)

Task 3: extract_video_data(video_ids)
  ↓ Calls YouTube API for detailed stats for each video
  ↓ Extracts: Video ID, Title, Upload Date, Duration, Views, Likes, Comments

Task 4: save_to_json(extracted_data)
  ↓ Saves to: ./data/YT_data_{today's_date}.json
  ↓ FILE IS CREATED IN THE CONTAINER'S MOUNTED VOLUME

Task 5: trigger_update_db
  ↓ Manually triggers next DAG (produce_json → update_db)
```

**Connection Point 1**: Variables configured in docker-compose:
- `API_KEY` = `AIRFLOW_VAR_API_KEY`
- `CHANNEL_HANDLE` = `AIRFLOW_VAR_CHANNEL_HANDLE`

---

### **DAG 2: `update_db` (Load & Transform Phase)**

```python
Task 1: staging_table()
  ↓ Reads JSON file: ./data/YT_data_{today's_date}.json
  ↓ Connects to PostgreSQL using AIRFLOW_CONN_POSTGRES_DB_YT_ELT
  ↓ Creates staging schema if not exists
  ↓ Creates yt_api table in staging schema
  ↓ Loads data: INSERT (new videos) or UPDATE (existing videos)

Task 2: core_table()
  ↓ Reads from staging.yt_api
  ↓ Transforms data (e.g., converts duration format)
  ↓ Creates core schema if not exists
  ↓ Creates yt_api table in core schema
  ↓ Loads transformed data: INSERT or UPDATE

Task 3: trigger_data_quality
  ↓ Manually triggers next DAG (update_db → data_quality)
```

**Connection Point 2**: PostgreSQL connection:
```python
from airflow.providers.postgres.hooks.postgres import PostgresHook

hook = PostgresHook(postgres_conn_id="postgres_db_yt_elt", database="elt_db")
conn = hook.get_conn()
cur = conn.cursor()
```

This reads the connection from: `AIRFLOW_CONN_POSTGRES_DB_YT_ELT`

---

### **DAG 3: `data_quality` (Validation Phase)**

```python
Task 1: soda_validate_staging()
  ↓ Runs SODA scan on staging schema
  ↓ Checks for nulls, duplicates, freshness
  ↓ Validates data quality rules

Task 2: soda_validate_core()
  ↓ Runs SODA scan on core schema
  ↓ Validates transformed data quality
```

---

## **Key Connection Points - The Confusion Clarified**

### **Problem**: "How do Airflow tasks access PostgreSQL?"

**Answer**: Through the PostgreSQL Hook with a **connection string** defined as an environment variable.

```
Environment Variable (docker-compose.yaml):
    AIRFLOW_CONN_POSTGRES_DB_YT_ELT = 
    postgresql://username:password@postgres:5432/elt_db

Python Code (in DAG task):
    hook = PostgresHook(postgres_conn_id="postgres_db_yt_elt")
    connection = hook.get_conn()
    
Connection ID: "postgres_db_yt_elt" → Maps to env var "AIRFLOW_CONN_POSTGRES_DB_YT_ELT"
Host: postgres → Docker container name (Docker DNS resolves this)
Port: 5432 → PostgreSQL default
Database: elt_db → The YouTube data database
```

### **Problem**: "How do files persist between containers?"

**Answer**: Through Docker **volume mounting**.

```yaml
volumes:
  - ./data:/opt/airflow/data     # Local ./data folder ↔ Container /opt/airflow/data
  - ./dags:/opt/airflow/dags     # Local ./dags folder ↔ Container /opt/airflow/dags
```

When Task saves: `./data/YT_data_2026-04-28.json` → Actually saves to your machine's `./data/` folder
When Task reads: `./data/YT_data_2026-04-28.json` → Reads from your machine's `./data/` folder

### **Problem**: "How does the Scheduler know when to run tasks?"

**Answer**: Through **Celery** with Redis message broker.

```
Scheduler (airflow-scheduler container)
  ↓ Checks DAG schedule: "0 14 * * *" (daily at 14:00)
  ↓ Sends task to Redis (message queue)
  ↓
Worker (airflow-worker container)
  ↓ Reads task from Redis
  ↓ Executes Python code
  ↓ Stores result back in Celery database
  ↓
Scheduler picks up result
```

---

## **Environment Variables (.env file)**

You need to create a `.env` file with:

```bash
# Airflow Admin
AIRFLOW_WWW_USER_USERNAME=airflow
AIRFLOW_WWW_USER_PASSWORD=airflow
AIRFLOW_UID=50000

# PostgreSQL Connection
POSTGRES_CONN_HOST=postgres          # Container name
POSTGRES_CONN_PORT=5432
POSTGRES_CONN_USERNAME=airflow_user
POSTGRES_CONN_PASSWORD=your_password

# Airflow Metadata Database
METADATA_DATABASE_NAME=airflow_db
METADATA_DATABASE_USERNAME=airflow_user
METADATA_DATABASE_PASSWORD=your_password

# Celery Backend Database
CELERY_BACKEND_NAME=celery_db
CELERY_BACKEND_USERNAME=celery_user
CELERY_BACKEND_PASSWORD=your_password

# YouTube Data Database
ELT_DATABASE_NAME=elt_db
ELT_DATABASE_USERNAME=elt_user
ELT_DATABASE_PASSWORD=your_password

# YouTube API
API_KEY=your_youtube_api_key
CHANNEL_HANDLE=MrBeast

# Encryption
FERNET_KEY=your_fernet_key

# Docker Hub
DOCKERHUB_NAMESPACE=your_namespace
DOCKERHUB_REPOSITORY=yt_elt
DOCKERHUB_USERNAME=your_username
```

---

## **How to Run the Project**

```bash
# 1. Create .env file with values above

# 2. Start all containers
docker compose up -d

# 3. Access Airflow UI
# Go to: http://localhost:8080

# 4. Unpause DAGs in UI and trigger manually (or wait for schedule)

# 5. Monitor execution
docker compose logs -f airflow-scheduler
docker compose logs -f airflow-worker

# 6. Connect to PostgreSQL directly
psql -h localhost -U elt_user -d elt_db
SELECT * FROM staging.yt_api;
SELECT * FROM core.yt_api;
```

---

## **Architecture Summary Table**

| Component | Type | Purpose | Communicates With |
|-----------|------|---------|-------------------|
| **PostgreSQL** | Container | Data storage | Airflow tasks via Hook |
| **Redis** | Container | Message broker | Scheduler ↔ Worker |
| **Airflow Scheduler** | Container | Task planner | Redis, PostgreSQL, Worker |
| **Airflow Worker** | Container | Task executor | Redis, PostgreSQL, File system |
| **Airflow Webserver** | Container | UI Dashboard | Metadata database |
| **YouTube API** | External | Data source | Python requests in tasks |
| **Docker Volume** | Mount point | File persistence | All containers can access |

---

## **Troubleshooting Checklist**

- ✅ Container names in connection strings must match docker-compose service names
- ✅ Use container name for host (not localhost) in connection strings
- ✅ Volumes must be mounted for files to persist
- ✅ Environment variables in docker-compose must be loaded from .env
- ✅ Ports (8080, 5432, 6379) must not be in use on your machine
- ✅ DAGs must be placed in the mounted `./dags/` folder
- ✅ Use `PostgresHook` to connect from Python tasks, not direct psycopg2

---

This architecture ensures **scalability** (you can add more workers), **reliability** (Airflow retries failed tasks), and **data quality** (SODA validates at each stage).