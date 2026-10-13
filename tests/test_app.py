from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from src import app as app_module


@pytest.fixture
def activity_state(monkeypatch):
    # Arrange a clean in-memory database for each test.
    isolated_activities = deepcopy(app_module.activities)
    monkeypatch.setattr(app_module, "activities", isolated_activities)
    return isolated_activities


@pytest.fixture
def client(activity_state):
    with TestClient(app_module.app) as test_client:
        yield test_client


def test_get_activities_returns_activity_data(client):
    # Arrange
    expected_activity = "Chess Club"

    # Act
    response = client.get("/activities")

    # Assert
    assert response.status_code == 200
    activities = response.json()
    assert expected_activity in activities
    assert activities[expected_activity]["participants"] == [
        "michael@mergington.edu",
        "daniel@mergington.edu",
    ]
    assert {
        "description",
        "schedule",
        "max_participants",
        "participants",
    } <= activities[expected_activity].keys()


def test_signup_normalizes_email_and_updates_activity(client, activity_state):
    # Arrange
    activity_name = "Art Club"
    email = " New.Student@Example.edu "

    # Act
    response = client.post(
        "/activities/Art%20Club/signup",
        params={"email": email},
    )

    # Assert
    assert response.status_code == 200
    assert response.json() == {
        "message": "Signed up new.student@example.edu for Art Club"
    }
    assert "new.student@example.edu" in activity_state[activity_name]["participants"]


def test_duplicate_signup_returns_400_even_with_case_variation(client, activity_state):
    # Arrange
    first_email = "student@example.edu"
    duplicate_email = "STUDENT@EXAMPLE.EDU"

    # Act
    first_response = client.post(
        "/activities/Chess%20Club/signup",
        params={"email": first_email},
    )
    duplicate_response = client.post(
        "/activities/Chess%20Club/signup",
        params={"email": duplicate_email},
    )

    # Assert
    assert first_response.status_code == 200
    assert duplicate_response.status_code == 400
    assert duplicate_response.json()["detail"] == "Student already signed up for this activity"
    assert activity_state["Chess Club"]["participants"].count(first_email) == 1


def test_signup_for_unknown_activity_returns_404(client):
    # Arrange
    activity_name = "Unknown Club"

    # Act
    response = client.post(
        f"/activities/{activity_name}/signup",
        params={"email": "student@example.edu"},
    )

    # Assert
    assert response.status_code == 404
    assert response.json()["detail"] == "Activity not found"


def test_unregister_removes_participant(client, activity_state):
    # Arrange
    activity_name = "Art Club"
    email = "student@example.edu"
    client.post(
        "/activities/Art%20Club/signup",
        params={"email": email},
    )

    # Act
    response = client.delete(
        "/activities/Art%20Club/participants",
        params={"email": email},
    )

    # Assert
    assert response.status_code == 200
    assert response.json() == {"message": "Unregistered student@example.edu from Art Club"}
    assert email not in activity_state[activity_name]["participants"]


def test_unregistering_absent_participant_returns_404(client):
    # Arrange
    email = "missing@example.edu"

    # Act
    response = client.delete(
        "/activities/Art%20Club/participants",
        params={"email": email},
    )

    # Assert
    assert response.status_code == 404
    assert response.json()["detail"] == "Student is not signed up for this activity"


def test_unregister_from_unknown_activity_returns_404(client):
    # Arrange
    activity_name = "Unknown Club"

    # Act
    response = client.delete(
        f"/activities/{activity_name}/participants",
        params={"email": "student@example.edu"},
    )

    # Assert
    assert response.status_code == 404
    assert response.json()["detail"] == "Activity not found"


def test_concurrent_duplicate_signups_only_register_once(activity_state):
    # Arrange
    email = "concurrent@example.edu"
    signup_url = "/activities/Art%20Club/signup"

    def signup(_):
        with TestClient(app_module.app) as concurrent_client:
            response = concurrent_client.post(signup_url, params={"email": email})
            return response.status_code

    # Act
    with ThreadPoolExecutor(max_workers=8) as executor:
        statuses = list(executor.map(signup, range(8)))

    # Assert
    assert statuses.count(200) == 1
    assert statuses.count(400) == 7
    assert activity_state["Art Club"]["participants"].count(email) == 1
