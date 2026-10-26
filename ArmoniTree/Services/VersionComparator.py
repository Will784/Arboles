from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Tuple

from Models.MusicNode import MusicNode

_TAGS = {"equal": "igual", "replace": "reemplazo", "delete": "solo en A", "insert": "solo en B"}


@dataclass(frozen=True)
class FieldDifference:
    label: str
    left: str
    right: str

    @property
    def changed(self) -> bool:
        return self.left != self.right


@dataclass(frozen=True)
class NoteChange:
    kind: str
    left: Tuple[str, ...]
    right: Tuple[str, ...]


@dataclass(frozen=True)
class VersionComparison:
    fields: Tuple[FieldDifference, ...]
    note_changes: Tuple[NoteChange, ...]
    similarity: float

    @property
    def identical(self) -> bool:
        return not any(field.changed for field in self.fields if field.label != "Fecha de creación") and all(
            change.kind == "igual" for change in self.note_changes
        )


class VersionComparator:
    def compare(self, left: MusicNode, right: MusicNode) -> VersionComparison:
        fields = (
            self._field("Nombre", left.name, right.name),
            self._field("Tonalidad", left.key or "Sin definir", right.key or "Sin definir"),
            self._field("Tempo (pulsos/min)", str(left.tempo_bpm), str(right.tempo_bpm)),
            self._field("Compás", left.time_signature, right.time_signature),
            self._field("Cantidad de notas", str(len(left.notes)), str(len(right.notes))),
            self._field("Duración total (pulsos)", f"{left.total_beats:g}", f"{right.total_beats:g}"),
            self._field("Descripción", left.description or "—", right.description or "—"),
            self._field("Fecha de creación", left.created_at, right.created_at),
        )
        left_tokens = [note.to_token() for note in left.notes]
        right_tokens = [note.to_token() for note in right.notes]
        matcher = SequenceMatcher(a=left_tokens, b=right_tokens, autojunk=False)
        changes = tuple(
            NoteChange(_TAGS[tag], tuple(left_tokens[a1:a2]), tuple(right_tokens[b1:b2]))
            for tag, a1, a2, b1, b2 in matcher.get_opcodes()
        )
        return VersionComparison(fields, changes, matcher.ratio())

    @staticmethod
    def _field(label: str, left: str, right: str) -> FieldDifference:
        return FieldDifference(label, left, right)
