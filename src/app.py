"""UNSW Exam Master main entry point."""

from __future__ import annotations

import random
from io import BytesIO
from pathlib import Path
from datetime import datetime
from typing import Any

import streamlit as st
from streamlit_echarts import st_echarts

from config import (
    MOTIVATIONAL_QUOTES,
    PAGE_ICON,
    PAGE_TITLE,
    SIDEBAR_HEADER,
    UNSW_BG_PAGE,
    UNSW_CARD_BG,
    UNSW_CARD_SHADOW,
    UNSW_FONT_HEADING,
    UNSW_PRIMARY,
    UNSW_PRIMARY_HOVER,
    UNSW_SIDEBAR_BG,
    UNSW_SIDEBAR_BORDER,
    UNSW_SIDEBAR_TEXT,
    UNSW_TEXT,
)
from i18n import tr
from migrations.migrate import (
    BACKUPS_DIR,
    DB_PATH,
    MigrationError,
    MigrationInProgressError,
    migrate_to_latest,
)
from services.document_processor import PDFProcessor
from services.graph_service import GraphGenerator
from services.llm_service import LLMProcessor
from services.quiz_generator import QuizGenerator
from services.vector_store_service import DocumentVectorStore

COURSE_ID = "default"
_MIGRATIONS_DONE = False


def _read_app_version() -> str:
    version_file = Path(__file__).resolve().parents[1] / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip() or "0.0.0"
    except Exception:
        return "0.0.0"


APP_VERSION = _read_app_version()


def _lang() -> str:
    return st.session_state.get("lang", "zh")


def _t(key: str, **kwargs: object) -> str:
    return tr(_lang(), key, **kwargs)


def _now_label() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _current_collection() -> str:
    name = str(st.session_state.get("selected_collection") or COURSE_ID).strip()
    return name or COURSE_ID


def _render_language_switcher() -> None:
    """Render a simple sidebar-top language toggle with connected click buttons."""
    if "lang" not in st.session_state:
        st.session_state["lang"] = "zh"

    c1, c2 = st.sidebar.columns(2, gap="small")
    if c1.button(
        _t("lang_zh"),
        key="btn_lang_zh",
        type="primary" if _lang() == "zh" else "secondary",
        use_container_width=True,
    ):
        st.session_state["lang"] = "zh"
        st.rerun()
    if c2.button(
        _t("lang_en"),
        key="btn_lang_en",
        type="primary" if _lang() == "en" else "secondary",
        use_container_width=True,
    ):
        st.session_state["lang"] = "en"
        st.rerun()
    st.sidebar.caption(f"{_t('lang_label')}: {_t('lang_zh') if _lang() == 'zh' else _t('lang_en')}")


def _ensure_migrations_once() -> int:
    global _MIGRATIONS_DONE
    if not _MIGRATIONS_DONE:
        try:
            version = migrate_to_latest()
        except MigrationInProgressError:
            if not st.session_state.get("migration_in_progress_notice_shown"):
                st.info("Migration in progress. Please refresh shortly.")
                st.session_state["migration_in_progress_notice_shown"] = True
            return int(st.session_state.get("schema_version", 0))
        except MigrationError as e:
            st.error(f"{e}")
            st.error(f"Recovery: restore from backups in {BACKUPS_DIR}")
            st.stop()
        _MIGRATIONS_DONE = True
        st.session_state["migration_in_progress_notice_shown"] = False
        st.session_state["schema_version"] = version
        return version
    if "schema_version" in st.session_state:
        return int(st.session_state["schema_version"])
    # Best effort if session state got reset while process is alive.
    try:
        version = migrate_to_latest()
    except MigrationInProgressError:
        if not st.session_state.get("migration_in_progress_notice_shown"):
            st.info("Migration in progress. Please refresh shortly.")
            st.session_state["migration_in_progress_notice_shown"] = True
        return int(st.session_state.get("schema_version", 0))
    except MigrationError as e:
        st.error(f"{e}")
        st.error(f"Recovery: restore from backups in {BACKUPS_DIR}")
        st.stop()
    st.session_state["migration_in_progress_notice_shown"] = False
    st.session_state["schema_version"] = version
    return version


