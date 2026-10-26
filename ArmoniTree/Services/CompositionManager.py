import json
import os
import uuid
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from Models.Errors import (
    ArmoniTreeError,
    NodeNotFoundError,
    PersistenceError,
    ProtectedRootError,
    ValidationError,
)
from Models.MusicNode import MusicNode
from Models.Note import Note
from Structures.MusicTree import STRATEGY_BRANCH, MusicTree

FORMAT_NAME = "armonitree"
FORMAT_VERSION = 1


class CompositionManager:
    def __init__(self, storage_path):
        self._path = Path(storage_path)
        self._trees: List[MusicTree] = []
        self.load()

    @property
    def storage_path(self) -> Path:
        return self._path

    @property
    def compositions(self) -> Tuple[MusicTree, ...]:
        return tuple(self._trees)

    def get_tree(self, root_id: str) -> MusicTree:
        for tree in self._trees:
            if tree.root.node_id == root_id:
                return tree
        raise NodeNotFoundError(f"La composición «{root_id}» no existe.")

    def find_node(self, node_id: str) -> Tuple[MusicTree, MusicNode]:
        for tree in self._trees:
            node = tree.find_by_id(node_id)
            if node is not None:
                return tree, node
        raise NodeNotFoundError(f"La versión «{node_id}» no existe.")

    def search_by_name(self, text: str) -> List[Tuple[MusicTree, MusicNode]]:
        results = []
        for tree in self._trees:
            results.extend((tree, node) for node in tree.find_by_name(text))
        return results

    def all_versions(self) -> List[Tuple[MusicTree, MusicNode, int]]:
        return [(tree, node, level) for tree in self._trees for node, level in tree.dfs_with_level()]

    def global_stats(self) -> dict:
        totals = {"compositions": len(self._trees), "versions": 0, "leaves": 0, "max_height": 0, "max_degree": 0}
        for tree in self._trees:
            stats = tree.stats()
            totals["versions"] += stats.weight
            totals["leaves"] += stats.leaf_count
            totals["max_height"] = max(totals["max_height"], stats.height)
            totals["max_degree"] = max(totals["max_degree"], stats.max_degree)
        return totals

    def create_composition(
        self,
        name: str,
        notes: Sequence[Note],
        tempo_bpm: int,
        time_signature: str,
        key: Optional[str],
        description: str,
    ) -> MusicTree:
        node = MusicNode(
            name=name, notes=notes, parent_id=None, tempo_bpm=tempo_bpm,
            time_signature=time_signature, key=key, description=description,
            node_id=self._new_id(),
        )
        tree = MusicTree()
        tree.set_root(node)

        def action():
            self._trees.append(tree)
            return tree

        return self._mutate(action)

    def add_variation(
        self,
        parent_id: str,
        name: str,
        notes: Sequence[Note],
        tempo_bpm: int,
        time_signature: str,
        key: Optional[str],
        description: str,
    ) -> MusicNode:
        tree, parent = self.find_node(parent_id)
        if not (description or "").strip():
            raise ValidationError("Describe la modificación realizada en esta variación.")
        node = MusicNode(
            name=name, notes=notes, parent_id=parent_id, tempo_bpm=tempo_bpm,
            time_signature=time_signature, key=key, description=description,
            node_id=self._new_id(),
        )
        if node.same_content_as(parent):
            raise ValidationError(
                "La variación es idéntica a su versión base: modifica notas, tempo, compás o tonalidad."
            )

        def action():
            tree.insert(parent_id, node)
            return node

        return self._mutate(action)

    def delete_variation(self, node_id: str, strategy: str = STRATEGY_BRANCH) -> List[MusicNode]:
        tree, node = self.find_node(node_id)
        if tree.root is node:
            raise ProtectedRootError(
                "La composición raíz no se elimina como variación: usa la eliminación de composición completa."
            )
        return self._mutate(lambda: tree.delete_node(node_id, strategy))

    def delete_composition(self, root_id: str, confirmation_name: str) -> int:
        tree = self.get_tree(root_id)
        if (confirmation_name or "").strip() != tree.root.name:
            raise ValidationError("El nombre escrito no coincide con la composición: no se eliminó nada.")
        weight = tree.weight()

        def action():
            self._trees.remove(tree)
            return weight

        return self._mutate(action)

    def save(self) -> None:
        payload = self._to_payload()
        temp_path = self._path.with_name(self._path.name + ".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp_path, self._path)
        except OSError as error:
            raise PersistenceError(f"No se pudo guardar en {self._path}: {error}")

    def load(self) -> None:
        if not self._path.exists():
            self._trees = []
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise PersistenceError(f"No se pudo leer {self._path}: {error}")
        self._trees = self._from_payload(payload)

    def _to_payload(self) -> dict:
        return {
            "format": FORMAT_NAME,
            "version": FORMAT_VERSION,
            "compositions": [{"nodes": tree.to_records()} for tree in self._trees],
        }

    @staticmethod
    def _from_payload(payload) -> List[MusicTree]:
        if not isinstance(payload, dict) or payload.get("format") != FORMAT_NAME:
            raise PersistenceError("El archivo no tiene el formato de ArmoniTree.")
        entries = payload.get("compositions")
        if not isinstance(entries, list):
            raise PersistenceError("El archivo no contiene una lista de composiciones.")
        trees, seen_ids = [], set()
        for entry in entries:
            records = entry.get("nodes") if isinstance(entry, dict) else None
            tree = MusicTree.from_records(records or [])
            for node in tree.dfs():
                if node.node_id in seen_ids:
                    raise PersistenceError(f"Identificador «{node.node_id}» repetido entre composiciones.")
                seen_ids.add(node.node_id)
            trees.append(tree)
        return trees

    def _mutate(self, action: Callable):
        snapshot = self._to_payload()
        result = action()
        try:
            self.save()
        except PersistenceError:
            self._trees = self._from_payload(snapshot)
            raise
        return result

    def _new_id(self) -> str:
        while True:
            candidate = uuid.uuid4().hex[:8]
            try:
                self.find_node(candidate)
            except ArmoniTreeError:
                return candidate
