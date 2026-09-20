# -*- coding: utf-8 -*-
"""Username/password login backed by Supabase Auth. No public sign-up route
anywhere in this app -- the only way a new account gets created is through
the admin panel, by someone already logged in as admin, using Supabase's
Admin API (service-role key, never exposed to the browser).

Unlike the earlier local-file version, sessions here are tied to Supabase
tokens kept in st.session_state (per-browser-session, safe for multiple
people using the app at the same time on Streamlit Community Cloud).
"""
import streamlit as st

import supabase_client as sb


def require_login():
    """Call this as the very first thing in app.py. Renders a login form
    and halts the rest of the script (via st.stop()) until the person is
    authenticated."""
    if not sb.is_configured():
        st.error(
            "La app no tiene configurada la conexión a Supabase todavía. "
            "Agrega SUPABASE_URL, SUPABASE_ANON_KEY y SUPABASE_SERVICE_ROLE_KEY "
            "en Settings → Secrets de Streamlit Cloud."
        )
        st.stop()

    if st.session_state.get("auth_user"):
        return st.session_state["auth_user"]

    st.title("🔒 Iniciar sesión")
    with st.form("login_form"):
        email = st.text_input("Correo")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Entrar", type="primary")

    if submitted:
        ok, role_or_error, tokens = sb.sign_in(email.strip(), password)
        if ok:
            st.session_state["auth_user"] = email.strip()
            st.session_state["auth_role"] = role_or_error
            st.session_state["auth_tokens"] = tokens
            st.rerun()
        else:
            st.error("Correo o contraseña incorrectos.")

    st.caption(
        "¿No tienes cuenta? Pídele al administrador que te cree una desde el panel "
        "'Administrar usuarios' -- aquí no hay registro abierto."
    )
    st.stop()


def logout_button():
    with st.sidebar:
        st.caption(f"Sesión: **{st.session_state.get('auth_user')}**"
                    f"{' (admin)' if is_admin() else ''}")
        if st.button("Cerrar sesión"):
            for k in ("auth_user", "auth_role", "auth_tokens"):
                st.session_state.pop(k, None)
            st.rerun()


def is_admin():
    return st.session_state.get("auth_role") == "admin"


def render_admin_panel():
    """A full page for managing accounts. Only ever reached because app.py
    only shows this option in the menu when is_admin() is True -- but we
    double-check here too, in case someone messes with session state."""
    if not is_admin():
        st.error("Esta sección es solo para administradores.")
        return

    st.header("Administrar usuarios")

    try:
        users = sb.admin_list_users()
    except Exception as e:
        st.error(f"No se pudo conectar con Supabase para leer los usuarios: {e}")
        return

    st.subheader("Usuarios actuales")
    for u in users:
        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
        col1.write(f"**{u['email']}**")
        col2.write(u["role"])
        col3.caption(f"desde {u['created_at']}")
        if u["email"] != st.session_state["auth_user"]:
            if col4.button("Eliminar", key=f"del_{u['id']}"):
                sb.admin_delete_user(u["id"])
                st.rerun()
        else:
            col4.caption("(tú)")

    st.divider()
    st.subheader("Crear nuevo usuario")
    with st.form("new_user_form", clear_on_submit=True):
        new_email = st.text_input("Correo del nuevo usuario")
        new_pass = st.text_input("Contraseña temporal")
        new_role = st.selectbox("Rol", ["usuario", "admin"])
        create = st.form_submit_button("Crear usuario", type="primary")
    if create:
        if not new_email.strip() or not new_pass:
            st.error("Completa correo y contraseña.")
        else:
            try:
                sb.admin_create_user(new_email.strip(), new_pass, new_role)
                st.success(f"Usuario **{new_email}** creado. Pásale su correo y esta "
                           f"contraseña temporal para que la cambie en su primer ingreso.")
            except Exception as e:
                st.error(f"No se pudo crear el usuario: {e}")

    st.divider()
    st.subheader("Cambiar mi contraseña")
    with st.form("change_pw_form", clear_on_submit=True):
        new_pw = st.text_input("Nueva contraseña", type="password")
        new_pw2 = st.text_input("Repite la nueva contraseña", type="password")
        change = st.form_submit_button("Cambiar contraseña", type="primary")
    if change:
        if not new_pw:
            st.error("Escribe una nueva contraseña.")
        elif new_pw != new_pw2:
            st.error("Las dos contraseñas nuevas no coinciden.")
        else:
            try:
                sb.change_own_password(st.session_state["auth_tokens"], new_pw)
                st.success("Contraseña actualizada.")
            except Exception as e:
                st.error(f"No se pudo cambiar la contraseña: {e}")
