import json
import struct
import tempfile
import unittest
import wave
import io
from pathlib import Path
from unittest import mock

from Models.Errors import (
    DuplicateNodeError,
    InvalidTreeDataError,
    NodeNotFoundError,
    PersistenceError,
    ProtectedRootError,
    ValidationError,
)
from Models.MusicNode import MusicNode
from Models.Note import Note
from Services.CompositionManager import CompositionManager
from Services.MusicExporter import MusicExporter
from Services.VersionComparator import VersionComparator
from Structures.MusicTree import STRATEGY_BRANCH, STRATEGY_PROMOTE, MusicTree
from Utils.DemoComposition import build_demo
from Utils.TreeVisualizer import TreeVisualizer

NOTES = Note.parse_sequence("C4:1 D4:1 E4:2")


def make_node(node_id, parent_id=None, notes=NOTES, **kwargs):
    return MusicNode(name=f"Version {node_id}", notes=notes, parent_id=parent_id, node_id=node_id, **kwargs)


def build_sample():
    tree = MusicTree()
    tree.set_root(make_node("A"))
    for node_id, parent in (("B", "A"), ("C", "A"), ("D", "B"), ("E", "B"), ("F", "C"), ("G", "C"), ("H", "F")):
        tree.insert(parent, make_node(node_id, parent))
    return tree


def ids(nodes):
    return [node.node_id for node in nodes]


class TestNote(unittest.TestCase):
    def test_parse_valid_tokens(self):
        self.assertEqual(Note.parse("C4:1").midi_number, 60)
        self.assertEqual(Note.parse("A4:2").frequency, 440.0)
        self.assertEqual(Note.parse("Bb3:0.5").pitch_class, "A#")
        self.assertEqual(Note.parse("f#5").to_token(), "F#5:1")
        self.assertTrue(Note.parse("R:2").is_rest)
        self.assertEqual(Note.parse("D").octave, 4)

    def test_parse_invalid_tokens(self):
        for token in ("H4:1", "C4:0", "C4:17", "C4:1.3", "E#4:1", "R4:1", "C9:1", "", "C4:-1", None, "Cb4:1"):
            with self.assertRaises(ValidationError, msg=repr(token)):
                Note.parse(token)

    def test_parse_sequence(self):
        self.assertEqual(len(Note.parse_sequence("C4:1, D4:1;E4:2")), 3)
        with self.assertRaises(ValidationError):
            Note.parse_sequence("   ")
        with self.assertRaises(ValidationError):
            Note.parse_sequence("C4:1 XX")


class TestMusicNode(unittest.TestCase):
    def test_valid_node_defaults(self):
        node = make_node("A")
        self.assertTrue(node.is_leaf)
        self.assertEqual(node.degree, 0)
        self.assertEqual(node.total_beats, 4)

    def test_invalid_inputs(self):
        with self.assertRaises(ValidationError):
            MusicNode(name="  ", notes=NOTES)
        with self.assertRaises(ValidationError):
            MusicNode(name="x", notes=())
        with self.assertRaises(ValidationError):
            MusicNode(name="x", notes=NOTES, tempo_bpm=5)
        with self.assertRaises(ValidationError):
            MusicNode(name="x", notes=NOTES, tempo_bpm=100.5)
        with self.assertRaises(ValidationError):
            MusicNode(name="x", notes=NOTES, time_signature="5/4")
        with self.assertRaises(ValidationError):
            MusicNode(name="x", notes=NOTES, key="Z mayor")
        with self.assertRaises(ValidationError):
            MusicNode(name="x", notes=NOTES, node_id="bad id")
        with self.assertRaises(ValidationError):
            MusicNode(name="x", notes=NOTES, node_id="a", parent_id="a")
        with self.assertRaises(ValidationError):
            MusicNode(name="x" * 61, notes=NOTES)
        with self.assertRaises(ValidationError):
            MusicNode(name="x", notes=["C4"])
        with self.assertRaises(ValidationError):
            MusicNode(name="x", notes=NOTES, created_at="ayer")

    def test_children_view_is_read_only(self):
        tree = build_sample()
        children = tree.root.children
        self.assertIsInstance(children, tuple)
        self.assertEqual(tree.root.degree, 2)

    def test_record_round_trip(self):
        node = make_node("A", key="A menor", tempo_bpm=88, time_signature="6/8", description="d")
        clone = MusicNode.from_record(node.to_record())
        self.assertTrue(clone.same_content_as(node))
        self.assertEqual(clone.description, "d")
        with self.assertRaises(ValidationError):
            MusicNode.from_record({"id": "x"})


