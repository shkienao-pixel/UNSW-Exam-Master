"""
Knowledge graph: extract hierarchical tree concepts from course text for ECharts tree visualization.
"""

import json
import re
from typing import Any

from services.llm_service import LLMProcessor

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMPTY_TREE: dict[str, Any] = {
    "name": "Knowledge Map",
    "description": "No data generated yet.",
    "children": [],
}

GRAPH_SYSTEM_PROMPT = """你是一个知识图谱构建专家。根据用户提供的课程文本，构建一个嵌套层级的知识树，输出将用于 ECharts tree 可视化。

你必须只输出一个合法的 JSON 对象，不要用 markdown 代码块包裹，不要输出任何 JSON 以外的文字。

JSON 结构必须严格如下（嵌套树格式，每个节点同时包含中英双语字段）：
{
  "name_zh": "总主题中文名称",
  "name_en": "Root Topic Name",
  "name": "总主题中文名称",
  "desc_zh": "对总主题的中文描述（含核心考点，30-100字）",
  "desc_en": "English description of the root topic (30-100 words, with key exam points)",
  "description": "对总主题的中文描述（含核心考点，30-100字）",
  "children": [
    {
      "name_zh": "关键概念A（中文）",
      "name_en": "Key Concept A",
      "name": "关键概念A（中文）",
      "desc_zh": "关键概念A的中文定义或描述（30-100字，含公式或考点）",
      "desc_en": "English definition of Key Concept A (30-100 words, with formulas or exam points)",
      "description": "关键概念A的中文定义或描述（30-100字，含公式或考点）",
      "children": [
        {
          "name_zh": "细节/公式1（中文）",
          "name_en": "Detail/Formula 1",
          "name": "细节/公式1（中文）",
          "desc_zh": "具体定义、公式推导或记忆要点（30-100字）",
          "desc_en": "Specific definition, formula derivation, or key points to remember (30-100 words)",
          "description": "具体定义、公式推导或记忆要点（30-100字）",
          "children": []
        }
      ]
    }
  ]
}

要求：
- 根节点（第0层）：1个，代表本章/本节总主题
- 第1层 children：3-8 个关键概念（Key Concepts）
- 第2层 children：每个关键概念下 2-6 个具体细节/公式（Details）
- 可以根据内容复杂度继续展开至第3-4层，叶节点 children 设为 []
- 每个节点必须有 name_zh、name_en、name（同name_zh）、desc_zh、desc_en、description（同desc_zh）、children（列表）
- name 字段：简短，≤20字
- 最大深度为8层
"""

# ---------------------------------------------------------------------------
# Known descriptions for image processing concepts (fallback enrichment)
# ---------------------------------------------------------------------------

