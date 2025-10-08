import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import market_data # Ensure models are imported

# --- Test Database Setup ---
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool, # Use a static pool for in-memory SQLite
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Fixture for Test Database Session ---
@pytest.fixture(scope="function")
def db_session():
    """
    Pytest fixture to create a new database session for each test.
    It also creates all tables before the test and drops them after.
    """
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

# --- Fixture for Test Client ---
@pytest.fixture(scope="function")
def client(db_session: Session):
    """
    Pytest fixture to create a TestClient with the database dependency overridden.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c

# --- Tests ---
def test_read_root(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to the EVE Online Market Analyzer API"}

def test_get_status(client: TestClient):
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_get_regions_empty(client: TestClient):
    response = client.get("/api/regions")
    assert response.status_code == 200
    assert response.json() == []