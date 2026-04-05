import pytest
from fastapi.testclient import TestClient
from app.main import app

def test_health_check_db_connection():
    # Using 'with TestClient' ensures the FastAPI lifespan (startup/shutdown) runs!
    # Without the 'with', the DB pool wouldn't be initialized during testing.
    with TestClient(app) as client:
        response = client.get("/health")
        
        # Verify HTTP status
        assert response.status_code == 200
        
        # Parse JSON payload
        data = response.json()
        
        # Verify business logic
        assert data["status"] == "ok"
        assert "PostgreSQL" in data["db_version"]
