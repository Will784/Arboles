import textwrap
from typing import Optional

from Structures.MusicTree import MusicTree

ROOT_COLOR = "#F4B23E"
BRANCH_COLOR = "#9CC3EE"
LEAF_COLOR = "#96D37A"
HIGHLIGHT_COLOR = "#C2410C"
EDGE_COLOR = "#6B7280"

LEGEND = (
    ("Raíz (composición original)", ROOT_COLOR),
    ("Rama (versión con variaciones)", BRANCH_COLOR),
    ("Hoja (sin descendientes)", LEAF_COLOR),
)


class TreeVisualizer:
    @staticmethod
    def _escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"')

    def build_dot(self, tree: MusicTree, selected_id: Optional[str] = None) -> str:
        lines = [
            "digraph ArmoniTree {",
            '  graph [rankdir=TB, bgcolor="transparent", nodesep=0.35, ranksep=0.55];',
            '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, fontcolor="#1F2937", color="#4B5563"];',
            f'  edge [color="{EDGE_COLOR}", arrowsize=0.7];',
        ]
        if tree.is_empty:
            lines.append("}")
            return "\n".join(lines)
        path_ids = {node.node_id for node in tree.path_to(selected_id)} if selected_id else set()
        for node, level in tree.dfs_with_level():
            fill = {"Raíz": ROOT_COLOR, "Rama": BRANCH_COLOR, "Hoja": LEAF_COLOR}[tree.kind_of(node)]
            title = "\\n".join(self._escape(line) for line in textwrap.wrap(node.name, 22) or [node.name])
            label = f"{title}\\n[{self._escape(node.node_id)}] · nivel {level}"
            extra = f', color="{HIGHLIGHT_COLOR}", penwidth=3' if node.node_id == selected_id else ""
            lines.append(f'  "{self._escape(node.node_id)}" [label="{label}", fillcolor="{fill}"{extra}];')
        for node, _ in tree.dfs_with_level():
            for child in node.children:
                on_path = node.node_id in path_ids and child.node_id in path_ids
                extra = f' [color="{HIGHLIGHT_COLOR}", penwidth=2]' if on_path else ""
                lines.append(f'  "{self._escape(node.node_id)}" -> "{self._escape(child.node_id)}"{extra};')
        lines.append("}")
        return "\n".join(lines)

    @staticmethod
    def build_outline(tree: MusicTree) -> str:
        return "\n".join(
            f"{'    ' * (level - 1)}{'└── ' if level > 1 else ''}{node.name} [{node.node_id}]"
            for node, level in tree.dfs_with_level()
        )