class TestInsertionAndSearch(unittest.TestCase):
    def test_root_creation(self):
        tree = MusicTree()
        self.assertTrue(tree.is_empty)
        tree.set_root(make_node("A"))
        self.assertEqual(tree.root.node_id, "A")
        with self.assertRaises(ValidationError):
            tree.set_root(make_node("Z"))

    def test_root_cannot_have_parent(self):
        with self.assertRaises(ValidationError):
            MusicTree().set_root(make_node("A", "P"))

    def test_insert_variations(self):
        tree = build_sample()
        self.assertEqual(tree.weight(), 8)
        self.assertEqual(tree.find_by_id("H").parent_id, "F")
        self.assertEqual(ids(tree.find_by_id("A").children), ["B", "C"])

    def test_insert_invalid(self):
        tree = build_sample()
        with self.assertRaises(DuplicateNodeError):
            tree.insert("A", make_node("D", "A"))
        with self.assertRaises(NodeNotFoundError):
            tree.insert("ZZ", make_node("N", "ZZ"))
        with self.assertRaises(ValidationError):
            tree.insert("A", make_node("N", "B"))
        with self.assertRaises(ValidationError):
            MusicTree().insert("A", make_node("N", "A"))
        self.assertEqual(tree.weight(), 8)
        self.assertEqual(tree.validate_integrity(), [])

    def test_find_by_id(self):
        tree = build_sample()
        self.assertEqual(tree.find_by_id("G").node_id, "G")
        self.assertIsNone(tree.find_by_id("NOPE"))
        self.assertIsNone(MusicTree().find_by_id("A"))

    def test_find_by_name_multiple_and_accents(self):
        tree = MusicTree()
        tree.set_root(MusicNode("Sanjuanito", NOTES, node_id="r"))
        tree.insert("r", MusicNode("Versión lenta", NOTES, parent_id="r", node_id="a"))
        tree.insert("r", MusicNode("VERSION rápida", NOTES, parent_id="r", node_id="b"))
        tree.insert("a", MusicNode("Otra", NOTES, parent_id="a", node_id="c"))
        self.assertEqual(ids(tree.find_by_name("version")), ["a", "b"])
        self.assertEqual(tree.find_by_name("zzz"), [])
        with self.assertRaises(ValidationError):
            tree.find_by_name("  ")


class TestTraversals(unittest.TestCase):
    def test_dfs_preorder(self):
        self.assertEqual(ids(build_sample().dfs()), list("ABDECFHG"))

    def test_bfs_order_and_levels(self):
        tree = build_sample()
        self.assertEqual(ids(tree.bfs()), list("ABCDEFGH"))
        self.assertEqual([ids(level) for level in tree.bfs_levels()], [["A"], ["B", "C"], ["D", "E", "F", "G"], ["H"]])

    def test_traversal_from_subtree(self):
        tree = build_sample()
        self.assertEqual(ids(tree.dfs("C")), list("CFHG"))
        self.assertEqual(ids(tree.bfs("C")), list("CFGH"))
        with self.assertRaises(NodeNotFoundError):
            tree.dfs("NOPE")

    def test_empty_tree(self):
        tree = MusicTree()
        self.assertEqual(list(tree.dfs()), [])
        self.assertEqual(list(tree.bfs()), [])
        self.assertEqual(tree.bfs_levels(), [])
        self.assertEqual(tree.height(), 0)
        self.assertEqual(tree.weight(), 0)
        self.assertEqual(tree.leaf_count(), 0)
        self.assertEqual(tree.max_degree(), 0)
        self.assertEqual(tree.validate_integrity(), [])
        self.assertEqual(tree.to_records(), [])
        with self.assertRaises(NodeNotFoundError):
            tree.level_of("A")

    def test_deep_chain_does_not_overflow_recursion(self):
        tree = MusicTree()
        tree.set_root(make_node("n0"))
        parent = tree.root
        for index in range(1, 3000):
            child = make_node(f"n{index}", parent.node_id)
            parent._attach_child(child)
            parent = child
        self.assertEqual(tree.height(), 3000)
        self.assertEqual(tree.weight(), 3000)
        self.assertEqual(tree.level_of("n2999"), 3000)