KNOWN_DESCRIPTIONS: dict[str, str] = {
    "Spatial Filtering": (
        "在空间域对图像像素邻域进行卷积操作，常见滤波器有均值、高斯、中值、Laplacian 等。"
        "考点：滤波核大小对平滑/锐化效果的影响；线性与非线性滤波的区别。"
    ),
    "Convolution": (
        "卷积 (f*g)[x,y] = ΣΣ f[m,n]·g[x-m,y-n]，满足交换律、结合律、线性。"
        "考点：卷积与互相关的区别；可分离核的计算优势（O(MN·(k+k)) vs O(MN·k²)）。"
    ),
    "Derivative Filters": (
        "一阶导数（Sobel/Prewitt）检测边缘幅度，二阶导数（Laplacian）检测过零点。"
        "Sobel: Gx=[-1,0,1;-2,0,2;-1,0,1], Gy 为其转置。考点：噪声敏感性。"
    ),
    "Gaussian Smoothing": (
        "G(x,y) = (1/2πσ²)·exp(-(x²+y²)/2σ²)，σ 控制平滑程度，核越大越模糊。"
        "考点：可分离性（2D=1D×1D）；σ 与截止频率关系；高斯-拉普拉斯（LoG）滤波器。"
    ),
    "Edge Detection": (
        "Canny 流程：高斯平滑→梯度幅值&方向→非极大值抑制→双阈值连接。"
        "考点：两个阈值的作用（高阈值确定强边缘，低阈值扩展弱边缘）；抑制噪声与定位精度的 trade-off。"
    ),
    "Frequency Domain Filtering": (
        "傅里叶变换 F(u,v)=ΣΣf(x,y)·e^(-j2π(ux/M+vy/N))，低通保留平滑，高通增强边缘。"
        "考点：空间域卷积=频率域乘法；理想低通滤波器的振铃效应；高斯低通无振铃。"
    ),
    "Histogram Equalization": (
        "累计分布函数 CDF 映射：s=T(r)=(L-1)·CDF(r)，使输出直方图接近均匀分布，增强对比度。"
        "考点：局部直方图均衡化（CLAHE）；对已均匀分布的图像效果有限。"
    ),
    "Image Formation": (
        "针孔相机模型：x'=-f·X/Z, y'=-f·Y/Z（焦距 f，物距 Z），世界坐标→图像坐标。"
        "考点：透视投影（近大远小）；内参矩阵 K；畸变校正。"
    ),
    "Morphological Operations": (
        "侵蚀(Erosion)=最小值滤波，膨胀(Dilation)=最大值滤波；开运算=先侵蚀再膨胀，去噪点；闭运算=先膨胀再侵蚀，填孔洞。"
        "考点：结构元素(SE)形状对结果的影响；Hit-or-Miss 变换用于形状检测。"
    ),
    "Thresholding": (
        "全局阈值（Otsu 最大类间方差）；自适应阈值（分块均值/高斯加权）。"
        "Otsu 目标：最大化 σ²_B = w0·w1·(μ0-μ1)²。考点：多阈值分割；噪声对阈值选择的影响。"
    ),
    "Sampling & Quantization": (
        "采样：连续→离散空间（奈奎斯特定理：采样率 ≥ 2·最高频率，否则混叠）。"
        "量化：连续幅值→离散灰度级，B bits → 2^B 灰度级，影响图像质量与文件大小。"
    ),
}

# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------


