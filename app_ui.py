"""
Streamlit UI — BIXSO Agentic Educator
Run with: streamlit run app_ui.py

Requires the FastAPI backend running at:
    uvicorn app.main:app --port 8000
"""


import requests
import streamlit as st
import time
import os 

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
SAMPLE_USERS = {
    "Alice (user_id=1) · 250 tokens · Premium": 1,
    "Bob   (user_id=2) · 50 tokens  · Basic":   2,
    "Carol (user_id=3) · 0 tokens   · Free":    3,
}
# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="BIXSO Agentic Educator",
    page_icon="🎓",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

if "debug_log" not in st.session_state:
    st.session_state.debug_log = []

# ---------------------------------------------------------------------------
# Backend helpers
# ---------------------------------------------------------------------------

def api_health():
    start = time.time()
    try:
        r = requests.get(f"{API_BASE}/health", timeout=2)
        latency = int((time.time() - start) * 1000)
        return r.status_code == 200, latency
    except Exception:
        return False, None


def send_message(user_id: int, message: str):
    r = requests.post(
        f"{API_BASE}/chat",
        json={"user_id": user_id, "message": message},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def upload_file(user_id: int, uploaded_file):
    files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
    data = {"user_id": user_id}

    r = requests.post(
        f"{API_BASE}/documents/upload-file",
        files=files,
        data=data,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 🎓 BIXSO Admin Panel")

    # -----------------------------------------------------------------------
    # API Health
    # -----------------------------------------------------------------------
    ok, latency = api_health()

    st.markdown("### API Health")

    if ok:
        st.success(f"Online · {latency} ms")
    else:
        st.error("Offline")

    if st.button("Refresh health"):
        st.rerun()

    st.divider()

    # -----------------------------------------------------------------------
    # User selection
    # -----------------------------------------------------------------------
    st.markdown("### Select User")

    st.markdown("### Select User")

    selected_label = st.selectbox(
        "User",
        list(SAMPLE_USERS.keys()),
    )

    user_id = SAMPLE_USERS[selected_label]
    st.divider()

    # -----------------------------------------------------------------------
    # Quick Action Buttons
    # -----------------------------------------------------------------------
    st.markdown("###  Quick Queries")

    if st.button("Show the balance"):
        st.session_state.inject = "How many tokens do I have left?"

    if st.button("Show the last transaction"):
        st.session_state.inject = "What is my last transaction?"

    if st.button("Show all transactions"):
        st.session_state.inject = "Show all my transactions."

    if st.button("Show current courses"):
        st.session_state.inject = "Which courses am I enrolled in?"

    if st.button("Show the user profile"):
        st.session_state.inject = "Show my user profile."

    st.divider()

    # -----------------------------------------------------------------------
    # File Upload
    # -----------------------------------------------------------------------
    st.markdown("### Upload document")

    uploaded_file = st.file_uploader("Choose file")

    if uploaded_file and st.button("Upload"):
        with st.spinner("Uploading..."):
            try:
                res = upload_file(user_id, uploaded_file)
                st.success(f"Ingested · id={res['document_id']}")
                st.session_state.debug_log.append(res)
            except Exception as e:
                st.error(str(e))

    st.divider()

    # -----------------------------------------------------------------------
    # Debug Console
    # -----------------------------------------------------------------------
    st.markdown("### Debug Console")

    if st.button("Clear debug"):
        st.session_state.debug_log = []

    st.code(st.session_state.debug_log, language="json")

# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------

st.markdown("## Chat")

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------

prompt = st.chat_input("Ask something...")

# injected button prompts
if "inject" in st.session_state:
    prompt = st.session_state.inject
    del st.session_state.inject

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                data = send_message(user_id, prompt)

                response = data["response"]

                # log debug
                st.session_state.debug_log.append(data)

            except Exception as e:
                response = str(e)

        st.markdown(response)

    st.session_state.messages.append(
        {"role": "assistant", "content": response}
    )