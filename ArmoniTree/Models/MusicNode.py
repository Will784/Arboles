import re
import uuid
from datetime import datetime
from typing import Iterable, Optional, Tuple

from Models.Errors import ValidationError
from Models.Note import MAX_SEQUENCE_LENGTH, PITCH_CLASSES, Note

KEYS = tuple(f"{pitch} {mode}" for pitch in PITCH_CLASSES for mode in ("mayor", "menor"))
TIME_SIGNATURES = ("2/4", "3/4", "4/4", "6/8", "12/8")
MIN_TEMPO = 20
MAX_TEMPO = 300
MAX_NAME_LENGTH = 60
MAX_DESCRIPTION_LENGTH = 500
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


class MusicNode:
    __slots__ = (
        "_node_id", "_name", "_parent_id", "_notes", "_tempo_bpm",
        "_time_signature", "_key", "_description", "_created_at", "_children",
    )

    def __init__(
        self,
        name: str,
        notes: Iterable[Note],
        parent_id: Optional[str] = None,
        tempo_bpm: int = 100,
        time_signature: str = "4/4",
        key: Optional[str] = None,
        description: str = "",
        node_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ):
        self._node_id = self._validate_id(node_id or uuid.uuid4().hex[:8], "El identificador")
        self._parent_id = None if parent_id is None else self._validate_id(parent_id, "El identificador del padre")
        if self._parent_id == self._node_id:
            raise ValidationError("Una versión no puede ser su propio padre.")
        self._name = self._validate_name(name)
        self._notes = self._validate_notes(notes)
        self._tempo_bpm = self._validate_tempo(tempo_bpm)
        if time_signature not in TIME_SIGNATURES:
            raise ValidationError(f"Compás no válido. Opciones: {', '.join(TIME_SIGNATURES)}.")
        self._time_signature = time_signature
        if key is not None and key not in KEYS:
            raise ValidationError("Tonalidad no válida.")
        self._key = key
        description = (description or "").strip()
        if len(description) > MAX_DESCRIPTION_LENGTH:
            raise ValidationError(f"La descripción no puede superar {MAX_DESCRIPTION_LENGTH} caracteres.")
        self._description = description
        self._created_at = self._validate_date(created_at)
        self._children = []

    @staticmethod
    def _validate_id(value, label: str) -> str:
        if not isinstance(value, str) or not _ID_PATTERN.match(value):
            raise ValidationError(f"{label} solo admite letras, números, «-» y «_» (máximo 32 caracteres).")
        return value

    @staticmethod
    def _validate_name(name) -> str:
        name = name.strip() if isinstance(name, str) else ""
        if not name:
            raise ValidationError("El nombre no puede estar vacío.")
        if len(name) > MAX_NAME_LENGTH:
            raise ValidationError(f"El nombre no puede superar {MAX_NAME_LENGTH} caracteres.")
        return name

    @staticmethod
    def _validate_notes(notes) -> Tuple[Note, ...]:
        notes = tuple(notes) if notes is not None else ()
        if not notes:
            raise ValidationError("Agrega al menos una nota.")
        if len(notes) > MAX_SEQUENCE_LENGTH:
            raise ValidationError(f"Se permiten máximo {MAX_SEQUENCE_LENGTH} notas.")
        if not all(isinstance(note, Note) for note in notes):
            raise ValidationError("La secuencia contiene elementos que no son notas.")
        return notes

    @staticmethod
    def _validate_tempo(tempo) -> int:
        valid = isinstance(tempo, (int, float)) and not isinstance(tempo, bool) and int(tempo) == tempo
        if not valid or not MIN_TEMPO <= tempo <= MAX_TEMPO:
            raise ValidationError(f"El tempo debe ser un entero entre {MIN_TEMPO} y {MAX_TEMPO}.")
        return int(tempo)

    @staticmethod
    def _validate_date(value) -> str:
        if value is None:
            return datetime.now().isoformat(timespec="seconds")
        try:
            datetime.fromisoformat(value)
        except (TypeError, ValueError):
            raise ValidationError("Fecha de creación no válida.")
        return value

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def parent_id(self) -> Optional[str]:
        return self._parent_id

    @property
    def notes(self) -> Tuple[Note, ...]:
        return self._notes

    @property
    def tempo_bpm(self) -> int:
        return self._tempo_bpm

    @property
    def time_signature(self) -> str:
        return self._time_signature

    @property
    def key(self) -> Optional[str]:
        return self._key

    @property
    def description(self) -> str:
        return self._description

    @property
    def created_at(self) -> str:
        return self._created_at

    @property
    def children(self) -> Tuple["MusicNode", ...]:
        return tuple(self._children)

    @property
    def degree(self) -> int:
        return len(self._children)

    @property
    def is_leaf(self) -> bool:
        return not self._children

    @property
    def total_beats(self) -> float:
        return sum(note.beats for note in self._notes)

    def same_content_as(self, other: "MusicNode") -> bool:
        return (
            self._notes == other._notes
            and self._tempo_bpm == other._tempo_bpm
            and self._time_signature == other._time_signature
            and self._key == other._key
        )

    def _attach_child(self, child: "MusicNode") -> None:
        self._children.append(child)

    def _detach_child(self, child: "MusicNode") -> None:
        for index, candidate in enumerate(self._children):
            if candidate is child:
                del self._children[index]
                return

    def _replace_child(self, child: "MusicNode", replacements) -> None:
        for index, candidate in enumerate(self._children):
            if candidate is child:
                for item in replacements:
                    item._parent_id = self._node_id
                self._children[index:index + 1] = list(replacements)
                return

    def _clear_children(self) -> None:
        self._children = []

    def to_record(self) -> dict:
        return {
            "id": self._node_id,
            "name": self._name,
            "parent_id": self._parent_id,
            "notes": [note.to_token() for note in self._notes],
            "tempo_bpm": self._tempo_bpm,
            "time_signature": self._time_signature,
            "key": self._key,
            "description": self._description,
            "created_at": self._created_at,
        }

    @classmethod
    def from_record(cls, record: dict) -> "MusicNode":
        try:
            return cls(
                name=record["name"],
                notes=[Note.parse(token) for token in record["notes"]],
                parent_id=record["parent_id"],
                tempo_bpm=record["tempo_bpm"],
                time_signature=record["time_signature"],
                key=record["key"],
                description=record["description"],
                node_id=record["id"],
                created_at=record["created_at"],
            )
        except (KeyError, TypeError) as error:
            raise ValidationError(f"Registro de versión incompleto o corrupto: {error!r}")

    def __repr__(self) -> str:
        return f"MusicNode(id={self._node_id!r}, name={self._name!r}, children={len(self._children)})"
