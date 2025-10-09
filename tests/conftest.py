import os
import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set environment variables for testing BEFORE importing the app
os.environ['DATABASE_URL'] = "sqlite:///:memory:"
os.environ['REDIS_URL'] = "redis://localhost:6379/0"
os.environ['API_KEY'] = "test_api_key"
os.environ['TESTING'] = "True"

from app.main import app
from app.database import Base, get_db

# Use an in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Override the get_db dependency to use the test database
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="function")
def db_session():
    """
    Fixture to set up the database for each test function.
    It creates all tables, yields a session, and then drops all tables.
    """
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="module")
def client():
    """
    A TestClient instance that can be used to make requests to the application.
    """
    with TestClient(app) as c:
        yield c