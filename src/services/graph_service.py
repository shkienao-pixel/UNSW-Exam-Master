"""
Knowledge graph: extract hierarchical concepts and relations for ECharts visualization.
"""

import json
import re
from typing import Any

from services.llm_service import LLMProcessor

GRAPH_SYSTEM_PROMPT = """你是一个知识图谱构建专家。根据用户提供的课程文本，构建一个分层、逻辑清晰的概念图谱，输出将用于 ECharts 图可视化。

你必须只输出一个合法的 JSON 对象，不要用 markdown 代码块包裹，不要输出任何 JSON 以外的文字。

**节点 (nodes)** 按三个等级 (category) 划分，用于控制显示大小与图例：
- **category 0 — Core Topic（核心主题）**：整章/整节的大主题，如 "Image Formation"、"Probability Theory"。对应 symbolSize 大 (50)，视觉上最突出。
- **category 1 — Key Concept（关键概念）**：支撑主题的重要概念，如 "Pinhole Model"、"Bayes Theorem"。对应 symbolSize 中 (35)。
- **category 2 — Detail（细节/公式）**：具体定义、公式或术语，如 "Linear Perspective"、"P(A|B)"。对应 symbolSize 小 (20)。

**边 (links)** 只保留 source 与 target，关系由连线表示即可。节点名称 (name) 作为唯一标识，source/target 必须与某节点的 name 一致。

JSON 结构必须严格如下（适配 ECharts graph）：
{
  "nodes": [
    {"name": "概念A", "category": 0, "symbolSize": 50},
    {"name": "概念B", "category": 1, "symbolSize": 35}
  ],
  "links": [
    {"source": "概念A", "target": "概念B"}
  ],
  "categories": [
    {"name": "Core Topic"},
    {"name": "Key Concept"},
    {"name": "Detail"}
  ]
}

要求：category 只能是 0、1 或 2；symbolSize 与层级一致（0→50, 1→35, 2→20）；至少 2 个 Core Topic；links 的 source/target 必须是 nodes 中某条的 name。"""

EMPTY_GRAPH: dict[str, Any] = {"nodes": [], "links": [], "categories": []}

# ECharts category index: 0=Core Topic, 1=Key Concept, 2=Detail
VALID_CATEGORIES = {0, 1, 2}
# Default symbolSize by category (Core=50, Key=35, Detail=20)
CATEGORY_SYMBOL_SIZE = {0: 50, 1: 35, 2: 20}


def _strip_json_raw(raw: str) -> str:
    """Remove markdown code fences and surrounding whitespace."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def _try_parse_graph_json(raw: str) -> dict[str, Any]:
    """Parse JSON from LLM output; return EMPTY_GRAPH on failure."""
    for candidate in [raw, _strip_json_raw(raw)]:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return EMPTY_GRAPH.copy()


def _normalize_category(value: Any) -> int:
    """Coerce to valid category 0, 1, or 2; default 1."""
    if value is None:
        return 1
    try:
        c = int(value)
        return c if c in VALID_CATEGORIES else 1
    except (TypeError, ValueError):
        return 1


def _validate_graph(obj: Any) -> dict[str, Any]:
    """Ensure ECharts-compatible structure: nodes (name, category, symbolSize), links (source, target), categories."""
    if not isinstance(obj, dict):
        return EMPTY_GRAPH.copy()
    nodes = obj.get("nodes")
    links = obj.get("links")
    categories = obj.get("categories")
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(links, list):
        links = []
    if not isinstance(categories, list) or len(categories) < 3:
        categories = [
            {"name": "Core Topic"},
            {"name": "Key Concept"},
            {"name": "Detail"},
        ]
    out_nodes: list[dict[str, Any]] = []
    name_set: set[str] = set()
    for n in nodes:
        if not isinstance(n, dict):
            continue
        name = str(n.get("name") or n.get("label") or n.get("id") or "").strip()
        if not name or name in name_set:
            continue
        name_set.add(name)
        cat = _normalize_category(n.get("category"))
        size = n.get("symbolSize")
        if size is not None and isinstance(size, (int, float)):
            size = max(10, min(80, int(size)))
        else:
            size = CATEGORY_SYMBOL_SIZE.get(cat, 35)
        out_nodes.append({
            "name": name,
            "category": cat,
            "symbolSize": size,
        })
    out_links: list[dict[str, str]] = []
    for e in links:
        if not isinstance(e, dict):
            continue
        src = str(e.get("source", "")).strip()
        tgt = str(e.get("target", "")).strip()
        if not src or not tgt or src not in name_set or tgt not in name_set:
            continue
        out_links.append({"source": src, "target": tgt})
    out_categories: list[dict[str, str]] = []
    for i, c in enumerate(categories[:3]):
        if isinstance(c, dict) and c.get("name"):
            out_categories.append({"name": str(c["name"])})
        else:
            out_categories.append({"name": ["Core Topic", "Key Concept", "Detail"][i]})
    return {"nodes": out_nodes, "links": out_links, "categories": out_categories}


class GraphGenerator:
    """Extracts hierarchical concept nodes and links from text for ECharts graph."""

    def __init__(self) -> None:
        self._llm = LLMProcessor()

    def generate_graph_data(self, text: str, api_key: str = "") -> dict[str, Any]:
        """
        Extract nodes, links, and categories from course text (ECharts graph format).

        Args:
            text: Raw course material text.
            api_key: OpenAI API key.

        Returns:
            Dict with "nodes" (name, category, symbolSize), "links" (source, target), "categories".
            On failure, returns structure with empty nodes and links.
        """
        if not (api_key and api_key.strip()):
            return EMPTY_GRAPH.copy()
        user_message = (
            "请从以下课程内容中构建分层知识图谱：节点用 category 0/1/2（Core Topic / Key Concept / Detail），"
            "symbolSize 对应 50/35/20；links 只填 source 与 target（节点 name）。只输出上述 JSON。\n\n"
            f"{text[:12000]}"
        )
        try:
            raw = self._llm.invoke(
                GRAPH_SYSTEM_PROMPT,
                user_message,
                api_key=api_key.strip(),
                temperature=0.3,
            )
        except ValueError:
            return EMPTY_GRAPH.copy()
        if not raw:
            return EMPTY_GRAPH.copy()
        parsed = _try_parse_graph_json(raw)
        return _validate_graph(parsed)
