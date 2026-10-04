from fastapi.testclient import TestClient


def login(client: TestClient, email: str) -> str:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": "test-password"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_ticket(client: TestClient, token: str) -> dict:
    response = client.post(
        "/tickets",
        headers=auth(token),
        json={"title": "Не работает проектор", "description": "Нет изображения на экране"},
    )
    assert response.status_code == 201
    return response.json()


def test_health_and_authentication(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/tickets").status_code == 401

    token = login(client, "user1@campus.local")
    me = client.get("/users/me", headers=auth(token))
    assert me.status_code == 200
    assert me.json()["role"] == "user"


def test_user_cannot_read_another_users_ticket(client: TestClient) -> None:
    owner = login(client, "user1@campus.local")
    other = login(client, "user2@campus.local")
    ticket = create_ticket(client, owner)

    response = client.get(f"/tickets/{ticket['id']}", headers=auth(other))
    assert response.status_code == 404


def test_client_cannot_choose_ticket_author(client: TestClient) -> None:
    owner = login(client, "user1@campus.local")
    response = client.post(
        "/tickets",
        headers=auth(owner),
        json={
            "title": "Подмена автора",
            "description": "Клиент не должен задавать author_id",
            "author_id": 2,
        },
    )
    assert response.status_code == 422


def test_internal_notes_are_not_exposed_to_user(client: TestClient) -> None:
    user = login(client, "user1@campus.local")
    specialist = login(client, "specialist@campus.local")
    ticket = create_ticket(client, user)
    ticket_id = ticket["id"]

    assert client.post(f"/tickets/{ticket_id}/accept", headers=auth(specialist)).status_code == 200
    note = client.post(
        f"/tickets/{ticket_id}/internal-notes",
        headers=auth(specialist),
        json={"body": "Проверить кабель HDMI"},
    )
    assert note.status_code == 201

    public_view = client.get(f"/tickets/{ticket_id}", headers=auth(user))
    assert public_view.status_code == 200
    assert "Проверить кабель HDMI" not in public_view.text
    assert client.get(
        f"/tickets/{ticket_id}/internal-notes", headers=auth(user)
    ).status_code == 403


def test_only_specialist_can_accept_and_close_ticket(client: TestClient) -> None:
    user = login(client, "user1@campus.local")
    specialist = login(client, "specialist@campus.local")
    ticket = create_ticket(client, user)
    ticket_id = ticket["id"]

    assert client.post(f"/tickets/{ticket_id}/accept", headers=auth(user)).status_code == 403
    accepted = client.post(f"/tickets/{ticket_id}/accept", headers=auth(specialist))
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "in_progress"

    closed = client.post(
        f"/tickets/{ticket_id}/close",
        headers=auth(specialist),
        json={"resolution": "Кабель заменён"},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"


def test_owner_can_reopen_closed_ticket(client: TestClient) -> None:
    user = login(client, "user1@campus.local")
    specialist = login(client, "specialist@campus.local")
    ticket_id = create_ticket(client, user)["id"]
    client.post(f"/tickets/{ticket_id}/accept", headers=auth(specialist))
    client.post(
        f"/tickets/{ticket_id}/close",
        headers=auth(specialist),
        json={"resolution": "Исправлено"},
    )

    reopened = client.post(
        f"/tickets/{ticket_id}/reopen",
        headers=auth(user),
        json={"body": "Проблема повторилась"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "reopened"
    assert reopened.json()["assignee_id"] is None
    assert reopened.json()["messages"][-1]["body"] == "Проблема повторилась"
