import streamlit as st

def require_login():
    if st.session_state.get("authed", False):
        return True

    st.title("Unit Plan Reviewer — Login")

    pw = st.text_input("Password", type="password")

    if st.button("Enter"):
        expected = st.secrets.get("APP_PASSWORD", "")
        if not expected:
            st.error("Missing APP_PASSWORD in secrets.")
            st.stop()

        if pw == expected:
            st.session_state["authed"] = True
            st.success("Logged in.")
            st.rerun()
        else:
            st.error("Incorrect password.")

    st.stop()
