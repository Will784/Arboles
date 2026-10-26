import math
import re
from dataclasses import dataclass
from typing import Optional, Tuple

from Models.Errors import ValidationError

PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
REST = "R"
MIN_OCTAVE = 0
MAX_OCTAVE = 8
DEFAULT_OCTAVE = 4
MAX_BEATS = 16.0
BEAT_STEP = 0.25
MAX_SEQUENCE_LENGTH = 512

_FLAT_TO_SHARP = {"DB": "C#", "EB": "D#", "GB": "F#", "AB": "G#", "BB": "A#"}
_TOKEN = re.compile(
    r"^(?P<letter>[A-Ga-gRr])(?P<accidental>[#b]?)(?P<octave>\d?)(?::(?P<beats>\d+(?:\.\d+)?))?$"
)
_FORMAT_HINT = "Usa el formato C4:1, F#3:0.5, Bb4:2 o R:1 (silencio)."


@dataclass(frozen=True)
class Note:
    pitch_class: str
    octave: Optional[int]
    beats: float

    def __post_init__(self):
        if self.pitch_class == REST:
            if self.octave is not None:
                raise ValidationError("Un silencio no tiene octava.")
        elif self.pitch_class in PITCH_CLASSES:
            valid_octave = (
                isinstance(self.octave, int)
                and not isinstance(self.octave, bool)
                and MIN_OCTAVE <= self.octave <= MAX_OCTAVE
            )
            if not valid_octave:
                raise ValidationError(f"La octava debe estar entre {MIN_OCTAVE} y {MAX_OCTAVE}.")
        else:
            raise ValidationError(f"Nota no válida: {self.pitch_class!r}.")
        if isinstance(self.beats, bool) or not isinstance(self.beats, (int, float)):
            raise ValidationError("La duración debe ser un número.")
        beats = float(self.beats)
        if not math.isfinite(beats) or not 0 < beats <= MAX_BEATS or round(beats * 4) != beats * 4:
            raise ValidationError(
                f"La duración debe ser múltiplo de {BEAT_STEP} pulsos y estar entre {BEAT_STEP} y {MAX_BEATS:g}."
            )
        object.__setattr__(self, "beats", beats)

    @property
    def is_rest(self) -> bool:
        return self.pitch_class == REST

    @property
    def midi_number(self) -> Optional[int]:
        if self.is_rest:
            return None
        return (self.octave + 1) * 12 + PITCH_CLASSES.index(self.pitch_class)

    @property
    def frequency(self) -> Optional[float]:
        midi = self.midi_number
        return None if midi is None else 440.0 * 2 ** ((midi - 69) / 12)

    def to_token(self) -> str:
        if self.is_rest:
            return f"{REST}:{self.beats:g}"
        return f"{self.pitch_class}{self.octave}:{self.beats:g}"

    @classmethod
    def parse(cls, token) -> "Note":
        match = _TOKEN.match(token.strip()) if isinstance(token, str) else None
        if not match:
            raise ValidationError(f"No se entiende la nota «{token}». {_FORMAT_HINT}")
        letter = match["letter"].upper()
        accidental = match["accidental"]
        beats = float(match["beats"]) if match["beats"] else 1.0
        if letter == REST:
            if accidental or match["octave"]:
                raise ValidationError(f"Un silencio solo lleva duración. {_FORMAT_HINT}")
            return cls(REST, None, beats)
        if accidental == "#":
            name = letter + "#"
        elif accidental == "b":
            name = _FLAT_TO_SHARP.get(letter + "B")
        else:
            name = letter
        if name not in PITCH_CLASSES:
            raise ValidationError(f"La nota «{token}» no es válida. {_FORMAT_HINT}")
        octave = int(match["octave"]) if match["octave"] else DEFAULT_OCTAVE
        return cls(name, octave, beats)

    @staticmethod
    def parse_sequence(text: str) -> Tuple["Note", ...]:
        tokens = [token for token in re.split(r"[\s,;]+", (text or "").strip()) if token]
        if not tokens:
            raise ValidationError("Agrega al menos una nota a la secuencia.")
        if len(tokens) > MAX_SEQUENCE_LENGTH:
            raise ValidationError(f"La secuencia no puede superar {MAX_SEQUENCE_LENGTH} notas.")
        return tuple(Note.parse(token) for token in tokens)