def _inject_unsw_css() -> None:
    """Inject UNSW style CSS."""
    st.markdown(
        f"""
        <style>
        .unsw-header {{
            background: {UNSW_PRIMARY};
            clip-path: polygon(0 0, 100% 0, 100% 72%, 0 100%);
            height: 64px;
            margin: -1rem -1rem 0 -1rem;
            padding: 0 0 0 1.5rem;
            display: flex;
            align-items: center;
            width: calc(100% + 2rem);
        }}
        .unsw-logo {{
            font-family: {UNSW_FONT_HEADING};
            font-weight: 900;
            font-size: 1.6rem;
            letter-spacing: 0.2em;
            color: #000;
        }}
        .stApp {{ background: {UNSW_BG_PAGE}; }}
        .main .block-container {{
            padding: 1.5rem 2rem;
            max-width: 100%;
            background: {UNSW_CARD_BG};
            box-shadow: {UNSW_CARD_SHADOW};
            border-radius: 6px;
        }}
        h1, h2, h3 {{
            font-family: {UNSW_FONT_HEADING} !important;
            letter-spacing: 0.03em !important;
            color: {UNSW_TEXT} !important;
        }}
        p, .stMarkdown {{ color: {UNSW_TEXT} !important; }}
        [data-testid="stSidebar"] {{
            background: {UNSW_SIDEBAR_BG};
            border-right: 1px solid {UNSW_SIDEBAR_BORDER};
        }}
        [data-testid="stSidebar"] .stMarkdown,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] .stCaptionContainer,
        [data-testid="stSidebar"] small {{ color: {UNSW_SIDEBAR_TEXT} !important; }}
        [data-testid="stSidebar"] .stButton > button {{
            border-radius: 4px !important;
            min-height: 2.1rem !important;
        }}
        .stButton > button {{
            background: {UNSW_PRIMARY} !important;
            color: {UNSW_TEXT} !important;
            border: none !important;
            border-radius: 4px;
            font-weight: 600;
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }}
        .stButton > button:hover {{
            background: {UNSW_PRIMARY_HOVER} !important;
            color: {UNSW_TEXT} !important;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.12);
        }}
        .stProgress > div > div > div {{ background: {UNSW_PRIMARY}; }}
        .sidebar-header {{
            font-family: {UNSW_FONT_HEADING};
            font-size: 0.9rem;
            font-weight: 700;
            color: {UNSW_PRIMARY};
            letter-spacing: 0.08em;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid {UNSW_SIDEBAR_BORDER};
        }}
        .quote-box {{
            background: rgba(255,255,255,0.06);
            border-left: 4px solid {UNSW_PRIMARY};
            padding: 0.75rem 1rem;
            border-radius: 0 4px 4px 0;
            color: rgba(255,255,255,0.9);
            font-size: 0.85rem;
            margin-top: 1rem;
        }}
        .unsw-section-title {{
            font-family: {UNSW_FONT_HEADING};
            font-size: 1rem;
            letter-spacing: 0.05em;
            color: #333;
            margin-bottom: 0.5rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _clear_study_derived_state() -> None:
    keys = [
        "study_summary",
        "study_graph_data",
        "study_syllabus",
        "study_flashcards",
        "study_image_analysis",
        "study_chat_history",
        "exam_quiz",
        "exam_submitted",
        "exam_user_answers",
        "study_index_stats",
    ]
    for k in keys:
        st.session_state.pop(k, None)


def _uploaded_files_signature(files: list[Any]) -> tuple[str, ...]:
    return tuple(sorted(f"{getattr(f, 'name', 'unknown')}:{getattr(f, 'size', 0)}" for f in files))


def _get_vector_store() -> DocumentVectorStore:
    return DocumentVectorStore(course_id=_current_collection())


def _get_index_status() -> dict[str, Any]:
    try:
        return _get_vector_store().get_index_status()
    except Exception:
        return {"compatible": True, "reasons": [], "metadata": {}, "expected": {}}


def _is_rebuild_locked() -> bool:
    return bool(st.session_state.get("index_rebuild_in_progress", False))


def _build_session_md() -> str:
    parts: list[str] = []
    if st.session_state.get("study_summary"):
        parts.append("## Chapter Summary\n\n")
        parts.append(st.session_state["study_summary"])
        parts.append("\n\n---\n\n")
    if st.session_state.get("study_syllabus"):
        s = st.session_state["study_syllabus"]
        parts.append("## Syllabus Checklist\n\n")
        parts.append(f"**{s.get('module_title') or 'Revision List'}**\n\n")
        for t in s.get("topics") or []:
            parts.append(f"- [{t.get('status', 'Pending')}] **{t.get('topic', '')}** - {t.get('priority', '')}\n")
        parts.append("\n---\n\n")
    if st.session_state.get("study_flashcards"):
        parts.append("## Flashcards\n\n")
        for i, c in enumerate(st.session_state["study_flashcards"], 1):
            parts.append(f"### Card {i}\n\n**Front** {c.get('front', '')}\n\n**Back** {c.get('back', '')}\n\n")
    return "".join(parts)


def _build_chat_context_base() -> str:
    parts: list[str] = []
    if st.session_state.get("study_summary"):
        parts.append("[Summary]\n")
        parts.append(st.session_state["study_summary"][:8000])
        parts.append("\n\n")
    if st.session_state.get("study_syllabus"):
        s = st.session_state["study_syllabus"]
        parts.append("[Syllabus]\n")
        parts.append(f"{s.get('module_title') or ''}\n")
        for t in s.get("topics") or []:
            parts.append(f"- {t.get('topic', '')} ({t.get('priority', '')})\n")
        parts.append("\n")
    return "".join(parts)


def _rag_context(query: str, api_key: str, top_k: int = 10) -> str:
    if not api_key.strip():
        return ""
    try:
        status = _get_index_status()
        if not status.get("compatible", True):
            st.session_state["index_outdated"] = True
            return ""
        chunks = _get_vector_store().search(query=query, api_key=api_key, top_k=top_k)
    except Exception:
        return ""
    if not chunks:
        return ""
    lines: list[str] = []
    for i, item in enumerate(chunks, 1):
        meta = item.get("metadata") or {}
        name = meta.get("file_name", "Unknown")
        page = meta.get("page", "-")
        lines.append(f"[Chunk {i}] ({name}, p.{page})\n{item.get('text', '')}\n")
    return "\n".join(lines)


def _task_context(task_hint: str, api_key: str, fallback_chars: int = 12000) -> str:
    retrieved = _rag_context(task_hint, api_key, top_k=12)
    if retrieved:
        return retrieved
    return (st.session_state.get("study_extracted_text") or "")[:fallback_chars]


def _build_revision_report_md() -> str:
    parts = ["# UNSW Revision Notes\n\n", "---\n\n"]
    if st.session_state.get("study_summary"):
        parts.append("## Chapter Summary\n\n")
        parts.append(st.session_state["study_summary"])
        parts.append("\n\n---\n\n")
    if st.session_state.get("study_syllabus"):
        s = st.session_state["study_syllabus"]
        parts.append("## Syllabus\n\n")
        parts.append(f"### {s.get('module_title') or 'Revision List'}\n\n")
        for t in s.get("topics") or []:
            parts.append(f"- **{t.get('topic', '')}** - *{t.get('priority', '')}*\n")
        parts.append("\n---\n\n")
    if st.session_state.get("study_flashcards"):
        parts.append("## Flashcards\n\n")
        for i, c in enumerate(st.session_state["study_flashcards"], 1):
            parts.append(f"### Card {i}\n\n**Q** {c.get('front', '')}\n\n**A** {c.get('back', '')}\n\n")
    return "".join(parts)


def _build_report_pdf_bytes(report_md: str) -> bytes | None:
    """Create a simple PDF from Markdown text if reportlab is installed."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import simpleSplit
        from reportlab.pdfgen import canvas
    except Exception:
        return None

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin_x = 40
    y = height - 50
    for raw_line in report_md.splitlines():
        line = raw_line.strip() or " "
        wrapped = simpleSplit(line, "Helvetica", 10, width - (margin_x * 2))
        for w in wrapped:
            c.setFont("Helvetica", 10)
            c.drawString(margin_x, y, w)
            y -= 14
            if y < 40:
                c.showPage()
                y = height - 50
    c.save()
    buffer.seek(0)
    return buffer.read()


def _get_changelog_preview(limit: int = 3) -> list[str]:
    changelog_path = Path(__file__).resolve().parents[1] / "CHANGELOG.md"
    if not changelog_path.exists():
        return []
    try:
        lines = changelog_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []

    in_latest_section = False
    bullets: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if in_latest_section:
                break
            in_latest_section = True
            continue
        if not in_latest_section:
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
    if bullets:
        return bullets[:limit]

    # fallback: first bullet lines in file
    all_bullets = [ln.strip()[2:].strip() for ln in lines if ln.strip().startswith("- ")]
    return all_bullets[:limit]


def _run_index_build(uploaded_files: list[Any], api_key: str) -> None:
    if not uploaded_files:
        st.warning(_t("rebuild_need_upload"))
        return
    if not api_key:
        st.warning(_t("enter_api_first"))
        return
    if _is_rebuild_locked():
        st.info("Index rebuild already in progress.")
        return

    st.session_state["index_rebuild_in_progress"] = True
    try:
        with st.spinner(_t("indexing")):
            for f in uploaded_files:
                f.seek(0)
            store = _get_vector_store()
            store.clear_course()
            stats = store.index_uploaded_files(uploaded_files, api_key=api_key)
            st.session_state["study_index_stats"] = stats
            st.session_state["last_index_build_time"] = _now_label()
            st.session_state["last_studied_collection"] = _current_collection()
            st.session_state["index_outdated"] = False
            st.success(
                _t(
                    "index_ready",
                    i=stats["indexed_files"],
                    s=stats["skipped_files"],
                    c=stats["chunks_added"],
                )
            )
    except Exception as e:
        st.error(f"Index build failed: {e!s}. Please rebuild.")
    finally:
        st.session_state["index_rebuild_in_progress"] = False


def _cached_uploaded_file_objects() -> list[Any]:
    cache = st.session_state.get("study_uploaded_files_cache") or []
    out: list[Any] = []
    for item in cache:
        name = str(item.get("name") or "uploaded.pdf")
        data = item.get("data") or b""
        bio = BytesIO(data)
        bio.name = name  # type: ignore[attr-defined]
        out.append(bio)
    return out


def _render_sidebar() -> None:
    _render_language_switcher()
    st.sidebar.markdown(f'<p class="sidebar-header">{SIDEBAR_HEADER}</p>', unsafe_allow_html=True)
    st.sidebar.caption(_t("sidebar_settings"))
    if "selected_collection" not in st.session_state:
        st.session_state["selected_collection"] = COURSE_ID
    st.sidebar.text_input(
        _t("collection_label"),
        key="selected_collection",
        help=_t("collection_help"),
    )
    if "nav_page" not in st.session_state:
        st.session_state["nav_page"] = "dashboard"
    if "nav_page_radio" not in st.session_state:
        st.session_state["nav_page_radio"] = st.session_state["nav_page"]
    elif st.session_state["nav_page_radio"] != st.session_state["nav_page"]:
        st.session_state["nav_page_radio"] = st.session_state["nav_page"]
    nav_radio = st.sidebar.radio(
        _t("nav"),
        options=["dashboard", "study", "exam"],
        format_func=lambda x: (
            _t("dashboard")
            if x == "dashboard"
            else (_t("study_mode") if x == "study" else _t("exam_simulator"))
        ),
        key="nav_page_radio",
    )
    if st.session_state.get("nav_page") != nav_radio:
        st.session_state["nav_page"] = nav_radio
    st.sidebar.text_input(
        _t("api_key"),
        type="password",
        key="api_key",
        placeholder=_t("api_placeholder"),
        help=_t("api_help"),
    )

    stats = st.session_state.get("study_index_stats") or {}
    if stats:
        st.sidebar.caption(f"**{_t('index_status')}**")
        st.sidebar.markdown(
            f"{_t('indexed_files')}: **{stats.get('indexed_files', 0)}**  \n"
            f"{_t('skipped_files')}: **{stats.get('skipped_files', 0)}**  \n"
            f"{_t('chunks')}: **{stats.get('chunks_added', 0)}**"
        )

    st.sidebar.divider()
    report_md = _build_revision_report_md()
    if report_md:
        if st.sidebar.download_button(
            _t("download_md"),
            data=report_md,
            file_name="UNSW_Revision_Notes.md",
            mime="text/markdown",
            key="download_report_md",
        ):
            st.session_state["last_export_time"] = _now_label()
        report_pdf = _build_report_pdf_bytes(report_md)
        if report_pdf is not None:
            if st.sidebar.download_button(
                _t("download_pdf"),
                data=report_pdf,
                file_name="UNSW_Revision_Notes.pdf",
                mime="application/pdf",
                key="download_report_pdf",
            ):
                st.session_state["last_export_time"] = _now_label()
        else:
            st.sidebar.caption(_t("reportlab_hint"))

    session_md = _build_session_md()
    if session_md:
        if st.sidebar.download_button(
            _t("save_session"),
            data=session_md,
            file_name="unsw_session.md",
            mime="text/markdown",
            key="export_session",
        ):
            st.session_state["last_export_time"] = _now_label()

    st.sidebar.divider()
    with st.sidebar.expander(_t("about"), expanded=False):
        st.caption(f"{_t('app_version')}: {APP_VERSION}")
        st.caption(f"{_t('schema_version')}: {st.session_state.get('schema_version', 0)}")
        st.caption(f"DB: {DB_PATH}")

    st.sidebar.divider()
    st.sidebar.markdown(f'<div class="quote-box">{random.choice(MOTIVATIONAL_QUOTES)}</div>', unsafe_allow_html=True)


def _render_dashboard() -> None:
    st.subheader(_t("dashboard"))
    st.markdown(f"### {PAGE_TITLE}")
    st.caption(_t("hero_tagline"))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(_t("app_version"), APP_VERSION)
    c2.metric(_t("schema_version"), str(st.session_state.get("schema_version", 0)))
    c3.metric(_t("selected_lang"), _lang())
    c4.metric(_t("selected_collection"), _current_collection())

    action1, action2, action3 = st.columns(3)
    if action1.button(_t("go_study"), use_container_width=True):
        st.session_state["nav_page"] = "study"
        st.rerun()
    if action2.button(_t("build_index"), use_container_width=True):
        api_key = (st.session_state.get("api_key") or "").strip()
        _run_index_build(_cached_uploaded_file_objects(), api_key)
    if action3.button(_t("start_exam"), use_container_width=True):
        st.session_state["nav_page"] = "exam"
        st.rerun()

    st.divider()
    qa1, qa2 = st.columns(2)
    with qa1.container(border=True):
        st.markdown(f"#### {_t('continue_study')}")
        st.caption(_t("continue_study_desc"))
        recent = st.session_state.get("study_recent_file_names") or []
        if recent:
            st.caption(", ".join(recent[:5]))
        if st.button(_t("continue_study"), key="btn_continue_study", use_container_width=True):
            st.session_state["nav_page"] = "study"
            st.rerun()
    with qa2.container(border=True):
        st.markdown(f"#### {_t('start_mock_exam')}")
        st.caption(_t("start_mock_exam_desc"))
        st.caption(f"{_t('selected_collection')}: {_current_collection()}")
        if st.button(_t("start_mock_exam"), key="btn_start_mock", use_container_width=True):
            st.session_state["nav_page"] = "exam"
            st.rerun()

    st.divider()
    st.markdown(f"#### {_t('updates')}")
    updates = _get_changelog_preview(limit=3)
    if updates:
        for item in updates:
            st.markdown(f"- {item}")
    else:
        st.caption(_t("not_available"))
    toggle_key = "show_full_changelog"
    if st.button(_t("hide_full_changelog") if st.session_state.get(toggle_key) else _t("open_full_changelog")):
        st.session_state[toggle_key] = not st.session_state.get(toggle_key, False)
    if st.session_state.get(toggle_key):
        changelog_path = Path(__file__).resolve().parents[1] / "CHANGELOG.md"
        if changelog_path.exists():
            st.code(changelog_path.read_text(encoding="utf-8"), language="markdown")

    st.divider()
    st.markdown(f"#### {_t('activity')}")
    idx_time = st.session_state.get("last_index_build_time") or _t("not_available")
    exp_time = st.session_state.get("last_export_time") or _t("not_available")
    last_collection = st.session_state.get("last_studied_collection") or _t("not_available")
    st.markdown(f"- {_t('last_index_time')}: **{idx_time}**")
    st.markdown(f"- {_t('last_export_time')}: **{exp_time}**")
    st.markdown(f"- {_t('last_studied_collection')}: **{last_collection}**")
    if idx_time == _t("not_available") and exp_time == _t("not_available"):
        st.caption(_t("empty_activity_tip_1"))
        st.caption(_t("empty_activity_tip_2"))

    st.divider()
    st.markdown(f"#### {_t('need_help')}")
    if st.button(_t("help_index"), key="btn_help_index"):
        st.session_state["nav_page"] = "study"
        st.rerun()
    st.markdown(f"- {_t('help_migration')}: `backups/`")
    st.markdown(f"- {_t('help_self_check')}")
    st.caption(_t("help_self_check_cmd"))


def _render_study_mode() -> None:
    st.subheader(_t("study_mode"))
    st.markdown(f'<p class="unsw-section-title">{_t("upload_materials")}</p>', unsafe_allow_html=True)

    uploaded_files = st.file_uploader(
        _t("upload_pdf"),
        type=["pdf"],
        accept_multiple_files=True,
        key="study_upload",
        help=_t("upload_help"),
    )

    if uploaded_files:
        signature = _uploaded_files_signature(uploaded_files)
        if signature != st.session_state.get("study_upload_signature"):
            _clear_study_derived_state()
            st.session_state["study_upload_signature"] = signature

            processor = PDFProcessor()
            extracted_parts: list[str] = []
            for file in uploaded_files:
                file.seek(0)
                try:
                    extracted_parts.append(processor.extract_text(file))
                except ValueError as e:
                    st.warning(f"{getattr(file, 'name', 'file')}: {e!s}")
            st.session_state["study_uploaded_files_cache"] = [
                {"name": getattr(f, "name", "uploaded.pdf"), "data": f.getvalue()}
                for f in uploaded_files
            ]
            st.session_state["study_recent_file_names"] = [getattr(f, "name", "uploaded.pdf") for f in uploaded_files]
            st.session_state["study_extracted_text"] = "\n\n".join(extracted_parts)
            st.session_state["last_uploaded_study_name"] = ", ".join(getattr(f, "name", "") for f in uploaded_files)
            st.session_state["last_studied_collection"] = _current_collection()

        text = st.session_state.get("study_extracted_text", "")
        if text:
            st.success(_t("loaded_files", n=len(uploaded_files), c=len(text)))
            with st.expander(_t("preview")):
                st.text(text[:700])

        api_key = (st.session_state.get("api_key") or "").strip()
        if st.button(_t("build_index"), key="btn_index_build"):
            _run_index_build(uploaded_files, api_key)

    status = _get_index_status()
    if not status.get("compatible", True):
        details = "; ".join(status.get("reasons") or [])
        st.warning(_t("index_outdated"))
        if details:
            st.caption(_t("index_details", details=details))
        if st.button(_t("rebuild_now"), key="btn_rebuild_outdated"):
            api_key = (st.session_state.get("api_key") or "").strip()
            _run_index_build(uploaded_files, api_key)

    st.markdown(f'<p class="unsw-section-title">{_t("generate")}</p>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    api_key = (st.session_state.get("api_key") or "").strip()

    with col1:
        if st.button(_t("gen_summary"), key="btn_summary"):
            if not api_key:
                st.warning(_t("enter_api"))
            else:
                with st.spinner(_t("gen_summary_spinner")):
                    context = _task_context("Comprehensive chapter summary with key formulas and exam priorities", api_key)
                    st.session_state["study_summary"] = LLMProcessor().generate_summary(context, api_key)

    with col2:
        if st.button(_t("gen_graph"), key="btn_graph"):
            if not api_key:
                st.warning(_t("enter_api"))
            else:
                with st.spinner(_t("gen_graph_spinner")):
                    context = _task_context("Concept hierarchy and dependency relationships", api_key)
                    st.session_state["study_graph_data"] = GraphGenerator().generate_graph_data(context, api_key)

    with col3:
        if st.button(_t("gen_syllabus"), key="btn_syllabus"):
            if not api_key:
                st.warning(_t("enter_api"))
            else:
                with st.spinner(_t("gen_syllabus_spinner")):
                    context = _task_context("Revision checklist with High Medium Low priorities", api_key)
                    st.session_state["study_syllabus"] = LLMProcessor().generate_syllabus_checklist(context, api_key)

    with st.expander(_t("image_analysis"), expanded=False):
        img_file = st.file_uploader(_t("upload_image"), type=["png", "jpg", "jpeg"], key="study_image")
        if img_file is not None:
            st.image(img_file, use_container_width=True)
            if st.button(_t("analyze_image"), key="btn_analyze_image"):
                if not api_key:
                    st.warning(_t("enter_api"))
                else:
                    img_file.seek(0)
                    st.session_state["study_image_analysis"] = LLMProcessor().analyze_image(img_file.read(), "", api_key)
        if st.session_state.get("study_image_analysis"):
            st.markdown(st.session_state["study_image_analysis"])

    if st.session_state.get("study_summary"):
        st.markdown(f'<p class="unsw-section-title">{_t("chapter_summary")}</p>', unsafe_allow_html=True)
        st.markdown(st.session_state["study_summary"])

    if st.session_state.get("study_graph_data"):
        graph_data = st.session_state["study_graph_data"]
        nodes_data = graph_data.get("nodes") or []
        links_data = graph_data.get("links") or []
        categories_data = graph_data.get("categories") or []
        if nodes_data or links_data:
            CATEGORY_COLORS = ["#FFCC00", "#F5F5F5", "#9E9E9E"]
            categories_echarts = []
            for i, cat in enumerate(categories_data[:3]):
                name = cat.get("name", ["Core Topic", "Key Concept", "Detail"][i])
                color = CATEGORY_COLORS[i] if i < len(CATEGORY_COLORS) else "#BDBDBD"
                categories_echarts.append({"name": name, "itemStyle": {"color": color}, "label": {"color": "#1a1a1a"}})
            option = {
                "backgroundColor": "#FFFFFF",
                "tooltip": {"show": True},
                "legend": {
                    "show": True,
                    "data": [c["name"] for c in categories_echarts],
                    "textStyle": {"color": "#333"},
                    "top": "top",
                },
                "series": [
                    {
                        "type": "graph",
                        "layout": "force",
                        "symbolSize": 30,
                        "roam": True,
                        "label": {"show": True, "position": "right", "color": "#333"},
                        "edgeSymbol": ["circle", "arrow"],
                        "edgeSymbolSize": [4, 8],
                        "lineStyle": {"curveness": 0.3, "color": "source", "opacity": 0.6},
                        "emphasis": {"focus": "adjacency", "lineStyle": {"width": 3}},
                        "force": {"repulsion": 1000, "edgeLength": [50, 200], "gravity": 0.08},
                        "data": nodes_data,
                        "links": links_data,
                        "categories": categories_echarts,
                    }
                ],
            }
            st_echarts(options=option, height="550px")

    if st.session_state.get("study_syllabus"):
        syllabus = st.session_state["study_syllabus"]
        topics = syllabus.get("topics") or []
        if topics:
            st.markdown(f"**{syllabus.get('module_title') or _t('syllabus_default')}**")
            checked = sum(1 for i in range(len(topics)) if st.session_state.get(f"syllabus_cb_{i}", False))
            progress = checked / len(topics)
            st.progress(progress)
            st.caption(_t("progress", done=checked, all=len(topics), pct=int(progress * 100)))
            for i, t in enumerate(topics):
                st.checkbox(f"**{t.get('topic', '')}** - {t.get('priority', 'Medium')}", key=f"syllabus_cb_{i}")

    st.divider()
    st.subheader(_t("flashcards"))
    if st.button(_t("extract_flashcards"), key="btn_flashcards"):
        if not api_key:
            st.warning(_t("enter_api"))
        else:
            with st.spinner(_t("extracting_flashcards")):
                context = _task_context("Core terms concepts and formulas as active recall flashcards", api_key)
                st.session_state["study_flashcards"] = LLMProcessor().generate_flashcards(context, api_key)

    cards = st.session_state.get("study_flashcards") or []
    if cards:
        cols = st.columns(2)
        for i, card in enumerate(cards):
            with cols[i % 2]:
                st.markdown(f"**{_t('front')}**")
                st.markdown(card.get("front", ""))
                with st.expander(_t("show_answer")):
                    st.markdown(card.get("back", "-"))

    st.divider()
    st.subheader(_t("qa"))
    if "study_chat_history" not in st.session_state:
        st.session_state["study_chat_history"] = []

    for msg in st.session_state["study_chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input(_t("chat_placeholder")):
        if not api_key:
            st.warning(_t("enter_api"))
        else:
            st.session_state["study_chat_history"].append({"role": "user", "content": prompt})
            with st.spinner(_t("answering")):
                base = _build_chat_context_base()
                retrieved = _rag_context(prompt, api_key, top_k=10)
                if not retrieved:
                    retrieved = (st.session_state.get("study_extracted_text") or "")[:10000]
                context = f"{base}\n\n[Retrieved Chunks]\n{retrieved}"
                reply = LLMProcessor().chat_with_context(context, prompt, api_key)
                st.session_state["study_chat_history"].append({"role": "assistant", "content": reply})
            st.rerun()


def _render_exam_simulator() -> None:
    st.subheader(_t("exam_simulator"))
    status = _get_index_status()
    if not status.get("compatible", True):
        details = "; ".join(status.get("reasons") or [])
        st.warning(_t("index_outdated"))
        if details:
            st.caption(_t("index_details", details=details))
    if "exam_quiz" not in st.session_state:
        st.session_state["exam_quiz"] = None
    if "exam_submitted" not in st.session_state:
        st.session_state["exam_submitted"] = False
    if "exam_user_answers" not in st.session_state:
        st.session_state["exam_user_answers"] = {}

    text = st.session_state.get("study_extracted_text") or ""
    if not text.strip():
        st.warning(_t("upload_first"))
        return

    num_questions = st.number_input(_t("num_questions"), min_value=1, max_value=15, value=5, key="exam_num_questions")
    if st.button(_t("generate_quiz"), key="exam_generate"):
        api_key = (st.session_state.get("api_key") or "").strip()
        if not api_key:
            st.warning(_t("enter_api"))
        else:
            with st.spinner(_t("generating_quiz")):
                quiz_context = _task_context(
                    f"Create {num_questions} single-choice exam questions covering broad key topics", api_key
                )
                quiz = QuizGenerator().generate_quiz(quiz_context, num_questions=num_questions, api_key=api_key)
                st.session_state["exam_quiz"] = quiz
                st.session_state["exam_submitted"] = False
                st.session_state["exam_user_answers"] = {}
            if not quiz.get("questions"):
                st.error(_t("quiz_fail"))
            else:
                st.success(_t("quiz_success", n=len(quiz["questions"])))

    quiz = st.session_state.get("exam_quiz")
    if not quiz or not quiz.get("questions"):
        return

    st.markdown(f"**{quiz.get('quiz_title') or _t('practice_test')}**")
    questions = quiz["questions"]
    with st.form("exam_form"):
        for q in questions:
            qid = q.get("id", 0)
            st.write(f"**{qid}. {q.get('question', '')}**")
            st.radio(_t("choose"), options=q.get("options") or [], key=f"exam_q_{qid}", label_visibility="collapsed")
        submitted = st.form_submit_button(_t("submit"))

    if submitted:
        st.session_state["exam_user_answers"] = {q.get("id", 0): st.session_state.get(f"exam_q_{q.get('id', 0)}") for q in questions}
        st.session_state["exam_submitted"] = True

    if st.session_state.get("exam_submitted"):
        st.divider()
        st.subheader(_t("results"))
        user_answers = st.session_state["exam_user_answers"]
        for q in questions:
            qid = q.get("id", 0)
            correct = q.get("correct_answer", "")
            chosen = user_answers.get(qid)
            if chosen == correct:
                st.success(_t("correct", qid=qid))
            else:
                st.error(_t("wrong", qid=qid, chosen=chosen or "N/A", correct=correct))
            expl = q.get("explanation", "").strip()
            if expl:
                with st.expander(_t("explanation")):
                    st.write(expl)


def main() -> None:
    st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout="wide")
    _ensure_migrations_once()
    _inject_unsw_css()
    st.markdown('<div class="unsw-header"><span class="unsw-logo">UNSW</span></div>', unsafe_allow_html=True)
    st.title(PAGE_TITLE)

    _render_sidebar()
    page = st.session_state.get("nav_page", "dashboard")
    if page == "dashboard":
        _render_dashboard()
    elif page == "study":
        _render_study_mode()
    elif page == "exam":
        _render_exam_simulator()
    else:
        _render_dashboard()


if __name__ == "__main__":
    main()
