import bcrypt
import streamlit as st

def _check_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def require_login():
    if st.session_state.get("authed", False):
        return True

    st.title("Unit Plan Reviewer — Login")
    pw = st.text_input("Password", type="password")

    if st.button("Enter"):
        hashed = st.secrets.get("APP_PASSWORD_HASH", "")
        if not hashed:
            st.error("Missing APP_PASSWORD_HASH in secrets.")
            st.stop()

        if _check_password(pw, hashed):
            st.session_state["authed"] = True
            st.success("Logged in.")
            st.rerun()
        else:
            st.error("Incorrect password.")

    st.stop()
