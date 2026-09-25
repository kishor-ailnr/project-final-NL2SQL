"""Comprehensive test suite for multi-conversation support (ChatGPT-style New Chat + history)."""

import sys
from pathlib import Path
from starlette.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app
from app.routers.query import reset_rate_limits
from app.services.sql_generator import clear_query_cache

client = TestClient(app)


def test_conversations_flow():
    print("=" * 80)
    print("        TESTING MULTI-CONVERSATION SUPPORT (NEW CHAT + HISTORY)")
    print("=" * 80)

    reset_rate_limits()
    clear_query_cache()

    # Step 0: Connect to demo hospital database
    conn_resp = client.post("/api/connect-db", json={"db_type": "demo", "demo_name": "hospital"})
    assert conn_resp.status_code == 200, f"Connect failed: {conn_resp.text}"
    session_id = conn_resp.json()["session_id"]
    print(f"[0] Connected to demo hospital DB. Session ID: {session_id}\n")

    # Step 1: Create Conversation 1 (POST /api/conversations/new)
    print("--- [1] Creating Conversation 1 ---")
    c1_resp = client.post("/api/conversations/new", json={"session_id": session_id})
    assert c1_resp.status_code == 200, f"Create conv 1 failed: {c1_resp.text}"
    c1_data = c1_resp.json()
    conv1_id = c1_data["conversation_id"]
    print(f"Created Conversation 1 ID: {conv1_id}, created_at: {c1_data['created_at']}")
    assert conv1_id and isinstance(conv1_id, str), "Invalid conversation_id"

    # Step 2: Query 1 in Conversation 1 (Patients older than 40)
    print("\n--- [2] Asking question 1 in Conversation 1 ---")
    q1_resp = client.post("/api/query", json={
        "session_id": session_id,
        "conversation_id": conv1_id,
        "text": "list all patients older than 40",
        "language": "auto"
    })
    assert q1_resp.status_code == 200, f"Query 1 failed: {q1_resp.text}"
    q1_data = q1_resp.json()
    print(f"Query 1 SQL: {q1_data.get('sql')}")
    print(f"Query 1 Rows: {len(q1_data.get('result', []))}")
    assert "patients" in q1_data.get("sql", "").lower()

    # Step 3: Check that Conversation 1 title was auto-generated
    print("\n--- [3] Listing conversations (checking title auto-generation) ---")
    list_resp1 = client.get(f"/api/conversations?session_id={session_id}")
    assert list_resp1.status_code == 200, f"List convs failed: {list_resp1.text}"
    convs1 = list_resp1.json()["conversations"]
    print(f"Current Conversations Count: {len(convs1)}")
    conv1_item = next(c for c in convs1 if c["conversation_id"] == conv1_id)
    print(f"Conversation 1 Title: '{conv1_item['title']}'")
    assert conv1_item["title"] != "New Chat", "Title should have been auto-generated from question"

    # Step 4: Create Conversation 2 (POST /api/conversations/new)
    print("\n--- [4] Creating Conversation 2 ---")
    c2_resp = client.post("/api/conversations/new", json={"session_id": session_id})
    assert c2_resp.status_code == 200
    conv2_id = c2_resp.json()["conversation_id"]
    print(f"Created Conversation 2 ID: {conv2_id}")
    assert conv2_id != conv1_id, "Conversation IDs must be distinct"

    # Step 5: Query in Conversation 2 (Doctors list)
    print("\n--- [5] Asking question in Conversation 2 ---")
    q2_resp = client.post("/api/query", json={
        "session_id": session_id,
        "conversation_id": conv2_id,
        "text": "list all doctors",
        "language": "auto"
    })
    assert q2_resp.status_code == 200
    q2_data = q2_resp.json()
    print(f"Query 2 SQL: {q2_data.get('sql')}")
    print(f"Query 2 Rows: {len(q2_data.get('result', []))}")
    assert "doctors" in q2_data.get("sql", "").lower()

    # Step 6: Verify GET /api/conversations lists both, most recent first
    print("\n--- [6] Verifying GET /api/conversations ordering ---")
    list_resp2 = client.get(f"/api/conversations?session_id={session_id}")
    assert list_resp2.status_code == 200
    convs2 = list_resp2.json()["conversations"]
    print(f"Total Conversations: {len(convs2)}")
    for i, c in enumerate(convs2):
        print(f"  #{i+1}: {c['conversation_id']} - '{c['title']}' ({c['created_at']})")
    assert convs2[0]["conversation_id"] == conv2_id, "Most recent conversation should be first"

    # Step 7: Verify messages separation via GET /api/conversations/{id}/messages
    print("\n--- [7] Verifying message history reload for Conversation 1 ---")
    m1_resp = client.get(f"/api/conversations/{conv1_id}/messages")
    assert m1_resp.status_code == 200
    m1_data = m1_resp.json()["messages"]
    print(f"Conversation 1 Message Count: {len(m1_data)}")
    assert len(m1_data) == 1
    assert "patients" in m1_data[0]["nl_query"].lower()
    assert "patients" in m1_data[0]["sql"].lower()
    assert len(m1_data[0]["result"]) > 0
    assert m1_data[0]["timestamp"]

    print("\n--- [8] Verifying message history reload for Conversation 2 ---")
    m2_resp = client.get(f"/api/conversations/{conv2_id}/messages")
    assert m2_resp.status_code == 200
    m2_data = m2_resp.json()["messages"]
    print(f"Conversation 2 Message Count: {len(m2_data)}")
    assert len(m2_data) == 1
    assert "doctors" in m2_data[0]["nl_query"].lower()
    assert "doctors" in m2_data[0]["sql"].lower()
    assert len(m2_data[0]["result"]) > 0

    # Step 8: Continuing Conversation 1 (switching back and asking another question)
    print("\n--- [9] Continuing Conversation 1 (switching back and asking question 2) ---")
    q3_resp = client.post("/api/query", json={
        "session_id": session_id,
        "conversation_id": conv1_id,
        "text": "how many total patients are there?",
        "language": "auto"
    })
    assert q3_resp.status_code == 200
    q3_data = q3_resp.json()
    print(f"Query 3 SQL: {q3_data.get('sql')}")

    # Re-fetch messages for Conversation 1 and Conversation 2 to confirm history preservation
    m1_updated = client.get(f"/api/conversations/{conv1_id}/messages").json()["messages"]
    m2_check = client.get(f"/api/conversations/{conv2_id}/messages").json()["messages"]
    print(f"Conversation 1 now has {len(m1_updated)} messages (expected 2)")
    print(f"Conversation 2 still has {len(m2_check)} messages (expected 1)")
    assert len(m1_updated) == 2, "Conversation 1 should have 2 queries now"
    assert len(m2_check) == 1, "Conversation 2 should remain isolated with 1 query"

    # Step 9: Regression check - Clarification Layer within a conversation
    print("\n--- [10] Regression check: Clarification layer ---")
    clarif_resp = client.post("/api/query", json={
        "session_id": session_id,
        "conversation_id": conv1_id,
        "text": "give me the top patients",
        "language": "auto"
    })
    assert clarif_resp.status_code == 200
    clarif_data = clarif_resp.json()
    assert clarif_data["needs_clarification"] is True
    print(f"Needs Clarification: {clarif_data['needs_clarification']}")
    print(f"Clarification Question: '{clarif_data['clarification_question']}'")

    # Step 10: Regression check - Voice Transcript Correction within a conversation
    print("\n--- [11] Regression check: Voice transcript correction ---")
    voice_resp = client.post("/api/query", json={
        "session_id": session_id,
        "conversation_id": conv2_id,
        "text": "shom me pashents older then fourty",
        "language": "auto"
    })
    assert voice_resp.status_code == 200
    voice_data = voice_resp.json()
    print(f"Interpreted text: '{voice_data.get('interpreted_text')}'")
    assert "patients" in voice_data.get("interpreted_text", "").lower()

    print("\n" + "=" * 80)
    print("ALL MULTI-CONVERSATION & REGRESSION TESTS PASSED PERFECTLY!")
    print("=" * 80)


if __name__ == "__main__":
    test_conversations_flow()
