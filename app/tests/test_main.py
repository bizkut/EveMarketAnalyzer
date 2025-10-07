from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models import Region

def test_read_root(test_client: TestClient):
    """
    Test the root endpoint.
    """
    response = test_client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to the EVE Online Market Analysis API"}

def test_get_regions_list(test_client: TestClient, db_session: Session):
    """
    Test the /regions endpoint.
    """
    # Test with no regions in the database
    response = test_client.get("/api/regions")
    assert response.status_code == 200
    assert response.json() == []

    # Add a region and test again
    region = Region(id=10000001, name="Test Region")
    db_session.add(region)
    db_session.commit()

    response = test_client.get("/api/regions")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "Test Region"