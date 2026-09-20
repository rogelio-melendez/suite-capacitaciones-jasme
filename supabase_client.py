# -*- coding: utf-8 -*-
"""All communication with Supabase: authentication (login + admin-only user
management, no public sign-up anywhere) and persistent storage for exam
configs (replaces the old local config/*.json files, which would not
survive Streamlit Community Cloud restarting the app).

Two different Supabase keys are used, on purpose:
  - SUPABASE_ANON_KEY: safe for regular sign-in (respects Row Level Security).
  - SUPABASE_SERVICE_ROLE_KEY: full admin power (create/delete users,
    bypass RLS). Only ever used inside render_admin_panel(), which itself
    is only reachable by someone already authenticated as admin. This key
    lives in Streamlit's secrets manager and is never sent to the browser
    (Streamlit apps execute their Python server-side).

IMPORTANT concurrency note: Streamlit's @st.cache_resource is shared across
EVERY visitor's session on the server, not per-browser-tab. A client object
that holds a signed-in user's session must therefore never be cached like
that -- two people logged in at once would silently share (and overwrite)
each other's session. Only the token-less admin client (authenticated by
the service-role API key itself, not a user session) is safe to cache and
share. Every per-user action creates a fresh client and re-attaches that
person's own tokens (kept in their own st.session_state) before use.
"""
import streamlit as st
from supabase import create_client


def _fresh_client():
    """A brand-new, uncached client -- safe to attach one person's session to."""
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])


@st.cache_resource
def _admin_client():
    """Cached and shared on purpose: authenticated by the service-role key
    itself, not tied to any individual person's login session."""
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_ROLE_KEY"])


def is_configured():
    try:
        return bool(st.secrets["SUPABASE_URL"]) and bool(st.secrets["SUPABASE_ANON_KEY"])
    except Exception:
        return False


# =====================================================================
# Auth
# =====================================================================

def sign_in(email: str, password: str):
    """Returns (success, role_or_error_message, tokens_dict_or_None).
    The caller (auth.py) stores tokens_dict in st.session_state -- that is
    what makes the session belong to this one browser session and no one
    else's."""
    try:
        client = _fresh_client()
        result = client.auth.sign_in_with_password({"email": email, "password": password})
        role = (result.user.user_metadata or {}).get("role", "usuario")
        tokens = {
            "access_token": result.session.access_token,
            "refresh_token": result.session.refresh_token,
        }
        return True, role, tokens
    except Exception as e:
        return False, str(e), None


def _client_for_session(tokens: dict):
    client = _fresh_client()
    client.auth.set_session(tokens["access_token"], tokens["refresh_token"])
    return client


def admin_create_user(email: str, password: str, role: str = "usuario"):
    client = _admin_client()
    client.auth.admin.create_user({
        "email": email,
        "password": password,
        "email_confirm": True,  # pre-confirmed -- no verification email, no self-serve step
        "user_metadata": {"role": role},
    })


def admin_list_users():
    client = _admin_client()
    response = client.auth.admin.list_users()
    users = []
    for u in response:
        users.append({
            "id": u.id,
            "email": u.email,
            "role": (u.user_metadata or {}).get("role", "usuario"),
            "created_at": str(u.created_at)[:10] if u.created_at else "",
        })
    return users


def admin_delete_user(user_id: str):
    client = _admin_client()
    client.auth.admin.delete_user(user_id)


def admin_set_role(user_id: str, role: str):
    client = _admin_client()
    client.auth.admin.update_user_by_id(user_id, {"user_metadata": {"role": role}})


def change_own_password(tokens: dict, new_password: str):
    """The logged-in user changes their own password, using THEIR OWN
    tokens (from st.session_state) attached to a fresh, throwaway client --
    never the shared admin client, never a shared cached user client."""
    client = _client_for_session(tokens)
    client.auth.update_user({"password": new_password})


# =====================================================================
# Exam configs (replaces config/*.json)
# =====================================================================

def list_exam_configs():
    client = _admin_client()
    result = client.table("exam_configs").select("*").order("title").execute()
    return {row["title"]: row for row in result.data}


def save_exam_config(config: dict):
    """config keys: nom_id, title, approve_operator, approve_threshold,
    questions (list[str]), options (list[dict]), answer_key (list[str])."""
    client = _admin_client()
    client.table("exam_configs").upsert(config, on_conflict="nom_id").execute()


def delete_exam_config(nom_id: str):
    client = _admin_client()
    client.table("exam_configs").delete().eq("nom_id", nom_id).execute()
