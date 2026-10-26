import unicodedata
from collections import deque
from dataclasses import dataclass
from typing import Iterator, List, Optional, Sequence, Tuple

from Models.Errors import (
    DuplicateNodeError,
    InvalidTreeDataError,
    NodeNotFoundError,
    ProtectedRootError,
    ValidationError,
)
from Models.MusicNode import MusicNode

ROOT_LEVEL = 1
STRATEGY_BRANCH = "branch"
STRATEGY_PROMOTE = "promote"


@dataclass(frozen=True)
class TreeStats:
    height: int
    weight: int
    leaf_count: int
    branch_count: int
    max_degree: int


@dataclass(frozen=True)
class NodeProfile:
    node: MusicNode
    level: int
    descendants: int


def normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


class MusicTree:
    def __init__(self):
        self._root: Optional[MusicNode] = None

    @property
    def root(self) -> Optional[MusicNode]:
        return self._root

    @property
    def is_empty(self) -> bool:
        return self._root is None

    def set_root(self, node: MusicNode) -> None:
        if self._root is not None:
            raise ValidationError("El árbol ya tiene una composición raíz.")
        if node.parent_id is not None:
            raise ValidationError("La composición raíz no puede tener versión padre.")
        if node.children:
            raise ValidationError("La raíz nueva no puede traer hijos asociados.")
        self._root = node

    def insert(self, parent_id: str, node: MusicNode) -> None:
        if self._root is None:
            raise ValidationError("El árbol está vacío: crea primero la composición raíz.")
        if node.parent_id != parent_id:
            raise ValidationError("El padre declarado en la variación no coincide con el padre indicado.")
        if node.children:
            raise ValidationError("Una variación nueva no puede traer hijos asociados.")
        parent = None
        for current, _ in self.dfs_with_level():
            if current.node_id == node.node_id:
                raise DuplicateNodeError(f"Ya existe una versión con el identificador «{node.node_id}».")
            if current.node_id == parent_id:
                parent = current
        if parent is None:
            raise NodeNotFoundError(f"La versión padre «{parent_id}» no existe.")
        parent._attach_child(node)

    def dfs_with_level(self) -> Iterator[Tuple[MusicNode, int]]:
        if self._root is None:
            return
        stack = [(self._root, ROOT_LEVEL)]
        while stack:
            node, level = stack.pop()
            yield node, level
            for child in reversed(node.children):
                stack.append((child, level + 1))

    def bfs_with_level(self) -> Iterator[Tuple[MusicNode, int]]:
        if self._root is None:
            return
        queue = deque([(self._root, ROOT_LEVEL)])
        while queue:
            node, level = queue.popleft()
            yield node, level
            for child in node.children:
                queue.append((child, level + 1))

    def _start_node(self, start_id: Optional[str]) -> Optional[MusicNode]:
        if start_id is None:
            return self._root
        node = self.find_by_id(start_id)
        if node is None:
            raise NodeNotFoundError(f"La versión «{start_id}» no existe.")
        return node

    def dfs(self, start_id: Optional[str] = None) -> Iterator[MusicNode]:
        start = self._start_node(start_id)
        return self._subtree(start)

    @staticmethod
    def _subtree(start: Optional[MusicNode]) -> Iterator[MusicNode]:
        if start is None:
            return
        stack = [start]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.children))

    def bfs(self, start_id: Optional[str] = None) -> Iterator[MusicNode]:
        start = self._start_node(start_id)
        return self._bfs_from(start)

    @staticmethod
    def _bfs_from(start: Optional[MusicNode]) -> Iterator[MusicNode]:
        if start is None:
            return
        queue = deque([start])
        while queue:
            node = queue.popleft()
            yield node
            queue.extend(node.children)

    def bfs_levels(self) -> List[List[MusicNode]]:
        levels: List[List[MusicNode]] = []
        for node, level in self.bfs_with_level():
            if level > len(levels):
                levels.append([])
            levels[level - 1].append(node)
        return levels

    def find_by_id(self, node_id: str) -> Optional[MusicNode]:
        for node in self._subtree(self._root):
            if node.node_id == node_id:
                return node
        return None

    def find_by_name(self, text: str) -> List[MusicNode]:
        needle = normalize_text((text or "").strip())
        if not needle:
            raise ValidationError("Escribe parte del nombre que quieres buscar.")
        return [node for node in self._subtree(self._root) if needle in normalize_text(node.name)]

    def path_to(self, node_id: str) -> Tuple[MusicNode, ...]:
        path: List[MusicNode] = []
        stack = [(self._root, 0)] if self._root is not None else []
        while stack:
            node, depth = stack.pop()
            del path[depth:]
            path.append(node)
            if node.node_id == node_id:
                return tuple(path)
            for child in reversed(node.children):
                stack.append((child, depth + 1))
        raise NodeNotFoundError(f"La versión «{node_id}» no existe.")

    def level_of(self, node_id: str) -> int:
        return len(self.path_to(node_id))

    def parent_of(self, node_id: str) -> Optional[MusicNode]:
        path = self.path_to(node_id)
        return path[-2] if len(path) > 1 else None

    def siblings_of(self, node_id: str) -> Tuple[MusicNode, ...]:
        path = self.path_to(node_id)
        if len(path) == 1:
            return ()
        return tuple(child for child in path[-2].children if child is not path[-1])

    def degree_of(self, node_id: str) -> int:
        node = self.find_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"La versión «{node_id}» no existe.")
        return node.degree

    def descendants_count(self, node_id: str) -> int:
        node = self.find_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"La versión «{node_id}» no existe.")
        return sum(1 for _ in self._subtree(node)) - 1

    def height(self) -> int:
        return max((level for _, level in self.dfs_with_level()), default=0)

    def weight(self) -> int:
        return sum(1 for _ in self._subtree(self._root))

    def max_degree(self) -> int:
        return max((node.degree for node in self._subtree(self._root)), default=0)

    def leaves(self) -> List[MusicNode]:
        return [node for node in self._subtree(self._root) if node.is_leaf]

    def leaf_count(self) -> int:
        return sum(1 for node in self._subtree(self._root) if node.is_leaf)

    def kind_of(self, node: MusicNode) -> str:
        if node is self._root:
            return "Raíz"
        return "Hoja" if node.is_leaf else "Rama"

    def stats(self) -> TreeStats:
        height = weight = leaves = branches = max_degree = 0
        for node, level in self.dfs_with_level():
            weight += 1
            height = max(height, level)
            max_degree = max(max_degree, node.degree)
            if node.is_leaf:
                leaves += 1
            elif node is not self._root:
                branches += 1
        return TreeStats(height, weight, leaves, branches, max_degree)

    def profiles(self) -> List[NodeProfile]:
        entries = list(self.dfs_with_level())
        sizes: List[int] = [0] * len(entries)
        pending: List[Tuple[int, int]] = []
        for index in range(len(entries) - 1, -1, -1):
            level = entries[index][1]
            size = 1
            while pending and pending[-1][0] > level:
                size += pending.pop()[1]
            pending.append((level, size))
            sizes[index] = size
        return [
            NodeProfile(node, level, sizes[index] - 1)
            for index, (node, level) in enumerate(entries)
        ]

    def lowest_common_ancestor(self, first_id: str, second_id: str) -> Optional[MusicNode]:
        first, second = self.path_to(first_id), self.path_to(second_id)
        common = None
        for left, right in zip(first, second):
            if left is not right:
                break
            common = left
        return common

    def delete_node(self, node_id: str, strategy: str = STRATEGY_BRANCH) -> List[MusicNode]:
        if strategy not in (STRATEGY_BRANCH, STRATEGY_PROMOTE):
            raise ValidationError("Estrategia de eliminación no reconocida.")
        path = self.path_to(node_id)
        if len(path) == 1:
            raise ProtectedRootError(
                "La composición raíz no se elimina como variación: usa la eliminación de composición completa."
            )
        node, parent = path[-1], path[-2]
        if strategy == STRATEGY_BRANCH:
            removed = list(self._subtree(node))
            parent._detach_child(node)
            return removed
        parent._replace_child(node, node.children)
        node._clear_children()
        return [node]

    def validate_integrity(self) -> List[str]:
        problems: List[str] = []
        if self._root is None:
            return problems
        if self._root.parent_id is not None:
            problems.append(f"La raíz «{self._root.node_id}» declara un padre.")
        seen_objects, seen_ids = set(), set()
        stack = [self._root]
        while stack:
            node = stack.pop()
            if id(node) in seen_objects:
                problems.append(f"Ciclo o nodo compartido en «{node.node_id}».")
                continue
            seen_objects.add(id(node))
            if node.node_id in seen_ids:
                problems.append(f"Identificador duplicado «{node.node_id}».")
            seen_ids.add(node.node_id)
            for child in node.children:
                if child.parent_id != node.node_id:
                    problems.append(f"«{child.node_id}» declara el padre «{child.parent_id}» pero cuelga de «{node.node_id}».")
                stack.append(child)
        return problems

    def to_records(self) -> List[dict]:
        return [node.to_record() for node in self.bfs()]

    @classmethod
    def from_records(cls, records: Sequence[dict]) -> "MusicTree":
        if not records:
            raise InvalidTreeDataError("Una composición guardada no contiene versiones.")
        nodes: List[MusicNode] = []
        index = {}
        for record in records:
            try:
                node = MusicNode.from_record(record)
            except ValidationError as error:
                raise InvalidTreeDataError(str(error))
            if node.node_id in index:
                raise InvalidTreeDataError(f"Identificador duplicado «{node.node_id}» en los datos guardados.")
            index[node.node_id] = node
            nodes.append(node)
        roots = [node for node in nodes if node.parent_id is None]
        if len(roots) != 1:
            raise InvalidTreeDataError("Cada composición guardada debe tener exactamente una raíz.")
        for node in nodes:
            if node.parent_id is None:
                continue
            parent = index.get(node.parent_id)
            if parent is None:
                raise InvalidTreeDataError(f"La versión «{node.node_id}» referencia un padre inexistente.")
            parent._attach_child(node)
        tree = cls()
        tree._root = roots[0]
        if tree.weight() != len(nodes):
            raise InvalidTreeDataError("Hay versiones desconectadas de la raíz (posible ciclo).")
        problems = tree.validate_integrity()
        if problems:
            raise InvalidTreeDataError(problems[0])
        return tree
