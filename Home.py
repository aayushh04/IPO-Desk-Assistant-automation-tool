"""Entry point: page setup and top navigation. Run with `streamlit run Home.py`.

Each module lives in views/ (layout only); all logic is in the ipodesk/ package.
"""
import streamlit as st

from ui_common import apply_theme

st.set_page_config(page_title="IPO Desk Assistant", page_icon=":material/fact_check:", layout="wide",
                   initial_sidebar_state="collapsed")
apply_theme()
st.logo("static/logo.svg", size="medium")

nav = st.navigation(
    [
        st.Page("views/overview.py", title="Overview", icon=":material/space_dashboard:", default=True),
        st.Page("views/note_generator.py", title="Note Generator", icon=":material/fact_check:"),
        st.Page("views/ipo_calendar.py", title="IPO Calendar", icon=":material/calendar_month:"),
        st.Page("views/subscription_tracker.py", title="Subscription Tracker", icon=":material/monitoring:"),
    ],
    position="top",
)
nav.run()
