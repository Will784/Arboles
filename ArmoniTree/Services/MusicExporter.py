import io
import math
import struct
import sys
import wave
from array import array
from typing import Sequence

from Models.Errors import ValidationError
from Models.Note import Note

TICKS_PER_BEAT = 480
PAN_FLUTE_PROGRAM = 75
MAX_AUDIO_SECONDS = 300


class MusicExporter:
    def to_midi_bytes(
        self,
        notes: Sequence[Note],
        tempo_bpm: int,
        time_signature: str = "4/4",
        title: str = "ArmoniTree",
    ) -> bytes:
        self._require_notes(notes)
        numerator, denominator = (int(part) for part in time_signature.split("/"))
        title_bytes = title.encode("utf-8")
        track = bytearray()
        track += b"\x00\xff\x03" + self._vlq(len(title_bytes)) + title_bytes
        track += b"\x00\xff\x51\x03" + int(60_000_000 / tempo_bpm).to_bytes(3, "big")
        track += b"\x00\xff\x58\x04" + bytes([numerator, int(math.log2(denominator)), 24, 8])
        track += bytes([0x00, 0xC0, PAN_FLUTE_PROGRAM])
        pending_rest = 0
        for note in notes:
            ticks = round(note.beats * TICKS_PER_BEAT)
            if note.is_rest:
                pending_rest += ticks
                continue
            track += self._vlq(pending_rest) + bytes([0x90, note.midi_number, 80])
            track += self._vlq(ticks) + bytes([0x80, note.midi_number, 0])
            pending_rest = 0
        track += self._vlq(pending_rest) + b"\xff\x2f\x00"
        header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, TICKS_PER_BEAT)
        return header + b"MTrk" + struct.pack(">I", len(track)) + bytes(track)

    def to_wav_bytes(self, notes: Sequence[Note], tempo_bpm: int, sample_rate: int = 22050) -> bytes:
        self._require_notes(notes)
        seconds_per_beat = 60.0 / tempo_bpm
        if sum(note.beats for note in notes) * seconds_per_beat > MAX_AUDIO_SECONDS:
            raise ValidationError(f"La vista previa de audio se limita a {MAX_AUDIO_SECONDS} segundos.")
        samples = array("h")
        for note in notes:
            count = int(round(note.beats * seconds_per_beat * sample_rate))
            if note.is_rest:
                samples.extend([0] * count)
                continue
            freq = note.frequency
            attack = max(1, int(0.012 * sample_rate))
            release = max(1, int(0.05 * sample_rate))
            for index in range(count):
                envelope = min(1.0, index / attack, (count - index) / release)
                phase = 2 * math.pi * freq * index / sample_rate
                value = math.sin(phase) + 0.25 * math.sin(2 * phase) + 0.08 * math.sin(3 * phase)
                samples.append(int(9000 * envelope * value))
        if sys.byteorder == "big":
            samples.byteswap()
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate)
            handle.writeframes(samples.tobytes())
        return buffer.getvalue()

    @staticmethod
    def _require_notes(notes) -> None:
        if not notes:
            raise ValidationError("No hay notas para exportar.")

    @staticmethod
    def _vlq(value: int) -> bytes:
        chunks = [value & 0x7F]
        value >>= 7
        while value:
            chunks.append((value & 0x7F) | 0x80)
            value >>= 7
        return bytes(reversed(chunks))
