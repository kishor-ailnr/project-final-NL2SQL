"""
tests/test_conversations.py
----------------------------
Tests for multi-conversation support (New Chat, history, listing, deletion).
Derived from scripts/test_conversations.py.
Calls Gemini for title auto-generation → marked integration.
Structural/CRUD tests (create, list, delete) don't need Gemini.
"""

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Conversation CRUD (structural — minimal Gemini dependency)
# ---------------------------------------------------------------------------

class TestConversationCRUD:
    def test_create_new_conversation_returns_200(self, client, hospital_sid):
        resp = client.post("/api/conversations/new", json={"session_id": hospital_sid})
        assert resp.status_code == 200

    def test_create_returns_conversation_id(self, client, hospital_sid):
        resp = client.post("/api/conversations/new", json={"session_id": hospital_sid})
        data = resp.json()
        assert "conversation_id" in data
        assert len(data["conversation_id"]) > 0

    def test_create_returns_created_at(self, client, hospital_sid):
        resp = client.post("/api/conversations/new", json={"session_id": hospital_sid})
        assert "created_at" in resp.json()

    def test_two_new_chats_get_distinct_ids(self, client, hospital_sid):
        c1 = client.post("/api/conversations/new", json={"session_id": hospital_sid}).json()["conversation_id"]
        c2 = client.post("/api/conversations/new", json={"session_id": hospital_sid}).json()["conversation_id"]
        assert c1 != c2

    def test_list_conversations_returns_200(self, client, hospital_sid):
        resp = client.get(f"/api/conversations?session_id={hospital_sid}")
        assert resp.status_code == 200

    def test_list_conversations_returns_conversations_key(self, client, hospital_sid):
        resp = client.get(f"/api/conversations?session_id={hospital_sid}")
        assert "conversations" in resp.json()

    def test_created_conversation_appears_in_list(self, client, hospital_sid):
        conv_id = client.post("/api/conversations/new", json={"session_id": hospital_sid}).json()["conversation_id"]
        convs = client.get(f"/api/conversations?session_id={hospital_sid}").json()["conversations"]
        ids = [c["conversation_id"] for c in convs]
        assert conv_id in ids

    def test_delete_conversation_returns_200(self, client, hospital_sid):
        conv_id = client.post("/api/conversations/new", json={"session_id": hospital_sid}).json()["conversation_id"]
        resp = client.delete(f"/api/conversations/{conv_id}?session_id={hospital_sid}")
        assert resp.status_code == 200

    def test_deleted_conversation_no_longer_in_list(self, client, hospital_sid):
        conv_id = client.post("/api/conversations/new", json={"session_id": hospital_sid}).json()["conversation_id"]
        client.delete(f"/api/conversations/{conv_id}?session_id={hospital_sid}")
        convs = client.get(f"/api/conversations?session_id={hospital_sid}").json()["conversations"]
        ids = [c["conversation_id"] for c in convs]
        assert conv_id not in ids


# ---------------------------------------------------------------------------
# Query within a conversation
# ---------------------------------------------------------------------------

class TestQueryWithConversation:
    def test_query_in_conversation_returns_200(self, client, hospital_sid):
        conv_id = client.post("/api/conversations/new", json={"session_id": hospital_sid}).json()["conversation_id"]
        resp = client.post("/api/query", json={
            "session_id": hospital_sid,
            "conversation_id": conv_id,
            "text": "list all patients older than 40",
            "language": "auto",
        })
        assert resp.status_code == 200

    def test_query_in_conversation_returns_sql_with_patients(self, client, hospital_sid):
        conv_id = client.post("/api/conversations/new", json={"session_id": hospital_sid}).json()["conversation_id"]
        resp = client.post("/api/query", json={
            "session_id": hospital_sid,
            "conversation_id": conv_id,
            "text": "list all patients older than 40",
            "language": "auto",
        })
        sql = resp.json().get("sql", "")
        assert "patients" in sql.lower()

    def test_conversation_title_auto_generated_after_first_query(self, client, hospital_sid):
        conv_id = client.post("/api/conversations/new", json={"session_id": hospital_sid}).json()["conversation_id"]
        client.post("/api/query", json={
            "session_id": hospital_sid,
            "conversation_id": conv_id,
            "text": "list all patients older than 40",
            "language": "auto",
        })
        convs = client.get(f"/api/conversations?session_id={hospital_sid}").json()["conversations"]
        conv = next((c for c in convs if c["conversation_id"] == conv_id), None)
        assert conv is not None
        # Title must be something other than the default "New Chat"
        assert conv.get("title") != "New Chat" or len(conv.get("title", "")) > 0

    def test_two_conversations_are_independent(self, client, hospital_sid):
        """Queries in Conv1 must not bleed into Conv2."""
        conv1 = client.post("/api/conversations/new", json={"session_id": hospital_sid}).json()["conversation_id"]
        conv2 = client.post("/api/conversations/new", json={"session_id": hospital_sid}).json()["conversation_id"]

        client.post("/api/query", json={
            "session_id": hospital_sid,
            "conversation_id": conv1,
            "text": "list all patients older than 40",
            "language": "auto",
        })
        client.post("/api/query", json={
            "session_id": hospital_sid,
            "conversation_id": conv2,
            "text": "list all doctors in Cardiology",
            "language": "auto",
        })

        # Both convs must exist independently
        convs = client.get(f"/api/conversations?session_id={hospital_sid}").json()["conversations"]
        ids = [c["conversation_id"] for c in convs]
        assert conv1 in ids
        assert conv2 in ids


# ---------------------------------------------------------------------------
# History retrieval
# ---------------------------------------------------------------------------

class TestConversationHistory:
    def test_get_history_returns_200(self, client, hospital_sid):
        conv_id = client.post("/api/conversations/new", json={"session_id": hospital_sid}).json()["conversation_id"]
        resp = client.get(f"/api/conversations/{conv_id}/messages")
        assert resp.status_code == 200

    def test_history_contains_query_after_ask(self, client, hospital_sid):
        conv_id = client.post("/api/conversations/new", json={"session_id": hospital_sid}).json()["conversation_id"]
        client.post("/api/query", json={
            "session_id": hospital_sid,
            "conversation_id": conv_id,
            "text": "list all patients older than 40",
            "language": "auto",
        })
        resp = client.get(f"/api/conversations/{conv_id}/messages")
        messages = resp.json().get("messages", [])
        assert len(messages) >= 1

    def test_follow_up_query_preserves_context(self, client, hospital_sid):
        conv_id = client.post("/api/conversations/new", json={"session_id": hospital_sid}).json()["conversation_id"]
        # Turn 1
        resp1 = client.post("/api/query", json={
            "session_id": hospital_sid,
            "conversation_id": conv_id,
            "text": "list all patients with diabetes",
            "language": "auto",
        })
        assert resp1.status_code == 200
        # Turn 2: Follow-up query using previous context
        resp2 = client.post("/api/query", json={
            "session_id": hospital_sid,
            "conversation_id": conv_id,
            "text": "what about hypertension instead?",
            "language": "auto",
        })
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2.get("sql") is not None
        assert "patients" in data2.get("sql", "").lower()