class TestProperties(unittest.TestCase):
    def setUp(self):
        self.tree = build_sample()

    def test_height_weight_levels(self):
        self.assertEqual(self.tree.height(), 4)
        self.assertEqual(self.tree.weight(), 8)
        self.assertEqual([self.tree.level_of(n) for n in "ABCDH"], [1, 2, 2, 3, 4])
        with self.assertRaises(NodeNotFoundError):
            self.tree.level_of("NOPE")

    def test_degrees(self):
        self.assertEqual([self.tree.degree_of(n) for n in "ABCFGH"], [2, 2, 2, 1, 0, 0])
        self.assertEqual(self.tree.max_degree(), 2)

    def test_leaves_and_kinds(self):
        self.assertEqual(sorted(ids(self.tree.leaves())), ["D", "E", "G", "H"])
        self.assertEqual(self.tree.leaf_count(), 4)
        kinds = {n: self.tree.kind_of(self.tree.find_by_id(n)) for n in "ABDF"}
        self.assertEqual(kinds, {"A": "Raíz", "B": "Rama", "D": "Hoja", "F": "Rama"})

    def test_descendants(self):
        self.assertEqual([self.tree.descendants_count(n) for n in "ABCFH"], [7, 2, 3, 1, 0])
        profiles = {p.node.node_id: p for p in self.tree.profiles()}
        for node_id in "ABCDEFGH":
            self.assertEqual(profiles[node_id].descendants, self.tree.descendants_count(node_id))
            self.assertEqual(profiles[node_id].level, self.tree.level_of(node_id))

    def test_stats_consistent(self):
        stats = self.tree.stats()
        self.assertEqual((stats.height, stats.weight, stats.leaf_count, stats.branch_count, stats.max_degree), (4, 8, 4, 3, 2))

    def test_single_node_tree(self):
        tree = MusicTree()
        tree.set_root(make_node("A"))
        self.assertEqual((tree.height(), tree.weight(), tree.leaf_count()), (1, 1, 1))
        self.assertEqual(tree.kind_of(tree.root), "Raíz")

    def test_relations(self):
        self.assertEqual(self.tree.parent_of("H").node_id, "F")
        self.assertIsNone(self.tree.parent_of("A"))
        self.assertEqual(ids(self.tree.siblings_of("D")), ["E"])
        self.assertEqual(ids(self.tree.path_to("H")), list("ACFH"))
        self.assertEqual(self.tree.lowest_common_ancestor("D", "H").node_id, "A")
        self.assertEqual(self.tree.lowest_common_ancestor("F", "H").node_id, "F")


class TestDeletion(unittest.TestCase):
    def test_delete_leaf(self):
        tree = build_sample()
        removed = tree.delete_node("D")
        self.assertEqual(ids(removed), ["D"])
        self.assertIsNone(tree.find_by_id("D"))
        self.assertEqual(ids(tree.find_by_id("B").children), ["E"])
        self.assertEqual(tree.validate_integrity(), [])

    def test_delete_branch(self):
        tree = build_sample()
        removed = tree.delete_node("C", STRATEGY_BRANCH)
        self.assertEqual(sorted(ids(removed)), ["C", "F", "G", "H"])
        self.assertEqual(tree.weight(), 4)
        for node_id in "CFGH":
            self.assertIsNone(tree.find_by_id(node_id))
        self.assertEqual(tree.validate_integrity(), [])

    def test_delete_promoting_children(self):
        tree = build_sample()
        removed = tree.delete_node("C", STRATEGY_PROMOTE)
        self.assertEqual(ids(removed), ["C"])
        self.assertEqual(ids(tree.root.children), ["B", "F", "G"])
        self.assertEqual(tree.find_by_id("F").parent_id, "A")
        self.assertEqual(tree.find_by_id("G").parent_id, "A")
        self.assertEqual(tree.weight(), 7)
        self.assertEqual(tree.level_of("H"), 3)
        self.assertEqual(tree.validate_integrity(), [])

    def test_root_is_protected(self):
        tree = build_sample()
        with self.assertRaises(ProtectedRootError):
            tree.delete_node("A")
        self.assertEqual(tree.weight(), 8)

    def test_delete_invalid(self):
        tree = build_sample()
        with self.assertRaises(NodeNotFoundError):
            tree.delete_node("NOPE")
        with self.assertRaises(ValidationError):
            tree.delete_node("D", "magic")
        self.assertEqual(tree.weight(), 8)

    def test_integrity_detects_corruption(self):
        tree = build_sample()
        tree.find_by_id("D")._parent_id = "C"
        self.assertTrue(tree.validate_integrity())
        tree.find_by_id("B")._attach_child(tree.root)
        self.assertTrue(any("Ciclo" in problem for problem in tree.validate_integrity()))


