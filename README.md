# Eve Market Analyzer

This project is a FastAPI application that provides an API for analyzing EVE Online market data. It fetches historical market data from EVEref, enriches it with details from the ESI API, and stores it in a PostgreSQL database. Background tasks for fetching and processing data are managed by Celery.

## Features

- **FastAPI Backend**: A modern, fast web framework for building APIs.
- **Celery for Background Tasks**: Asynchronous task queue for handling long-running data fetching and analysis processes.
- **PostgreSQL Database**: Robust and reliable storage for market data.
- **Docker Compose Setup**: Easily build and run the entire application stack (API, worker, scheduler, database, and message broker) with a single command.
- **Scheduled Data Updates**: Automatically fetches the latest market data daily.
- **Initial Data Load**: On first launch, it populates the database with the last year of market history.

## Getting Started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

### Setup

1.  **Clone the repository:**

    ```bash
    git clone <repository-url>
    cd EveMarketAnalyzer
    ```

2.  **Create an environment file:**

    Copy the example environment file to create your own local configuration:

    ```bash
    cp .env.example .env
    ```

3.  **Configure your environment:**

    Open the `.env` file and customize the variables as needed. At a minimum, you should set a secure `API_KEY`. The `DATABASE_URL` is configured in `docker-compose.yml` and does not need to be changed here unless you are running outside of Docker.

    ```env
    # This is for reference, but the primary DATABASE_URL is set in docker-compose.yml
    DATABASE_URL=postgresql://eveuser:password@db:5432/evemarket
    REDIS_URL=redis://redis:6379/0
    API_KEY=your_secret_api_key
    LOG_LEVEL=INFO
    ```

### Running the Application

1.  **Build and start the services:**

    Use Docker Compose to build the images and start all the containers in detached mode:

    ```bash
    docker-compose up --build -d
    ```

2.  **Verify the services are running:**

    You can check the status of the running containers:

    ```bash
    docker-compose ps
    ```

    You should see the `web`, `worker`, `beat`, `db`, and `redis` services running.

3.  **Access the API:**

    The API will be available at `http://localhost:8000`. You can access the interactive API documentation (Swagger UI) at `http://localhost:8000/docs`.

## API Endpoints

-   **`GET /api/markets/{region_id}/history?type_id={type_id}`**: Retrieves the market history for a specific item type within a given region.
-   **`POST /api/refresh`**: Triggers a full refresh of the market data, fetching the last year of history. This endpoint is protected and requires a valid API key sent in the `X-API-KEY` header.

## Running Tests

To run the test suite, execute the following command from the root of the project:

```bash
python -m pytest
```