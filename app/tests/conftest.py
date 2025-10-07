import os

# --- Set mock environment variables for testing ---
# This MUST be done before any application modules are imported to ensure
# the settings are loaded with the correct test configuration.
os.environ["TESTING"] = "1"
os.environ["POSTGRES_USER"] = "testuser"
os.environ["POSTGRES_PASSWORD"] = "testpassword"
os.environ["POSTGRES_DB"] = "testdb"
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_PORT"] = "5432"
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "6379"
os.environ["API_KEY"] = "testapikey"
os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/0"
os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6379/0"


import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Now that the environment is patched, we can safely import the app
from app.main import app
from app.database import Base, get_db


# --- Test Database Setup ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# --- Fixtures ---
@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """
    Create the test database and tables before any tests run.
    """
    Base.metadata.create_all(bind=engine)
    yield
    # Teardown: remove the test database file after all tests are done
    os.remove("./test.db")


@pytest.fixture(scope="function")
def db_session():
    """
    Provides a clean database session for each test function.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def test_client(db_session):
    """
    Creates a TestClient with an overridden database session dependency.
    """
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    # Clean up dependency overrides
    app.dependency_overrides.clear()