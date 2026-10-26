from Models.Note import Note
from Services.CompositionManager import CompositionManager

BASE = "A4:1 C5:1 D5:1 E5:2 D5:1 C5:1 A4:2 G4:1 A4:1 C5:1 D5:2 R:1 E5:1 D5:1 C5:1 A4:1"


def _notes(text: str):
    return Note.parse_sequence(text)


def build_demo(manager: CompositionManager):
    tree = manager.create_composition(
        name="Motivo andino (ejemplo)",
        notes=_notes(BASE),
        tempo_bpm=96,
        time_signature="4/4",
        key="A menor",
        description="Motivo de ejemplo sobre la escala pentatónica de La menor (A C D E G), creado para demostrar el árbol.",
    )
    root_id = tree.root.node_id

    def add(parent_id, name, notes, tempo, signature, key, description):
        return manager.add_variation(parent_id, name, _notes(notes), tempo, signature, key, description).node_id

    slow = add(root_id, "Versión lenta", BASE, 72, "4/4", "A menor",
               "Mismo motivo con el tempo reducido de 96 a 72 pulsos por minuto.")
    add(slow, "Lenta con adorno", "A4:1 C5:1 D5:1 E5:1 G5:0.5 E5:0.5 D5:1 C5:1 A4:2 G4:1 A4:1 C5:1 D5:2 R:1 E5:1 D5:1 C5:1 A4:1",
        72, "4/4", "A menor", "Se reemplaza la nota larga E5 por un adorno E5-G5-E5.")
    add(slow, "Lenta en octava grave",
        "A3:1 C4:1 D4:1 E4:2 D4:1 C4:1 A3:2 G3:1 A3:1 C4:1 D4:2 R:1 E4:1 D4:1 C4:1 A3:1",
        72, "4/4", "A menor", "Todo el motivo bajado una octava para un instrumento grave.")
    six_eight = add(root_id, "Ritmo en 6/8",
                    "A4:1.5 C5:0.5 D5:1 E5:2 D5:1.5 C5:0.5 A4:1 G4:1 A4:0.5 C5:0.5 D5:2 R:1 E5:0.5 D5:0.5 C5:0.5 A4:1.5",
                    96, "6/8", "A menor", "Redistribución de duraciones para un pulso ternario en 6/8.")
    syncopated = add(six_eight, "6/8 con síncopa",
                     "A4:0.5 C5:1 D5:0.5 E5:2 D5:0.5 C5:1 A4:0.5 G4:1.5 A4:0.5 C5:1 D5:2 R:1 E5:0.5 D5:0.5 C5:0.5 A4:1.5",
                     96, "6/8", "A menor", "Se desplazan los acentos para crear síncopa.")
    add(syncopated, "6/8 síncopa con final largo",
        "A4:0.5 C5:1 D5:0.5 E5:2 D5:0.5 C5:1 A4:0.5 G4:1.5 A4:0.5 C5:1 D5:2 R:1 E5:0.5 D5:0.5 C5:0.5 A4:4",
        96, "6/8", "A menor", "La nota final se alarga a cuatro pulsos para cerrar la frase.")
    add(root_id, "Transposición a D menor",
        "D5:1 F5:1 G5:1 A5:2 G5:1 F5:1 D5:2 C5:1 D5:1 F5:1 G5:2 R:1 A5:1 G5:1 F5:1 D5:1",
        96, "4/4", "D menor", "Todo el motivo subido una cuarta justa (de La menor a Re menor).")
    return tree