def _strip_json_raw(raw: str) -> str:
    """Remove markdown code fences and surrounding whitespace."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def _try_parse_tree_json(raw: str) -> dict[str, Any]:
    """Parse JSON from LLM output; return EMPTY_TREE on failure."""
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
    return EMPTY_TREE.copy()


# ---------------------------------------------------------------------------
# Tree validation
# ---------------------------------------------------------------------------


def _validate_tree(obj: Any, depth: int = 0, max_depth: int = 8) -> dict[str, Any]:
    """
    Recursively validate tree node structure.
    Ensures name/description/children exist.
    If description is too short, attempts enrichment from KNOWN_DESCRIPTIONS.
    """
    if not isinstance(obj, dict):
        return EMPTY_TREE.copy()

    # Support bilingual fields (name_zh/name_en) with fallback to name
    name_zh = str(obj.get("name_zh") or obj.get("name") or "").strip()
    name_en = str(obj.get("name_en") or name_zh).strip()
    name = name_zh or "Unknown"

    desc_zh = str(obj.get("desc_zh") or obj.get("description") or "").strip()
    desc_en = str(obj.get("desc_en") or desc_zh).strip()
    description = desc_zh

    # Enrich short descriptions from known table
    if len(description) < 20:
        description = KNOWN_DESCRIPTIONS.get(name, description or f"{name} 的核心概念与考点。")
        desc_zh = description
        if len(desc_en) < 20:
            desc_en = description

    children_raw = obj.get("children")
    if not isinstance(children_raw, list):
        children_raw = []

    children: list[dict[str, Any]] = []
    if depth < max_depth - 1:
        for child in children_raw:
            validated = _validate_tree(child, depth + 1, max_depth)
            children.append(validated)

    return {
        "name": name,
        "name_zh": name_zh,
        "name_en": name_en,
        "description": description,
        "desc_zh": desc_zh,
        "desc_en": desc_en,
        "children": children,
    }


# ---------------------------------------------------------------------------
# Legacy format compatibility
# ---------------------------------------------------------------------------


def is_legacy_graph_format(data: dict) -> bool:
    """Return True if data is in the old nodes/links format (not tree format)."""
    return (
        isinstance(data, dict)
        and "nodes" in data
        and "links" in data
        and "children" not in data
    )


def flat_graph_to_tree(flat: dict) -> dict[str, Any]:
    """
    Convert legacy nodes/links graph format to nested tree format.
    Finds root nodes (category=0 with no incoming links), builds tree by adjacency.
    """
    nodes: list[dict] = flat.get("nodes") or []
    links: list[dict] = flat.get("links") or []

    if not nodes:
        return EMPTY_TREE.copy()

    # Build adjacency list (parent -> children)
    children_map: dict[str, list[str]] = {n["name"]: [] for n in nodes if n.get("name")}
    all_targets: set[str] = set()
    for link in links:
        src = str(link.get("source", "")).strip()
        tgt = str(link.get("target", "")).strip()
        if src in children_map and tgt in children_map:
            children_map[src].append(tgt)
            all_targets.add(tgt)

    # Find root candidates: category 0 nodes not pointed to by others
    name_to_node: dict[str, dict] = {n["name"]: n for n in nodes if n.get("name")}
    roots = [
        name
        for name, node in name_to_node.items()
        if node.get("category", 1) == 0 and name not in all_targets
    ]
    # Fallback: any node not in all_targets
    if not roots:
        roots = [name for name in name_to_node if name not in all_targets]
    # Last resort: first node
    if not roots:
        roots = [nodes[0]["name"]]

    def _build_node(name: str, visited: set[str]) -> dict[str, Any]:
        if name in visited:
            return {"name": name, "description": "", "children": []}
        visited = visited | {name}
        node_data = name_to_node.get(name, {})
        desc = str(node_data.get("description") or "").strip()
        if len(desc) < 20:
            desc = KNOWN_DESCRIPTIONS.get(name, desc or f"{name} 的核心概念。")
        child_names = children_map.get(name, [])
        children = [_build_node(c, visited) for c in child_names]
        return {
            "name": name,
            "name_zh": name,
            "name_en": name,
            "description": desc,
            "desc_zh": desc,
            "desc_en": desc,
            "children": children,
        }

    if len(roots) == 1:
        return _build_node(roots[0], set())

    # Multiple roots: wrap under a synthetic root
    visited: set[str] = set()
    root_children = [_build_node(r, visited) for r in roots]
    return {
        "name": "Knowledge Map",
        "description": "课程知识图谱总览",
        "children": root_children,
    }


# ---------------------------------------------------------------------------
# GraphGenerator
# ---------------------------------------------------------------------------


class GraphGenerator:
    """Extracts hierarchical concept tree from text for ECharts tree visualization."""

    def __init__(self) -> None:
        self._llm = LLMProcessor()

    def generate_graph_data(self, text: str, api_key: str = "") -> dict[str, Any]:
        """
        Extract nested tree from course text.

        Args:
            text: Raw course material text.
            api_key: OpenAI API key.

        Returns:
            Dict with nested tree structure (name/description/children).
            Returns EMPTY_TREE on failure.
        """
        if not (api_key and api_key.strip()):
            return EMPTY_TREE.copy()

        user_message = (
            "请从以下课程内容中构建分层知识树（嵌套 JSON）："
            "根节点=总主题，第1层=关键概念(3-8个)，第2层及以下=具体细节/公式(每组2-6个，可继续细分)。"
            "每节点必须含 name_zh（中文名）、name_en（英文名）、name（同name_zh）、"
            "desc_zh（中文描述30-100字含公式/考点）、desc_en（英文描述30-100字）、"
            "description（同desc_zh）、children（列表）。只输出 JSON，无其他文字。\n\n"
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
            return EMPTY_TREE.copy()

        if not raw:
            return EMPTY_TREE.copy()

        parsed = _try_parse_tree_json(raw)
        return _validate_tree(parsed)
