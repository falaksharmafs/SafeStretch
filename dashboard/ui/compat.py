"""Streamlit renamed use_container_width -> width='stretch'. Try the old one first, fall back to the new one."""
import streamlit as st


def stretch(fn, *args, **kwargs):
    try:
        return fn(*args, use_container_width=True, **kwargs)
    except TypeError:
        return fn(*args, width="stretch", **kwargs)


def is_dark() -> bool:
    """Follow Streamlit's active theme (switch it in the top-right menu > Settings > Theme)."""
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return (st.get_option("theme.base") or "dark") == "dark"
