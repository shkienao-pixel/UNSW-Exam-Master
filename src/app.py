"""
UNSW Exam Master — main entry point.
UI layout only: sidebar, tabs, and calls to services.
"""

import random

import streamlit as st
from streamlit_echarts import st_echarts

from config import (
    MOTIVATIONAL_QUOTES,
    PAGE_ICON,
    PAGE_TITLE,
    SIDEBAR_HEADER,
    SIDEBAR_TITLE,
    TAB_EXAM,
    TAB_STUDY,
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
from services.document_processor import PDFProcessor
from services.graph_service import GraphGenerator
from services.llm_service import LLMProcessor
from services.quiz_generator import QuizGenerator


def _inject_unsw_css() -> None:
    """Inject UNSW official-site style CSS: geometric header, cards, typography, sidebar."""
    st.markdown(
        f"""
        <style>
        /* ===== UNSW Geometric Header (clip-path) ===== */
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
        /* Page: very light gray */
        .stApp {{ background: {UNSW_BG_PAGE}; }}
        /* Main content: white card with shadow */
        .main .block-container {{
            padding: 1.5rem 2rem;
            max-width: 100%;
            background: {UNSW_CARD_BG};
            box-shadow: {UNSW_CARD_SHADOW};
            border-radius: 6px;
        }}
        /* Typography: sans-serif, letter-spacing for headings */
        h1, h2, h3 {{
            font-family: {UNSW_FONT_HEADING} !important;
            letter-spacing: 0.03em !important;
            color: {UNSW_TEXT} !important;
        }}
        p, .stMarkdown {{ color: {UNSW_TEXT} !important; }}
        /* Sidebar: deep black, white text, dark gray borders */
        [data-testid="stSidebar"] {{
            background: {UNSW_SIDEBAR_BG};
            border-right: 1px solid {UNSW_SIDEBAR_BORDER};
        }}
        [data-testid="stSidebar"] hr {{ border-color: {UNSW_SIDEBAR_BORDER}; opacity: 0.7; }}
        [data-testid="stSidebar"] .stMarkdown,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] .stCaptionContainer,
        [data-testid="stSidebar"] small {{ color: {UNSW_SIDEBAR_TEXT} !important; }}
        [data-testid="stSidebar"] input {{
            background: #2a2a2a !important;
            color: #fff !important;
            border: 1px solid {UNSW_SIDEBAR_BORDER} !important;
            border-radius: 4px;
        }}
        [data-testid="stSidebar"] input::placeholder {{ color: rgba(255,255,255,0.5); }}
        /* Sidebar file uploader: dark zone + yellow Browse button */
        [data-testid="stSidebar"] [data-testid="stFileUploader"] {{
            border: 1px dashed {UNSW_SIDEBAR_BORDER};
            border-radius: 4px;
            background: rgba(255,255,255,0.04);
        }}
        [data-testid="stSidebar"] [data-testid="stFileUploader"] section {{ color: rgba(255,255,255,0.9); }}
        [data-testid="stSidebar"] [data-testid="stFileUploader"] button {{
            background: {UNSW_PRIMARY} !important;
            color: #000 !important;
            border-radius: 4px;
            font-weight: 600;
        }}
        /* Sidebar expander */
        [data-testid="stSidebar"] [data-testid="stExpander"] summary,
        [data-testid="stSidebar"] [data-testid="stExpander"] label {{ color: {UNSW_SIDEBAR_TEXT} !important; }}
        [data-testid="stSidebar"] [data-testid="stExpander"] {{
            border: 1px solid {UNSW_SIDEBAR_BORDER};
            border-radius: 4px;
            background: rgba(255,255,255,0.03);
        }}
        [data-testid="stSidebar"] strong {{ color: {UNSW_PRIMARY}; }}
        /* Buttons: yellow, no border; hover = darker + lift */
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
        /* Section subtitle (官网风格) */
        .unsw-section-title {{
            font-family: {UNSW_FONT_HEADING};
            font-size: 1rem;
            letter-spacing: 0.05em;
            color: #333;
            margin-bottom: 0.5rem;
        }}
        [data-testid="stChatMessage"] {{ background: #FFF; border: 1px solid #eee; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _build_session_md() -> str:
    """Build a single Markdown string from current summary, syllabus, and flashcards."""
    parts: list[str] = []
    if st.session_state.get("study_summary"):
        parts.append("## 章节摘要\n\n")
        parts.append(st.session_state["study_summary"])
        parts.append("\n\n---\n\n")
    if st.session_state.get("study_syllabus"):
        s = st.session_state["study_syllabus"]
        parts.append("## 复习大纲\n\n")
        parts.append(f"**{s.get('module_title') or '复习清单'}**\n\n")
        for t in s.get("topics") or []:
            parts.append(f"- [{t.get('status', 'Pending')}] **{t.get('topic', '')}** — {t.get('priority', '')}\n")
        parts.append("\n---\n\n")
    if st.session_state.get("study_flashcards"):
        parts.append("## 核心考点闪卡\n\n")
        for i, c in enumerate(st.session_state["study_flashcards"], 1):
            parts.append(f"### 卡 {i}\n\n**正面** {c.get('front', '')}\n\n**背面** {c.get('back', '')}\n\n")
    return "".join(parts) if parts else ""


def _build_chat_context() -> str:
    """Build context string from summary, syllabus, and extracted text for chat."""
    parts: list[str] = []
    if st.session_state.get("study_summary"):
        parts.append("【摘要】\n")
        parts.append(st.session_state["study_summary"][:8000])
        parts.append("\n\n")
    if st.session_state.get("study_syllabus"):
        s = st.session_state["study_syllabus"]
        parts.append("【大纲】")
        parts.append(f" {s.get('module_title') or ''}\n")
        for t in s.get("topics") or []:
            parts.append(f"- {t.get('topic', '')} ({t.get('priority', '')})\n")
        parts.append("\n")
    if st.session_state.get("study_extracted_text"):
        parts.append("【原文摘录】\n")
        parts.append(st.session_state["study_extracted_text"][:10000])
    return "".join(parts) if parts else "（暂无上传资料，请先上传 PDF 并生成摘要或大纲。）"


def _build_revision_report_md() -> str:
    """Build a polished revision report Markdown (summary + syllabus + flashcards)."""
    parts: list[str] = [
        "# UNSW Revision Notes\n\n",
        "---\n\n",
    ]
    if st.session_state.get("study_summary"):
        parts.append("## 📝 章节摘要\n\n")
        parts.append(st.session_state["study_summary"])
        parts.append("\n\n---\n\n")
    if st.session_state.get("study_syllabus"):
        s = st.session_state["study_syllabus"]
        parts.append("## 📋 复习大纲\n\n")
        parts.append(f"### {s.get('module_title') or '复习清单'}\n\n")
        for t in s.get("topics") or []:
            parts.append(f"- **{t.get('topic', '')}** — *{t.get('priority', '')}*\n")
        parts.append("\n---\n\n")
    if st.session_state.get("study_flashcards"):
        parts.append("## 🗂️ 核心考点闪卡\n\n")
        for i, c in enumerate(st.session_state["study_flashcards"], 1):
            parts.append(f"### 卡 {i}\n\n")
            parts.append(f"**Q** {c.get('front', '')}\n\n")
            parts.append(f"**A** {c.get('back', '')}\n\n")
        parts.append("---\n\n*Generated by UNSW Exam Master*\n")
    return "".join(parts) if len(parts) > 2 else ""


def _clear_study_derived_state() -> None:
    """Clear summary, syllabus, flashcards, graph, chat, exam when PDF changes."""
    keys = [
        "study_summary", "study_graph_data", "study_syllabus", "study_flashcards",
        "study_image_analysis", "study_chat_history",
        "exam_quiz", "exam_submitted", "exam_user_answers",
    ]
    for k in keys:
        if k in st.session_state:
            del st.session_state[k]


def _get_cached_counts() -> tuple[int, int]:
    """Return (num syllabus topics, num exam questions) cached in session."""
    topics = st.session_state.get("study_syllabus") or {}
    topic_list = topics.get("topics") or []
    quiz = st.session_state.get("exam_quiz") or {}
    questions = quiz.get("questions") or []
    return len(topic_list), len(questions)


def generate_final_report() -> str:
    """
    Build the final offline report Markdown from session state.
    Includes: course/PDF info, AI summary, syllabus (with completion), flashcards.
    """
    parts: list[str] = []
    # Title and course info
    pdf_name = st.session_state.get("last_uploaded_study_name", "") or "Course Materials"
    module_title = ""
    if st.session_state.get("study_syllabus"):
        module_title = (st.session_state["study_syllabus"].get("module_title") or "").strip()
    course_label = module_title or pdf_name.replace(".pdf", "").replace("_", " ").title()
    parts.append("# UNSW Study Notes\n\n")
    parts.append("---\n\n")
    parts.append("## 📌 课程信息\n\n")
    parts.append(f"- **材料名称**: {pdf_name}\n")
    if module_title:
        parts.append(f"- **模块/章节**: {module_title}\n")
    parts.append("\n---\n\n")
    # AI summary
    if st.session_state.get("study_summary"):
        parts.append("## 📝 章节摘要\n\n")
        parts.append(st.session_state["study_summary"])
        parts.append("\n\n---\n\n")
    # Syllabus with completion status
    if st.session_state.get("study_syllabus"):
        s = st.session_state["study_syllabus"]
        title = s.get("module_title") or "复习大纲"
        topics = s.get("topics") or []
        parts.append("## 📋 复习大纲\n\n")
        parts.append(f"### {title}\n\n")
        for i, t in enumerate(topics):
            done = st.session_state.get(f"syllabus_cb_{i}", False)
            check = "- [x]" if done else "- [ ]"
            parts.append(f"{check} **{t.get('topic', '')}** — {t.get('priority', '')}\n")
        parts.append("\n---\n\n")
    # Flashcards
    if st.session_state.get("study_flashcards"):
        parts.append("## 🗂️ 核心考点闪卡 (Active Recall)\n\n")
        for i, c in enumerate(st.session_state["study_flashcards"], 1):
            parts.append(f"### 卡 {i}\n\n")
            parts.append(f"**Q** {c.get('front', '')}\n\n")
            parts.append(f"**A** {c.get('back', '')}\n\n")
        parts.append("---\n\n")
    parts.append("*Generated by UNSW Exam Master · 关闭前请保存*\n")
    return "".join(parts)


def _render_sidebar() -> None:
    """Render sidebar: header, file uploader, API key, export, motivational quote."""
    st.sidebar.markdown(f'<p class="sidebar-header">{SIDEBAR_HEADER}</p>', unsafe_allow_html=True)
    st.sidebar.caption(SIDEBAR_TITLE)
    st.sidebar.file_uploader(
        "Upload materials",
        type=["pdf", "pptx", "txt"],
        key="sidebar_upload",
        help="PDF, PPTX, or TXT",
    )
    st.sidebar.text_input(
        "API Key",
        type="password",
        key="api_key",
        placeholder="OpenAI / Gemini API Key",
        help="Stored in session only, not persisted.",
    )
    st.sidebar.divider()
    # Session status: cached 考点 & 题目 count
    num_topics, num_questions = _get_cached_counts()
    st.sidebar.caption("**Session 状态**")
    st.sidebar.markdown(
        f"考点 **{num_topics}** · 模拟题 **{num_questions}** 道  \n"
        "*关闭前请保存导出*",
        help="当前已缓存的复习大纲条目与模拟题数量",
    )
    st.sidebar.divider()
    with st.sidebar.expander("Export & Save", expanded=False):
        has_report_content = (
            bool(st.session_state.get("study_summary"))
            or bool(st.session_state.get("study_syllabus"))
            or bool(st.session_state.get("study_flashcards"))
        )
        if has_report_content:
            report_md = generate_final_report()
            st.download_button(
                "📥 下载 UNSW_Study_Notes.md",
                data=report_md,
                file_name="UNSW_Study_Notes.md",
                mime="text/markdown",
                key="download_final_report",
            )
        else:
            st.caption("暂无摘要/大纲/闪卡，生成后即可导出。")
    session_md = _build_session_md()
    if session_md:
        st.sidebar.download_button(
            "保存当前 Session",
            data=session_md,
            file_name="unsw_session.md",
            mime="text/markdown",
            key="export_session",
        )
    st.sidebar.divider()
    quote = random.choice(MOTIVATIONAL_QUOTES)
    st.sidebar.markdown(f'<div class="quote-box">💡 {quote}</div>', unsafe_allow_html=True)


def _render_study_mode() -> None:
    """Study Mode tab: file uploader and PDF text extraction."""
    st.subheader("Study Mode")
    st.markdown('<p class="unsw-section-title">上传课程材料 · Upload Materials</p>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader(
        "File Uploader",
        type=["pdf", "pptx", "txt"],
        key="study_upload",
        help="Upload course materials for processing.",
    )
    if uploaded_file is not None:
        current_name = getattr(uploaded_file, "name", "") or ""
        last_name = st.session_state.get("last_uploaded_study_name", "")
        if current_name and current_name != last_name:
            _clear_study_derived_state()
            st.session_state["last_uploaded_study_name"] = current_name
        if uploaded_file.type == "application/pdf":
            with st.spinner("正在读取 PDF…"):
                processor = PDFProcessor()
                try:
                    text = processor.extract_text(uploaded_file)
                    st.session_state["study_extracted_text"] = text
                    st.success(f"✅ 文件读取成功！共提取了 {len(text)} 个字符。")
                    with st.expander("预览（前 500 字）"):
                        st.text(text[:500] if len(text) > 500 else text)
                except ValueError as e:
                    st.error(str(e))
            if st.session_state.get("study_extracted_text"):
                st.markdown('<p class="unsw-section-title">一键生成 · Generate</p>', unsafe_allow_html=True)
                with st.container():
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if st.button("📝 生成章节摘要", key="btn_summary"):
                            api_key = (st.session_state.get("api_key") or "").strip()
                            if not api_key:
                                st.warning("请在侧边栏输入 API Key。")
                            else:
                                with st.spinner("正在分析课程内容，请稍候..."):
                                    try:
                                        summary = LLMProcessor().generate_summary(
                                            st.session_state["study_extracted_text"], api_key
                                        )
                                        st.session_state["study_summary"] = summary
                                    except ValueError as e:
                                        st.error(str(e))
                    with col2:
                        if st.button("🕸️ 生成知识图谱", key="btn_graph"):
                            api_key = (st.session_state.get("api_key") or "").strip()
                            if not api_key:
                                st.warning("请在侧边栏输入 API Key。")
                            else:
                                with st.spinner("正在生成知识图谱，请稍候..."):
                                    try:
                                        graph_data = GraphGenerator().generate_graph_data(
                                            st.session_state["study_extracted_text"], api_key
                                        )
                                        if not graph_data.get("nodes") and not graph_data.get("links"):
                                            st.error("生成知识图谱失败或返回为空，请稍后重试。")
                                        else:
                                            st.session_state["study_graph_data"] = graph_data
                                            st.success("知识图谱已生成。")
                                    except Exception as e:
                                        st.error(f"生成知识图谱时出错：{e!s}")
                    with col3:
                        if st.button("📋 生成复习大纲", key="btn_syllabus"):
                            api_key = (st.session_state.get("api_key") or "").strip()
                            if not api_key:
                                st.warning("请在侧边栏输入 API Key。")
                            else:
                                with st.spinner("正在生成复习大纲，请稍候..."):
                                    try:
                                        syllabus = LLMProcessor().generate_syllabus_checklist(
                                            st.session_state["study_extracted_text"], api_key
                                        )
                                        if not syllabus.get("topics"):
                                            st.error("生成复习大纲失败或返回为空，请稍后重试。")
                                        else:
                                            st.session_state["study_syllabus"] = syllabus
                                            st.success("复习大纲已生成。")
                                    except ValueError as e:
                                        st.error(str(e))
                                    except Exception as e:
                                        st.error(f"生成复习大纲时出错：{e!s}")
        else:
            st.info("当前仅支持 PDF 文本提取，PPTX/TXT 将在后续版本支持。")
    with st.expander("📷 课件截图分析", expanded=False):
        img_file = st.file_uploader("上传课件截图", type=["png", "jpg", "jpeg"], key="study_image")
        if img_file is not None:
            st.image(img_file, use_container_width=True, caption="截图预览")
            if st.button("分析截图", key="btn_analyze_image"):
                api_key = (st.session_state.get("api_key") or "").strip()
                if not api_key:
                    st.warning("请在侧边栏输入 API Key。")
                else:
                    img_file.seek(0)
                    with st.spinner("正在分析截图…"):
                        try:
                            analysis = LLMProcessor().analyze_image(img_file.read(), "", api_key)
                            st.session_state["study_image_analysis"] = analysis
                        except ValueError as e:
                            st.error(str(e))
                        except Exception as e:
                            st.error(f"分析截图时出错：{e!s}")
        if st.session_state.get("study_image_analysis"):
            st.markdown("**分析结果**")
            st.markdown(st.session_state["study_image_analysis"])
    if st.session_state.get("study_summary"):
        st.markdown('<p class="unsw-section-title">章节摘要 · Chapter Summary</p>', unsafe_allow_html=True)
        st.markdown(st.session_state["study_summary"])
        st.download_button(
            "下载摘要 (.md)",
            data=st.session_state["study_summary"],
            file_name="summary.md",
            mime="text/markdown",
            key="download_summary",
        )
    report_md = _build_revision_report_md()
    if report_md:
        st.download_button(
            "📦 导出复习报告",
            data=report_md,
            file_name="UNSW_Revision_Notes.md",
            mime="text/markdown",
            key="export_revision_report",
        )
    if st.session_state.get("study_graph_data"):
        graph_data = st.session_state["study_graph_data"]
        nodes_data = graph_data.get("nodes") or []
        links_data = graph_data.get("links") or []
        categories_data = graph_data.get("categories") or []
        if nodes_data or links_data:
            st.markdown('<p class="unsw-section-title">知识图谱 · Knowledge Graph</p>', unsafe_allow_html=True)
            st.subheader("知识图谱")
            # UNSW / 学术配色：Core=金 #FFCC00, Key=白 #F5F5F5, Detail=灰 #9E9E9E
            CATEGORY_COLORS = ["#FFCC00", "#F5F5F5", "#9E9E9E"]
            categories_echarts = []
            for i, cat in enumerate(categories_data[:3]):
                name = cat.get("name", ["Core Topic", "Key Concept", "Detail"][i])
                color = CATEGORY_COLORS[i] if i < len(CATEGORY_COLORS) else "#BDBDBD"
                categories_echarts.append({
                    "name": name,
                    "itemStyle": {"color": color},
                    "label": {"color": "#1a1a1a"},
                })
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
                        "force": {
                            "repulsion": 1000,
                            "edgeLength": [50, 200],
                            "gravity": 0.08,
                        },
                        "data": nodes_data,
                        "links": links_data,
                        "categories": categories_echarts,
                    }
                ],
            }
            with st.expander("图例说明", expanded=False):
                st.markdown(
                    "| 层级 | 含义 | 颜色 |\n"
                    "|------|------|------|\n"
                    "| **Core Topic** | 核心主题 | 🟡 金色 |\n"
                    "| **Key Concept** | 关键概念 | ⚪ 浅灰白 |\n"
                    "| **Detail** | 细节/公式 | ⚫ 灰色 |"
                )
            st.markdown(
                '<div style="background-color:#FFFFFF; padding:1rem; border-radius:4px; margin:0.5rem 0; box-shadow:0 1px 3px rgba(0,0,0,0.08);">',
                unsafe_allow_html=True,
            )
            try:
                st_echarts(options=option, height="550px")
            except Exception as e:
                st.error(f"渲染知识图谱时出错：{e!s}")
            st.markdown("</div>", unsafe_allow_html=True)
    if st.session_state.get("study_syllabus"):
        syllabus = st.session_state["study_syllabus"]
        topics = syllabus.get("topics") or []
        if topics:
            st.markdown('<p class="unsw-section-title">复习大纲 · Syllabus Checklist</p>', unsafe_allow_html=True)
            st.subheader("复习大纲")
            st.markdown(f"**{syllabus.get('module_title') or '复习清单'}**")
            checked = sum(
                1 for i in range(len(topics))
                if st.session_state.get(f"syllabus_cb_{i}", False)
            )
            progress = checked / len(topics) if topics else 0.0
            st.progress(progress)
            st.caption(f"进度：{checked}/{len(topics)}（{int(progress * 100)}%）")
            priority_color = {"High": "🔴", "Medium": "🟠", "Low": "🟢"}
            for i, t in enumerate(topics):
                prio = t.get("priority") or "Medium"
                badge = priority_color.get(prio, "🟠")
                label = f"{badge} **{t['topic']}** — {prio}"
                st.checkbox(label, key=f"syllabus_cb_{i}", label_visibility="visible")
            st.divider()
    st.divider()
    st.markdown('<p class="unsw-section-title">核心考点闪卡 · Active Recall</p>', unsafe_allow_html=True)
    st.subheader("🗂️ 核心考点闪卡 (Active Recall)")
    if st.session_state.get("study_extracted_text"):
        if st.button("💡 提取闪卡", key="btn_flashcards"):
            api_key = (st.session_state.get("api_key") or "").strip()
            if not api_key:
                st.warning("请在侧边栏输入 API Key。")
            else:
                with st.spinner("正在提取闪卡，请稍候..."):
                    try:
                        cards = LLMProcessor().generate_flashcards(
                            st.session_state["study_extracted_text"], api_key
                        )
                        if not cards:
                            st.error("提取闪卡失败或返回为空，请稍后重试。")
                        else:
                            st.session_state["study_flashcards"] = cards
                            st.success(f"已生成 {len(cards)} 张闪卡。")
                    except ValueError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"提取闪卡时出错：{e!s}")
    if st.session_state.get("study_flashcards"):
        cards = st.session_state["study_flashcards"]
        if cards:
            cols = st.columns(2)
            for i, card in enumerate(cards):
                with cols[i % 2]:
                    with st.container():
                        st.markdown(f"**正面**")
                        st.markdown(card.get("front", ""))
                        with st.expander("查看答案"):
                            st.markdown(card.get("back", "—"))
                        st.checkbox(
                            "标记为已掌握",
                            key=f"flashcard_mastered_{i}",
                            label_visibility="visible",
                        )
            mastered = sum(
                1 for i in range(len(cards))
                if st.session_state.get(f"flashcard_mastered_{i}", False)
            )
            if mastered > 0:
                st.caption(f"已掌握：{mastered}/{len(cards)} 张")
    st.divider()
    st.markdown('<p class="unsw-section-title">基于资料的问答 · Q&A</p>', unsafe_allow_html=True)
    st.subheader("💬 基于资料的问答")
    if "study_chat_history" not in st.session_state:
        st.session_state["study_chat_history"] = []
    for msg in st.session_state["study_chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    if prompt := st.chat_input("针对已上传资料提问…"):
        api_key = (st.session_state.get("api_key") or "").strip()
        if not api_key:
            st.warning("请在侧边栏输入 API Key 后重试。")
        else:
            st.session_state["study_chat_history"].append({"role": "user", "content": prompt})
            context = _build_chat_context()
            with st.spinner("正在生成回答…"):
                try:
                    reply = LLMProcessor().chat_with_context(context, prompt, api_key)
                    st.session_state["study_chat_history"].append({"role": "assistant", "content": reply})
                except ValueError as e:
                    st.session_state["study_chat_history"].append({"role": "assistant", "content": f"❌ {e!s}"})
                except Exception as e:
                    st.session_state["study_chat_history"].append({"role": "assistant", "content": f"❌ 出错：{e!s}"})
            st.rerun()


def _render_exam_simulator() -> None:
    """Exam Simulator tab: generate quiz from study text, render form, grade and show results."""
    st.subheader("Exam Simulator")
    if "exam_quiz" not in st.session_state:
        st.session_state["exam_quiz"] = None
    if "exam_submitted" not in st.session_state:
        st.session_state["exam_submitted"] = False
    if "exam_user_answers" not in st.session_state:
        st.session_state["exam_user_answers"] = {}

    text = st.session_state.get("study_extracted_text") or ""
    if not text or not text.strip():
        st.warning("请先在 **Study Mode** 上传并成功读取 PDF，再在此生成模拟题。")
        return

    num_questions = st.number_input("题目数量", min_value=1, max_value=15, value=5, key="exam_num_questions")
    if st.button("生成模拟题", key="exam_generate"):
        api_key = (st.session_state.get("api_key") or "").strip()
        if not api_key:
            st.warning("请在侧边栏输入 API Key。")
        else:
            with st.spinner("正在生成模拟题，请稍候..."):
                quiz = QuizGenerator().generate_quiz(text, num_questions=num_questions, api_key=api_key)
                st.session_state["exam_quiz"] = quiz
                st.session_state["exam_submitted"] = False
                st.session_state["exam_user_answers"] = {}
            if not quiz.get("questions"):
                st.error("生成题目失败或返回为空，请检查 API Key 或稍后重试。")
            else:
                st.success(f"已生成 {len(quiz['questions'])} 道题。")

    quiz = st.session_state.get("exam_quiz")
    if not quiz or not quiz.get("questions"):
        return

    st.markdown(f"**{quiz.get('quiz_title') or '模拟测验'}**")
    questions = quiz["questions"]

    with st.form("exam_form"):
        for q in questions:
            qid = q.get("id", 0)
            st.write(f"**{qid}. {q.get('question', '')}**")
            options = q.get("options") or []
            choice = st.radio(
                "请选择",
                options=options,
                key=f"exam_q_{qid}",
                label_visibility="collapsed",
            )
        submitted = st.form_submit_button("提交答案")

    if submitted:
        user_answers = {}
        for q in questions:
            qid = q.get("id", 0)
            user_answers[qid] = st.session_state.get(f"exam_q_{qid}")
        st.session_state["exam_user_answers"] = user_answers
        st.session_state["exam_submitted"] = True

    if st.session_state.get("exam_submitted") and st.session_state.get("exam_user_answers") is not None:
        st.divider()
        st.subheader("批改结果")
        user_answers = st.session_state["exam_user_answers"]
        for q in questions:
            qid = q.get("id", 0)
            correct = q.get("correct_answer", "")
            chosen = user_answers.get(qid)
            is_correct = chosen == correct
            if is_correct:
                st.success(f"第 {qid} 题：正确 ✅")
            else:
                st.error(f"第 {qid} 题：错误 ❌（你的选择：{chosen or '未选'}；正确答案：{correct}）")
            expl = q.get("explanation", "").strip()
            if expl:
                with st.expander("解析"):
                    st.write(expl)


def main() -> None:
    """Application entry point."""
    st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout="wide")
    _inject_unsw_css()
    st.markdown(
        '<div class="unsw-header"><span class="unsw-logo">UNSW</span></div>',
        unsafe_allow_html=True,
    )
    st.title(PAGE_TITLE)

    _render_sidebar()

    tab1, tab2 = st.tabs([TAB_STUDY, TAB_EXAM])
    with tab1:
        _render_study_mode()
    with tab2:
        _render_exam_simulator()


if __name__ == "__main__":
    main()