class TestComparator(unittest.TestCase):
    def test_compare_real_node_data(self):
        left = make_node("A", key="A menor", tempo_bpm=100, description="base")
        right = MusicNode(
            "Otra", Note.parse_sequence("C4:1 E4:1 E4:2 G4:1"), parent_id="A", node_id="B",
            key="D menor", tempo_bpm=80, time_signature="6/8", description="cambio",
        )
        result = VersionComparator().compare(left, right)
        fields = {field.label: field for field in result.fields}
        self.assertTrue(fields["Tonalidad"].changed)
        self.assertEqual((fields["Tonalidad"].left, fields["Tonalidad"].right), ("A menor", "D menor"))
        self.assertEqual((fields["Tempo (pulsos/min)"].left, fields["Tempo (pulsos/min)"].right), ("100", "80"))
        self.assertTrue(fields["Compás"].changed)
        self.assertEqual(fields["Cantidad de notas"].right, "4")
        kinds = [change.kind for change in result.note_changes]
        self.assertIn("reemplazo", kinds)
        self.assertIn("solo en B", kinds)
        self.assertFalse(result.identical)
        self.assertTrue(0 < result.similarity < 1)

    def test_compare_same_content(self):
        node = make_node("A")
        result = VersionComparator().compare(node, node)
        self.assertTrue(result.identical)
        self.assertEqual(result.similarity, 1.0)


