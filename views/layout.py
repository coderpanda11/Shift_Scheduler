"""Application header banner with logo placeholder."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).parent.parent / "assets"
LOGO_PATH = ASSETS / "logo.png"


def render_app_header(subtitle: str = "Dynamic Shift Scheduling & Duty Roster") -> None:
    """Top banner with logo slot and title."""
    logo_html = '<div class="logo-placeholder">LOGO</div>'
    if LOGO_PATH.exists():
        import base64

        b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode()
        logo_html = f'<img src="data:image/png;base64,{b64}" class="logo-img" alt="Logo"/>'

    st.markdown(
        f"""
        <div class="app-banner">
            <div class="logo-slot">{logo_html}</div>
            <div class="banner-text">
                <h1>Duty Roster Management System</h1>
                <p>{subtitle}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def inject_global_css() -> None:
    st.markdown(
        """
        <style>
        .app-banner, .login-banner {
            display: flex;
            align-items: center;
            gap: 1.25rem;
            background: linear-gradient(90deg, #1e3a8a 0%, #2563eb 100%);
            color: #fff;
            padding: 0.85rem 1.25rem;
            border-radius: 0.5rem;
            margin-bottom: 1rem;
        }
        .login-banner { max-width: 520px; margin: 2rem auto 1.5rem auto; }
        .logo-slot {
            min-width: 88px;
            width: 88px;
            height: 88px;
            background: rgba(255,255,255,0.15);
            border: 2px dashed rgba(255,255,255,0.45);
            border-radius: 0.5rem;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }
        .logo-placeholder { font-size: 0.75rem; font-weight: 600; opacity: 0.85; }
        .logo-img { max-width: 80px; max-height: 80px; object-fit: contain; }
        .banner-text h1, .login-banner h2 {
            margin: 0;
            font-size: 1.35rem;
            font-weight: 700;
            color: #fff;
        }
        .banner-text p, .login-banner p {
            margin: 0.15rem 0 0 0;
            font-size: 0.9rem;
            opacity: 0.9;
        }
        [data-testid="stSidebar"] .sidebar-user {
            font-size: 0.85rem;
            color: #475569;
            margin-bottom: 0.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
