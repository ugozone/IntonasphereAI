import base64
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


LOGO_PATH = "assets/jamispeak_logo.png"


def image_to_base64(path: str) -> str:
    image_path = Path(path)
    if not image_path.exists():
        return ""

    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def load_global_css(css_path: str = "styles.css"):
    """
    Load only general Streamlit styling.
    Navbar/hero styling is loaded inside components.html to prevent raw HTML display.
    """
    try:
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()

        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

    except FileNotFoundError:
        st.warning(f"CSS file not found: {css_path}")



def render_mobile_responsive_navbar():
    """
    Native Streamlit navbar.

    This avoids HTML overlay problems that can block buttons.
    Mobile-friendly logic:
    - Logo remains on the left.
    - Hamburger/popover menu is on the right.
    - No floating HTML layer blocks the app.
    """
    logo_path = Path(LOGO_PATH)

    st.markdown(
        """
        <div class="native-navbar-shell">
        """,
        unsafe_allow_html=True,
    )

    left, middle, right = st.columns([0.18, 0.62, 0.20], vertical_alignment="center")

    with left:
        if logo_path.exists():
            st.image(str(logo_path), width=58)
        else:
            st.markdown(
                """
                <div class="nav-logo-fallback">IS</div>
                """,
                unsafe_allow_html=True,
            )

    with middle:
        st.markdown(
            """
            <div class="native-brand-text">
                <div class="native-brand-name">IntonaSphere AI</div>
                <div class="native-brand-subtitle">Global Speech Intelligence</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        with st.popover("☰", use_container_width=True):
            st.markdown("### Navigate")
            st.markdown("[Input](#input)")
            st.markdown("[Transcription](#transcription)")
            st.markdown("[Phonetics](#phonetics)")
            st.markdown("[Prosody](#prosody)")
            st.markdown("[Exports](#exports)")

    st.markdown(
        """
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_global_hero():
    """
    Hero rendered inside HTML component to prevent raw-code display.
    """
    logo_base64 = image_to_base64(LOGO_PATH)

    if logo_base64:
        hero_logo = f'<img src="data:image/png;base64,{logo_base64}" class="hero-logo-img" alt="IntonaSphere AI Logo">'
    else:
        hero_logo = '<div class="hero-logo-fallback">IS</div>'

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            * {{
                box-sizing: border-box;
            }}

            body {{
                margin: 0;
                padding: 0;
                font-family: Inter, Helvetica, Arial, sans-serif;
                background: transparent;
            }}

            .global-hero {{
                background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 52%, #8b5e34 100%);
                color: #ffffff;
                padding: 3.2rem 3rem;
                border-radius: 30px;
                box-shadow: 0 24px 70px rgba(15, 23, 42, 0.23);
                position: relative;
                overflow: hidden;
            }}

            .global-hero::after {{
                content: "";
                position: absolute;
                width: 420px;
                height: 420px;
                right: -160px;
                top: -160px;
                background: rgba(255, 255, 255, 0.11);
                border-radius: 50%;
            }}

            .hero-content-grid {{
                display: grid;
                grid-template-columns: 1.45fr 0.75fr;
                gap: 2rem;
                align-items: center;
                position: relative;
                z-index: 2;
            }}

            .hero-badge {{
                display: inline-block;
                background: rgba(255, 255, 255, 0.14);
                border: 1px solid rgba(255, 255, 255, 0.28);
                padding: 0.45rem 0.85rem;
                border-radius: 999px;
                font-size: 0.82rem;
                letter-spacing: 0.03em;
                text-transform: uppercase;
                margin-bottom: 1rem;
            }}

            .hero-title {{
                font-size: clamp(2rem, 4vw, 4.1rem);
                line-height: 1.05;
                font-weight: 900;
                max-width: 930px;
                margin: 0 0 1rem 0;
                letter-spacing: -0.055em;
            }}

            .hero-subtitle {{
                font-size: 1.1rem;
                line-height: 1.7;
                max-width: 860px;
                color: rgba(255, 255, 255, 0.9);
                margin-bottom: 1.5rem;
            }}

            .hero-tags {{
                display: flex;
                flex-wrap: wrap;
                gap: 0.65rem;
                margin-top: 1.5rem;
            }}

            .hero-tag {{
                background: rgba(255, 255, 255, 0.13);
                border: 1px solid rgba(255, 255, 255, 0.22);
                border-radius: 999px;
                padding: 0.55rem 0.9rem;
                color: #ffffff;
                font-size: 0.9rem;
            }}

            .hero-logo-block {{
                display: flex;
                justify-content: center;
                align-items: center;
            }}

            .hero-logo-img {{
                width: min(330px, 100%);
                border-radius: 30px;
                box-shadow: 0 30px 80px rgba(0, 0, 0, 0.28);
            }}

            .hero-logo-fallback {{
                width: 220px;
                height: 220px;
                border-radius: 50%;
                background: linear-gradient(135deg, #1e3a5f, #8b5e34);
                color: #ffffff;
                font-size: 4rem;
                font-weight: 900;
                display: flex;
                align-items: center;
                justify-content: center;
            }}

            @media (max-width: 900px) {{
                .global-hero {{
                    padding: 2.3rem 1.45rem;
                    border-radius: 24px;
                }}

                .hero-content-grid {{
                    grid-template-columns: 1fr;
                }}

                .hero-logo-block {{
                    display: none;
                }}
            }}

            @media (max-width: 640px) {{
                .global-hero {{
                    padding: 1.8rem 1.1rem;
                    border-radius: 22px;
                }}

                .hero-badge {{
                    font-size: 0.7rem;
                    padding: 0.38rem 0.65rem;
                }}

                .hero-title {{
                    font-size: 2rem;
                    line-height: 1.08;
                }}

                .hero-subtitle {{
                    font-size: 0.94rem;
                    line-height: 1.58;
                }}

                .hero-tag {{
                    font-size: 0.78rem;
                    padding: 0.45rem 0.65rem;
                }}
            }}
        </style>
    </head>

    <body>
        <section class="global-hero">
            <div class="hero-content-grid">
                <div class="hero-text-block">
                    <div class="hero-badge">Global Speech Intelligence · Research-Ready · Multilingual</div>

                    <h1 class="hero-title">IntonaSphere AI</h1>

                    <p class="hero-subtitle">
                        A multilingual speech analysis platform for transcribing audio and video,
                        generating phonetic representations, aligning TextGrid tiers, extracting
                        F0 contours, and connecting prosodic prominence to words, syllables,
                        phones, AP/IP domains, and interrogative meaning.
                    </p>

                    <div class="hero-tags">
                        <span class="hero-tag">European Languages</span>
                        <span class="hero-tag">African Languages</span>
                        <span class="hero-tag">Asian Languages</span>
                        <span class="hero-tag">TextGrid + Praat</span>
                        <span class="hero-tag">F0 / Pitch Contours</span>
                        <span class="hero-tag">Research Reports</span>
                    </div>
                </div>

                <div class="hero-logo-block">
                    {hero_logo}
                </div>
            </div>
        </section>
    </body>
    </html>
    """

    components.html(html, height=520, scrolling=False)


def render_global_feature_cards():
    st.markdown("## Built for global speech, teaching, and research")
    st.write(
        "Designed for linguists, language teachers, researchers, students, and speech-technology builders "
        "working across accents, scripts, regions, and multilingual communities."
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### Multilingual Transcription")
        st.write(
            "Process audio, video, recordings, and public media links with speech-to-text "
            "support for language learning, fieldwork, and research workflows."
        )

    with col2:
        st.markdown("### Phonetic + Prosodic Intelligence")
        st.write(
            "Generate phonetic representations, extract F0 movement, locate prominence, "
            "and connect pitch patterns to words, syllables, phones, AP/IP domains, and interrogative meaning."
        )

    with col3:
        st.markdown("### Research-Ready Outputs")
        st.write(
            "Export coherent speaker-level reports, acoustic tables, subtitles, and pitch-contour images "
            "in TXT, DOCX, PDF, CSV, Excel, SRT, and PNG formats."
        )


def render_research_workflow():
    st.markdown("## Analysis workflow")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.markdown("**1. Input**")
        st.caption("Upload audio/video, record speech, paste media URL, or pair audio with TextGrid.")

    with col2:
        st.markdown("**2. Transcribe**")
        st.caption("Generate orthographic transcript and verify accuracy with WER indices.")

    with col3:
        st.markdown("**3. Phonetic Layer**")
        st.caption("Route text through global phonetic engines and display engine reliability notes.")

    with col4:
        st.markdown("**4. Prosody**")
        st.caption("Extract F0, AP/IP windows, TextGrid intervals, and prominence markers.")

    with col5:
        st.markdown("**5. Export**")
        st.caption("Download full reports, acoustic tables, subtitles, and pitch-contour images.")


def render_trust_banner():
    st.info(
        "Transparent by design: every phonetic output includes the engine used, language code, "
        "fallback status, and a reliability note. For research, TextGrid/Praat verification remains "
        "the gold standard for timing-sensitive acoustic interpretation."
    )


def render_global_footer():
    st.markdown("---")
    st.caption(
        "IntonaSphere AI · Built for multilingual research, "
        "language education, and speech technology across Africa, Europe, Asia, and the world."
    )