class TestCompositionManager(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "Data" / "compositions.json"
        self.manager = CompositionManager(self.path)

    def tearDown(self):
        self.directory.cleanup()

    def create(self, name="Obra"):
        return self.manager.create_composition(name, NOTES, 100, "4/4", "C mayor", "original")

    def variation(self, parent_id, name="Var", notes="C4:1 G4:2", description="cambio"):
        return self.manager.add_variation(parent_id, name, Note.parse_sequence(notes), 100, "4/4", "C mayor", description)

    def test_missing_file_gives_empty_state(self):
        self.assertEqual(self.manager.compositions, ())
        self.assertEqual(self.manager.global_stats()["versions"], 0)

    def test_create_and_add(self):
        tree = self.create()
        node = self.variation(tree.root.node_id)
        self.assertEqual(node.parent_id, tree.root.node_id)
        self.assertEqual(tree.weight(), 2)
        self.assertEqual(self.manager.find_node(node.node_id)[0], tree)

    def test_variation_validations(self):
        tree = self.create()
        root_id = tree.root.node_id
        with self.assertRaises(NodeNotFoundError):
            self.variation("NOPE")
        with self.assertRaises(ValidationError):
            self.variation(root_id, description="  ")
        with self.assertRaises(ValidationError):
            self.variation(root_id, notes="C4:1 D4:1 E4:2")
        with self.assertRaises(ValidationError):
            self.variation(root_id, name="")
        self.assertEqual(tree.weight(), 1)

    def test_original_version_is_never_overwritten(self):
        tree = self.create()
        before = tree.root.to_record()
        self.variation(tree.root.node_id)
        self.assertEqual(tree.root.to_record(), before)

    def test_persistence_round_trip(self):
        tree = self.create()
        child = self.variation(tree.root.node_id, "Hijo")
        grandchild = self.variation(child.node_id, "Nieto", "C4:1 A4:2")
        self.variation(tree.root.node_id, "Hermano", "C4:1 B4:2")
        reloaded = CompositionManager(self.path)
        self.assertEqual(len(reloaded.compositions), 1)
        other = reloaded.compositions[0]
        self.assertEqual(ids(other.bfs()), ids(tree.bfs()))
        self.assertEqual(ids(other.dfs()), ids(tree.dfs()))
        self.assertEqual(other.level_of(grandchild.node_id), 3)
        self.assertEqual(other.find_by_id(child.node_id).notes, child.notes)
        self.assertEqual(other.validate_integrity(), [])
        self.assertFalse(self.path.with_name(self.path.name + ".tmp").exists())

    def test_json_is_flat_and_readable(self):
        tree = self.create()
        self.variation(tree.root.node_id)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["format"], "armonitree")
        self.assertEqual(len(payload["compositions"][0]["nodes"]), 2)

    def test_corrupt_files(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{no es json", encoding="utf-8")
        with self.assertRaises(PersistenceError):
            CompositionManager(self.path)
        self.path.write_text(json.dumps({"format": "otro"}), encoding="utf-8")
        with self.assertRaises(PersistenceError):
            CompositionManager(self.path)

    def test_inconsistent_saved_tree(self):
        tree = self.create()
        self.variation(tree.root.node_id)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload["compositions"][0]["nodes"][1]["parent_id"] = "fantasma"
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(InvalidTreeDataError):
            CompositionManager(self.path)

    def test_saved_cycle_and_duplicates_rejected(self):
        base = make_node("A").to_record()
        second = make_node("B", "A").to_record()
        with self.assertRaises(InvalidTreeDataError):
            MusicTree.from_records([base, dict(second, id="A")])
        a = dict(make_node("X").to_record(), parent_id="Y")
        b = dict(make_node("Y").to_record(), parent_id="X")
        with self.assertRaises(InvalidTreeDataError):
            MusicTree.from_records([base, a, b])
        with self.assertRaises(InvalidTreeDataError):
            MusicTree.from_records([])
        with self.assertRaises(InvalidTreeDataError):
            MusicTree.from_records([base, dict(base, id="Z")])

    def test_delete_variation_strategies(self):
        tree = self.create()
        root_id = tree.root.node_id
        middle = self.variation(root_id, "Medio")
        leaf = self.variation(middle.node_id, "Hoja", "C4:1 A4:2")
        self.manager.delete_variation(middle.node_id, "promote")
        self.assertEqual(self.manager.find_node(leaf.node_id)[1].parent_id, root_id)
        reloaded = CompositionManager(self.path)
        self.assertEqual(reloaded.compositions[0].weight(), 2)
        self.manager.delete_variation(leaf.node_id)
        self.assertEqual(tree.weight(), 1)
        with self.assertRaises(ProtectedRootError):
            self.manager.delete_variation(root_id)

    def test_delete_composition_requires_exact_name(self):
        tree = self.create("Obra uno")
        root_id = tree.root.node_id
        self.variation(root_id)
        with self.assertRaises(ValidationError):
            self.manager.delete_composition(root_id, "otra cosa")
        self.assertEqual(len(self.manager.compositions), 1)
        self.assertEqual(self.manager.delete_composition(root_id, " Obra uno "), 2)
        self.assertEqual(self.manager.compositions, ())
        self.assertEqual(CompositionManager(self.path).compositions, ())

    def test_ids_unique_across_forest(self):
        for index in range(30):
            self.create(f"Obra {index}")
        all_ids = [node.node_id for _, node, _ in self.manager.all_versions()]
        self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_rollback_when_save_fails(self):
        tree = self.create()
        with mock.patch.object(self.manager, "save", side_effect=PersistenceError("disco lleno")):
            with self.assertRaises(PersistenceError):
                self.variation(tree.root.node_id)
        self.assertEqual(self.manager.compositions[0].weight(), 1)

    def test_global_search(self):
        first = self.create("Carnaval uno")
        self.create("Carnaval dos")
        self.variation(first.root.node_id, "Carnaval lento")
        self.assertEqual(len(self.manager.search_by_name("carnaval")), 3)
        self.assertEqual(self.manager.search_by_name("zzz"), [])

    def test_demo_composition_structure(self):
        tree = build_demo(self.manager)
        stats = tree.stats()
        self.assertEqual((stats.height, stats.weight, stats.leaf_count, stats.max_degree), (4, 8, 4, 3))
        self.assertEqual(tree.validate_integrity(), [])
        self.assertIn("Motivo andino (ejemplo)", TreeVisualizer.build_outline(tree))


class TestVisualizer(unittest.TestCase):
    def test_dot_reflects_tree(self):
        tree = build_sample()
        dot = TreeVisualizer().build_dot(tree, "H")
        self.assertEqual(dot.count("->"), tree.weight() - 1)
        for node in tree.dfs():
            self.assertIn(f'"{node.node_id}" [label=', dot)
        self.assertIn("#F4B23E", dot)
        self.assertIn("penwidth=3", dot)

    def test_dot_escapes_quotes(self):
        tree = MusicTree()
        tree.set_root(MusicNode('Obra "uno"', NOTES, node_id="r"))
        self.assertIn('Obra \\"uno\\"', TreeVisualizer().build_dot(tree))

    def test_dot_empty_tree(self):
        self.assertNotIn("->", TreeVisualizer().build_dot(MusicTree()))


def parse_midi(data):
    assert data[:4] == b"MThd"
    fmt, tracks, division = struct.unpack(">HHH", data[8:14])
    assert data[14:18] == b"MTrk"
    length = struct.unpack(">I", data[18:22])[0]
    body = data[22:22 + length]
    assert len(body) == length
    position, tick, events, running = 0, 0, [], None

    def read_vlq():
        nonlocal position
        value = 0
        while True:
            byte = body[position]
            position += 1
            value = (value << 7) | (byte & 0x7F)
            if not byte & 0x80:
                return value

    while position < len(body):
        tick += read_vlq()
        status = body[position]
        position += 1
        if status == 0xFF:
            meta_type = body[position]
            position += 1
            size = read_vlq()
            events.append(("meta", meta_type, tick, bytes(body[position:position + size])))
            position += size
        elif status & 0xF0 in (0x90, 0x80):
            events.append(("on" if status & 0xF0 == 0x90 else "off", body[position], tick))
            position += 2
        elif status & 0xF0 == 0xC0:
            events.append(("program", body[position], tick))
            position += 1
        else:
            raise AssertionError(f"evento desconocido {status:#x}")
    return fmt, tracks, division, events


class TestExporter(unittest.TestCase):
    def test_midi_structure(self):
        notes = Note.parse_sequence("C4:1 R:1 E4:2 G#4:0.5")
        data = MusicExporter().to_midi_bytes(notes, 120, "6/8", "Prueba ñ")
        fmt, tracks, division, events = parse_midi(data)
        self.assertEqual((fmt, tracks, division), (0, 1, 480))
        ons = [event for event in events if event[0] == "on"]
        offs = [event for event in events if event[0] == "off"]
        self.assertEqual([event[1] for event in ons], [60, 64, 68])
        self.assertEqual([event[2] for event in ons], [0, 960, 1920])
        self.assertEqual([event[2] for event in offs], [480, 1920, 2160])
        tempo = next(event for event in events if event[:2] == ("meta", 0x51))
        self.assertEqual(int.from_bytes(tempo[3], "big"), 500000)
        signature = next(event for event in events if event[:2] == ("meta", 0x58))
        self.assertEqual(signature[3][:2], bytes([6, 3]))

    def test_midi_rejects_empty(self):
        with self.assertRaises(ValidationError):
            MusicExporter().to_midi_bytes((), 100)

    def test_wav_duration_matches_notes(self):
        notes = Note.parse_sequence("A4:1 R:1 A4:2")
        data = MusicExporter().to_wav_bytes(notes, 120, sample_rate=8000)
        with wave.open(io.BytesIO(data)) as handle:
            self.assertEqual(handle.getframerate(), 8000)
            self.assertEqual(handle.getnframes(), 8000 * 2)
            frames = handle.readframes(handle.getnframes())
        self.assertTrue(any(frames))

    def test_wav_length_limit(self):
        notes = Note.parse_sequence(" ".join(["C4:16"] * 50))
        with self.assertRaises(ValidationError):
            MusicExporter().to_wav_bytes(notes, 20)


if __name__ == "__main__":
    unittest.main()
