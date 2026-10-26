import os
from pathlib import Path

import pandas as pd
import streamlit as st

from Models.Errors import ArmoniTreeError, PersistenceError, ValidationError
from Models.MusicNode import KEYS, MAX_TEMPO, MIN_TEMPO, TIME_SIGNATURES
from Models.Note import DEFAULT_OCTAVE, MAX_BEATS, MAX_OCTAVE, MIN_OCTAVE, PITCH_CLASSES, REST, Note
from Services.CompositionManager import CompositionManager
from Services.MusicExporter import MusicExporter
from Services.VersionComparator import VersionComparator
from Structures.MusicTree import STRATEGY_BRANCH, STRATEGY_PROMOTE
from Utils.DemoComposition import build_demo
from Utils.TreeVisualizer import LEGEND, TreeVisualizer

PAGES = (
    "Panel principal",
    "Editor musical",
    "Variaciones",
    "Explorador del árbol",
    "Historial y recuperación",
    "Comparador",
    "Exportar y escuchar",
)
NO_KEY = "Sin definir"
DATA_PATH = Path(os.environ.get("ARMONITREE_DATA", Path(__file__).parent / "Data" / "compositions.json"))
EXPORTER = MusicExporter()
VISUALIZER = TreeVisualizer()
COMPARATOR = VersionComparator()

st.set_page_config(page_title="ArmoniTree", page_icon="🎶", layout="wide")
st.markdown(
    """
    <style>
    .hero{background:linear-gradient(120deg,#7C2D12,#C2410C 55%,#F4B23E);color:#fff;padding:1.3rem 1.6rem;border-radius:16px;margin-bottom:1.1rem}
    .hero h1{margin:0;font-size:2rem;color:#fff}.hero p{margin:.3rem 0 0;opacity:.95}
    .pill{display:inline-block;padding:.1rem .65rem;border-radius:999px;font-size:.8rem;margin-right:.3rem;color:#1F2937;font-weight:600}
    </style>
    """,
    unsafe_allow_html=True,
)


def init_state():
    for key, value in {"current_root": None, "current_node": None, "nonce": 0, "flash": [], "pending_page": None, "page": PAGES[0]}.items():
        st.session_state.setdefault(key, value)


def get_manager() -> CompositionManager:
    if "manager" not in st.session_state:
        try:
            st.session_state.manager = CompositionManager(DATA_PATH)
        except PersistenceError as error:
            st.error(f"No se pudieron cargar los datos: {error}")
            st.info("Tus datos no fueron modificados. Corrige o mueve el archivo indicado y recarga la página.")
            st.stop()
    return st.session_state.manager


def flash(message: str, kind: str = "success"):
    st.session_state.flash.append((kind, message))


def show_flash():
    for kind, message in st.session_state.flash:
        {"success": st.success, "error": st.error, "info": st.info, "warning": st.warning}[kind](message)
    st.session_state.flash = []


def navigate(page: str, root_id=None, node_id=None):
    if root_id is not None:
        st.session_state.current_root = root_id
    if node_id is not None:
        st.session_state.current_node = node_id
    st.session_state.pending_page = page


def finish_mutation(message: str, page: str, root_id=None, node_id=None):
    flash(message)
    st.session_state.nonce += 1
    navigate(page, root_id, node_id)
    st.rerun()


def hero(title: str, subtitle: str):
    st.markdown(f'<div class="hero"><h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)


def kind_pill(kind: str) -> str:
    color = {"Raíz": "#F4B23E", "Rama": "#9CC3EE", "Hoja": "#96D37A"}[kind]
    return f'<span class="pill" style="background:{color}">{kind}</span>'


def composition_label(tree) -> str:
    return f"{tree.root.name} · {tree.weight()} versión(es)"


def version_label(node, level) -> str:
    return f"[N{level}] {node.name} · {node.node_id}"


def require_compositions(manager: CompositionManager) -> bool:
    if manager.compositions:
        return True
    st.info("Aún no hay composiciones. Crea la primera en «Editor musical» o carga el ejemplo desde el «Panel principal».")
    st.button("Ir al editor musical", on_click=navigate, args=("Editor musical",), key="empty_to_editor")
    return False


def pick_version(manager: CompositionManager, prefix: str):
    nonce = st.session_state.nonce
    trees = manager.compositions
    root_ids = [tree.root.node_id for tree in trees]
    current_root = st.session_state.current_root if st.session_state.current_root in root_ids else root_ids[0]
    column_a, column_b = st.columns(2)
    root_id = column_a.selectbox(
        "Composición", root_ids, index=root_ids.index(current_root),
        format_func=lambda rid: composition_label(manager.get_tree(rid)), key=f"{prefix}_root_{nonce}",
    )
    tree = manager.get_tree(root_id)
    entries = list(tree.dfs_with_level())
    node_ids = [node.node_id for node, _ in entries]
    current_node = st.session_state.current_node
    if root_id != st.session_state.current_root or current_node not in node_ids:
        current_node = node_ids[0]
    levels = {node.node_id: level for node, level in entries}
    node_id = column_b.selectbox(
        "Versión", node_ids, index=node_ids.index(current_node),
        format_func=lambda nid: version_label(tree.find_by_id(nid), levels[nid]), key=f"{prefix}_node_{nonce}",
    )
    st.session_state.current_root, st.session_state.current_node = root_id, node_id
    return tree, tree.find_by_id(node_id), levels[node_id]


def notes_to_dataframe(notes) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Nota": pd.Series([note.pitch_class for note in notes], dtype="object"),
            "Octava": pd.Series([note.octave or DEFAULT_OCTAVE for note in notes], dtype="int64"),
            "Pulsos": pd.Series([note.beats for note in notes], dtype="float64"),
        }
    )


def dataframe_to_notes(frame: pd.DataFrame):
    notes = []
    for position, row in enumerate(frame.itertuples(index=False), start=1):
        if pd.isna(row.Nota):
            raise ValidationError(f"Fila {position}: elige una nota (o R para silencio).")
        beats = 1.0 if pd.isna(row.Pulsos) else float(row.Pulsos)
        try:
            if row.Nota == REST:
                notes.append(Note(REST, None, beats))
            else:
                octave = DEFAULT_OCTAVE if pd.isna(row.Octava) else int(row.Octava)
                notes.append(Note(str(row.Nota), octave, beats))
        except ValidationError as error:
            raise ValidationError(f"Fila {position}: {error}")
    if not notes:
        raise ValidationError("Agrega al menos una nota a la secuencia.")
    return tuple(notes)


def note_input(key: str, initial_notes):
    mode = st.radio("Modo de entrada de notas", ("Tabla", "Texto"), horizontal=True, key=f"{key}_mode")
    try:
        if mode == "Tabla":
            st.caption("Agrega filas con «+». Nota R = silencio. La duración se mide en pulsos (negra = 1).")
            frame = st.data_editor(
                notes_to_dataframe(initial_notes), num_rows="dynamic", key=f"{key}_table",
                column_config={
                    "Nota": st.column_config.SelectboxColumn("Nota", options=list(PITCH_CLASSES) + [REST], required=True),
                    "Octava": st.column_config.NumberColumn("Octava", min_value=MIN_OCTAVE, max_value=MAX_OCTAVE, step=1, default=DEFAULT_OCTAVE),
                    "Pulsos": st.column_config.NumberColumn("Pulsos", min_value=0.25, max_value=MAX_BEATS, step=0.25, default=1.0),
                },
            )
            notes = dataframe_to_notes(frame)
        else:
            st.caption("Formato: C4:1 F#3:0.5 Bb4:2 R:1 (nota, octava, «:» y pulsos). Separa con espacios.")
            text = st.text_area("Secuencia", value=" ".join(note.to_token() for note in initial_notes), key=f"{key}_text")
            notes = Note.parse_sequence(text)
    except ValidationError as error:
        st.warning(str(error))
        return None
    st.caption(f"{len(notes)} nota(s) · {sum(note.beats for note in notes):g} pulsos: " + " ".join(note.to_token() for note in notes[:24]) + (" …" if len(notes) > 24 else ""))
    return notes


def audio_preview(notes, tempo: int, key: str):
    if st.button("▶ Generar vista previa de audio", key=key):
        try:
            st.audio(EXPORTER.to_wav_bytes(notes, tempo), format="audio/wav")
        except ArmoniTreeError as error:
            st.error(str(error))


def music_fields(prefix: str, defaults):
    column_a, column_b, column_c = st.columns(3)
    key_options = (NO_KEY,) + KEYS
    key_choice = column_a.selectbox("Tonalidad (opcional)", key_options, index=key_options.index(defaults["key"] or NO_KEY), key=f"{prefix}_key")
    tempo = column_b.number_input("Tempo (pulsos por minuto)", MIN_TEMPO, MAX_TEMPO, defaults["tempo"], step=1, key=f"{prefix}_tempo")
    signature = column_c.selectbox("Compás", TIME_SIGNATURES, index=TIME_SIGNATURES.index(defaults["signature"]), key=f"{prefix}_sig")
    return (None if key_choice == NO_KEY else key_choice), int(tempo), signature


def show_node_content(node):
    st.markdown(
        f"**Tonalidad:** {node.key or NO_KEY} · **Tempo:** {node.tempo_bpm} ppm · **Compás:** {node.time_signature} · "
        f"**Notas:** {len(node.notes)} ({node.total_beats:g} pulsos) · **Creada:** {node.created_at.replace('T', ' ')}"
    )
    st.code(" ".join(note.to_token() for note in node.notes), language=None)
    if node.description:
        st.markdown(f"**Modificación / descripción:** {node.description}")


def page_dashboard(manager):
    hero("🎶 ArmoniTree", "Organiza la evolución de tus composiciones como un árbol de versiones: cada variación nace de la versión que la originó.")
    stats = manager.global_stats()
    columns = st.columns(4)
    columns[0].metric("Composiciones (raíces)", stats["compositions"])
    columns[1].metric("Versiones en total (peso)", stats["versions"])
    columns[2].metric("Altura máxima", stats["max_height"])
    columns[3].metric("Hojas", stats["leaves"])
    if not manager.compositions:
        with st.container(border=True):
            st.markdown("### Empieza tu primer árbol")
            st.write(
                "Una composición original es la **raíz**; cada vez que la modificas y guardas, se crea un **nodo hijo**. "
                "Crea tu primera composición en el editor, o carga una composición de ejemplo (datos de demostración, no tuyos) para explorar el árbol."
            )
            left, right = st.columns(2)
            left.button("Crear mi primera composición", on_click=navigate, args=("Editor musical",), type="primary", key="dash_create")
            if right.button("Cargar composición de ejemplo", key="dash_demo"):
                try:
                    tree = build_demo(manager)
                except ArmoniTreeError as error:
                    st.error(str(error))
                else:
                    finish_mutation("Se cargó la composición de ejemplo «Motivo andino (ejemplo)».", "Explorador del árbol", tree.root.node_id, tree.root.node_id)
        return
    st.subheader("Mis composiciones")
    for tree in manager.compositions:
        tree_stats = tree.stats()
        with st.container(border=True):
            info, action = st.columns([5, 1])
            info.markdown(f"**{tree.root.name}** · {tree.root.key or NO_KEY} · {tree.root.tempo_bpm} ppm · {tree.root.time_signature}")
            info.caption(
                f"{tree_stats.weight} versión(es) · altura {tree_stats.height} · grado máximo {tree_stats.max_degree} · "
                f"{tree_stats.leaf_count} hoja(s) · creada {tree.root.created_at.replace('T', ' ')}"
            )
            action.button("Abrir", key=f"open_{tree.root.node_id}_{st.session_state.nonce}", on_click=navigate,
                          args=("Explorador del árbol", tree.root.node_id, tree.root.node_id))


def page_editor(manager):
    hero("Editor musical", "Registra la idea original: será la raíz de un nuevo árbol de versiones.")
    nonce = st.session_state.nonce
    name = st.text_input("Nombre de la composición", max_chars=60, key=f"ed_name_{nonce}")
    key, tempo, signature = music_fields(f"ed_{nonce}", {"key": None, "tempo": 100, "signature": "4/4"})
    description = st.text_area("Descripción", max_chars=500, key=f"ed_desc_{nonce}", placeholder="Idea, intención o contexto de la composición")
    notes = note_input(f"ed_notes_{nonce}", ())
    if notes:
        audio_preview(notes, tempo, f"ed_audio_{nonce}")
    if st.button("Guardar composición", type="primary", key=f"ed_save_{nonce}"):
        if notes is None:
            st.error("Completa correctamente la secuencia de notas antes de guardar.")
            return
        try:
            tree = manager.create_composition(name, notes, tempo, signature, key, description)
        except ArmoniTreeError as error:
            st.error(str(error))
            return
        finish_mutation(f"Composición «{tree.root.name}» guardada como raíz de un nuevo árbol.", "Explorador del árbol", tree.root.node_id, tree.root.node_id)


def page_variation(manager):
    hero("Creación de variaciones", "Elige cualquier versión como base: la nueva variación quedará como su hija y la base no se modifica.")
    if not require_compositions(manager):
        return
    tree, base, level = pick_version(manager, "var")
    with st.expander(f"Versión base: {base.name} (nivel {level})", expanded=True):
        show_node_content(base)
    nonce, scope = st.session_state.nonce, f"{base.node_id}_{st.session_state.nonce}"
    st.markdown(f"#### Nueva variación derivada de «{base.name}»")
    name = st.text_input("Nombre de la variación", value=f"Variación de {base.name}"[:60], max_chars=60, key=f"var_name_{scope}")
    key, tempo, signature = music_fields(f"var_{scope}", {"key": base.key, "tempo": base.tempo_bpm, "signature": base.time_signature})
    description = st.text_area("¿Qué modificaste? (obligatorio)", max_chars=500, key=f"var_desc_{scope}")
    notes = note_input(f"var_notes_{scope}", base.notes)
    if notes:
        audio_preview(notes, tempo, f"var_audio_{scope}")
    if st.button("Guardar variación", type="primary", key=f"var_save_{scope}"):
        if notes is None:
            st.error("Completa correctamente la secuencia de notas antes de guardar.")
            return
        try:
            node = manager.add_variation(base.node_id, name, notes, tempo, signature, key, description)
        except ArmoniTreeError as error:
            st.error(str(error))
            return
        finish_mutation(f"Variación «{node.name}» creada como hija de «{base.name}».", "Explorador del árbol", tree.root.node_id, node.node_id)


def render_details(tree, node, level):
    parent = tree.parent_of(node.node_id)
    siblings = tree.siblings_of(node.node_id)
    st.markdown(f"### {node.name}")
    st.markdown(kind_pill(tree.kind_of(node)), unsafe_allow_html=True)
    st.caption(f"ID {node.node_id} · nivel {level} · grado {node.degree} · {tree.descendants_count(node.node_id)} descendiente(s)")
    st.markdown(f"**Padre:** {parent.name + ' [' + parent.node_id + ']' if parent else 'ninguno (es la raíz)'}")
    if siblings:
        st.markdown("**Hermanos:** " + ", ".join(sibling.name for sibling in siblings))
    if node.children:
        st.markdown("**Ramas que nacen de esta versión:** " + ", ".join(child.name for child in node.children))
    show_node_content(node)
    st.button("➕ Crear variación desde aquí", key=f"ex_var_{node.node_id}", on_click=navigate, args=("Variaciones", tree.root.node_id, node.node_id))
    st.button("📜 Ver historial", key=f"ex_hist_{node.node_id}", on_click=navigate, args=("Historial y recuperación", tree.root.node_id, node.node_id))


def render_deletion(manager, tree, node):
    nonce = st.session_state.nonce
    with st.expander("🗑 Eliminar"):
        if node is tree.root:
            st.warning(f"Eliminarás la composición completa «{node.name}» con sus {tree.weight() - 1} variación(es). Esta acción no se puede deshacer.")
            typed = st.text_input("Escribe el nombre exacto de la composición para confirmar", key=f"del_root_text_{nonce}")
            if st.button("Eliminar composición completa", key=f"del_root_{nonce}"):
                try:
                    count = manager.delete_composition(node.node_id, typed)
                except ArmoniTreeError as error:
                    st.error(str(error))
                    return
                st.session_state.current_root = st.session_state.current_node = None
                finish_mutation(f"Composición eliminada ({count} versión(es)).", "Explorador del árbol")
            return
        descendants = tree.descendants_count(node.node_id)
        strategy = STRATEGY_BRANCH
        if descendants == 0:
            st.info("Es una hoja: solo se eliminará esta versión.")
        else:
            st.warning(f"Esta versión tiene {node.degree} hijo(s) directo(s) y {descendants} descendiente(s).")
            options = {
                f"Eliminar la rama completa ({descendants + 1} versiones)": STRATEGY_BRANCH,
                "Eliminar solo esta versión y reasignar sus hijos al padre": STRATEGY_PROMOTE,
            }
            strategy = options[st.radio("Estrategia", list(options), key=f"del_strategy_{node.node_id}_{nonce}")]
        confirmed = st.checkbox("Entiendo que esta acción no se puede deshacer", key=f"del_confirm_{node.node_id}_{nonce}")
        if st.button("Eliminar versión", disabled=not confirmed, key=f"del_node_{node.node_id}_{nonce}"):
            parent = tree.parent_of(node.node_id)
            try:
                removed = manager.delete_variation(node.node_id, strategy)
            except ArmoniTreeError as error:
                st.error(str(error))
                return
            finish_mutation(f"Se eliminaron {len(removed)} versión(es).", "Explorador del árbol", tree.root.node_id, parent.node_id)


def render_properties(tree):
    stats = tree.stats()
    columns = st.columns(5)
    columns[0].metric("Altura (niveles)", stats.height)
    columns[1].metric("Peso (nodos)", stats.weight)
    columns[2].metric("Grado máximo", stats.max_degree)
    columns[3].metric("Hojas", stats.leaf_count)
    columns[4].metric("Ramas", stats.branch_count)
    st.caption("Convención del curso: la raíz está en el nivel 1 y la altura es la cantidad de niveles del camino más largo.")
    table = pd.DataFrame(
        [
            {
                "Nivel": profile.level,
                "Versión": profile.node.name,
                "ID": profile.node.node_id,
                "Tipo": tree.kind_of(profile.node),
                "Grado": profile.node.degree,
                "Descendientes": profile.descendants,
                "Padre": profile.node.parent_id or "—",
            }
            for profile in tree.profiles()
        ]
    )
    st.dataframe(table, hide_index=True)
    left, right = st.columns(2)
    left.markdown("**Recorrido en profundidad (DFS, preorden)**")
    left.write(" → ".join(node.name for node in tree.dfs()))
    right.markdown("**Recorrido en anchura (BFS) por niveles**")
    for index, level_nodes in enumerate(tree.bfs_levels(), start=1):
        right.write(f"Nivel {index}: " + ", ".join(node.name for node in level_nodes))


def render_search(manager, tree):
    nonce = st.session_state.nonce
    mode = st.radio("Buscar por", ("Identificador", "Nombre"), horizontal=True, key=f"search_mode_{nonce}")
    scope = st.radio("Alcance", ("Esta composición", "Todas las composiciones"), horizontal=True, key=f"search_scope_{nonce}")
    query = st.text_input("Texto a buscar", key=f"search_text_{nonce}")
    if not query.strip():
        st.caption("Escribe un identificador exacto o parte de un nombre (ignora mayúsculas y tildes).")
        return
    trees = [tree] if scope == "Esta composición" else list(manager.compositions)
    try:
        if mode == "Identificador":
            matches = [(item, item.find_by_id(query.strip())) for item in trees]
            matches = [(item, node) for item, node in matches if node is not None]
        else:
            matches = [(item, node) for item in trees for node in item.find_by_name(query)]
    except ArmoniTreeError as error:
        st.error(str(error))
        return
    if not matches:
        st.info("No se encontraron coincidencias.")
        return
    st.success(f"{len(matches)} coincidencia(s).")
    for item, node in matches:
        columns = st.columns([4, 1])
        columns[0].markdown(f"**{node.name}** · `{node.node_id}` · nivel {item.level_of(node.node_id)} · composición «{item.root.name}»")
        columns[1].button("Abrir", key=f"found_{node.node_id}_{nonce}", on_click=navigate, args=("Explorador del árbol", item.root.node_id, node.node_id))


def page_explorer(manager):
    hero("Explorador del árbol", "El diagrama se dibuja directamente desde el árbol que está en memoria.")
    if not require_compositions(manager):
        return
    tree, node, level = pick_version(manager, "ex")
    tab_tree, tab_props, tab_search = st.tabs(["🌳 Árbol", "📐 Recorridos y propiedades", "🔎 Búsqueda"])
    with tab_tree:
        left, right = st.columns([3, 2])
        with left:
            st.markdown("  ".join(f'<span class="pill" style="background:{color}">{label}</span>' for label, color in LEGEND), unsafe_allow_html=True)
            st.caption("La versión seleccionada se resalta y su camino hasta la raíz se marca en naranja.")
            st.graphviz_chart(VISUALIZER.build_dot(tree, node.node_id))
        with right:
            render_details(tree, node, level)
            render_deletion(manager, tree, node)
    with tab_props:
        render_properties(tree)
    with tab_search:
        render_search(manager, tree)


def page_history(manager):
    hero("Historial y recuperación", "Recorre cómo evolucionó una versión desde la composición original y retómala como punto de partida.")
    if not require_compositions(manager):
        return
    tree, node, level = pick_version(manager, "hist")
    st.markdown("#### Linaje: de la raíz hasta la versión seleccionada")
    for depth, ancestor in enumerate(tree.path_to(node.node_id), start=1):
        with st.container(border=True):
            st.markdown(f"**Nivel {depth} · {ancestor.name}** `{ancestor.node_id}` · {ancestor.created_at.replace('T', ' ')}")
            st.write(ancestor.description or "Sin descripción.")
    st.markdown("#### Contenido de la versión seleccionada")
    show_node_content(node)
    if node.children:
        st.markdown("**Ramas que se originan aquí:** " + ", ".join(f"{child.name} ({child.node_id})" for child in node.children))
    else:
        st.caption("Esta versión es una hoja: todavía no tiene variaciones.")
    st.button("Usar como base de una nueva variación", type="primary", key=f"hist_use_{node.node_id}", on_click=navigate, args=("Variaciones", tree.root.node_id, node.node_id))
    st.markdown("#### Todas las versiones de la composición, de la más antigua a la más reciente")
    ordered = sorted(tree.dfs_with_level(), key=lambda entry: entry[0].created_at)
    st.dataframe(
        pd.DataFrame([{"Creada": item.created_at.replace("T", " "), "Versión": item.name, "ID": item.node_id, "Nivel": lvl, "Padre": item.parent_id or "—", "Cambio": item.description or "—"} for item, lvl in ordered]),
        hide_index=True,
    )


def page_comparator(manager):
    hero("Comparador musical", "Compara dos versiones usando los datos realmente almacenados en cada nodo.")
    versions = manager.all_versions()
    if len(versions) < 2:
        st.info("Necesitas al menos dos versiones para comparar. Crea una variación desde «Variaciones».")
        if not manager.compositions:
            require_compositions(manager)
        return
    ids = [node.node_id for _, node, _ in versions]
    labels = {node.node_id: f"{tree.root.name} › {version_label(node, level)}" for tree, node, level in versions}
    nonce = st.session_state.nonce
    default_a = ids.index(st.session_state.current_node) if st.session_state.current_node in ids else 0
    column_a, column_b = st.columns(2)
    first_id = column_a.selectbox("Versión A", ids, index=default_a, format_func=labels.get, key=f"cmp_a_{nonce}")
    default_b = next((i for i, value in enumerate(ids) if value != first_id and value == (manager.find_node(first_id)[1].parent_id)), 0 if ids[0] != first_id else 1)
    second_id = column_b.selectbox("Versión B", ids, index=default_b, format_func=labels.get, key=f"cmp_b_{nonce}")
    tree_a, node_a = manager.find_node(first_id)
    tree_b, node_b = manager.find_node(second_id)
    result = COMPARATOR.compare(node_a, node_b)
    if tree_a is tree_b:
        ancestor = tree_a.lowest_common_ancestor(first_id, second_id)
        st.info(f"Misma composición. Ancestro común más cercano: «{ancestor.name}» (nivel {tree_a.level_of(ancestor.node_id)}). Niveles: A = {tree_a.level_of(first_id)}, B = {tree_a.level_of(second_id)}.")
    else:
        st.info("Las versiones pertenecen a composiciones distintas: no comparten ancestros.")
    st.progress(result.similarity, text=f"Similitud de la secuencia de notas: {result.similarity:.0%}")
    if result.identical:
        st.success("Las dos versiones tienen exactamente el mismo contenido musical.")
    st.markdown("#### Atributos")
    st.dataframe(
        pd.DataFrame([{"Atributo": item.label, "A": item.left, "B": item.right, "¿Cambió?": "Sí" if item.changed else "No"} for item in result.fields]),
        hide_index=True,
    )
    st.markdown("#### Notas (alineadas por secuencia)")
    st.dataframe(
        pd.DataFrame([{"Diferencia": change.kind, "Notas en A": " ".join(change.left) or "—", "Notas en B": " ".join(change.right) or "—"} for change in result.note_changes]),
        hide_index=True,
    )


def page_export(manager):
    hero("Exportar y escuchar", "Descarga la versión como archivo MIDI (instrumento: flauta de pan) o genera una vista previa de audio.")
    if not require_compositions(manager):
        return
    tree, node, _ = pick_version(manager, "exp")
    show_node_content(node)
    try:
        midi = EXPORTER.to_midi_bytes(node.notes, node.tempo_bpm, node.time_signature, node.name)
    except ArmoniTreeError as error:
        st.error(str(error))
        return
    safe_name = "".join(char if char.isalnum() else "_" for char in node.name).strip("_") or "version"
    st.download_button("⬇ Descargar MIDI", midi, file_name=f"{safe_name}_{node.node_id}.mid", mime="audio/midi", type="primary")
    st.caption("En el MIDI, 1 pulso = 1 negra; el compás se escribe como metadato.")
    audio_preview(node.notes, node.tempo_bpm, f"exp_audio_{node.node_id}")
    st.caption("La vista previa usa una síntesis sencilla de onda (no es el sonido real de una quena o zampoña).")


def main():
    init_state()
    manager = get_manager()
    if st.session_state.pending_page:
        st.session_state.page = st.session_state.pending_page
        st.session_state.pending_page = None
    with st.sidebar:
        st.markdown("## 🎶 ArmoniTree")
        st.caption("Versiones musicales organizadas como árbol")
        st.radio("Navegación", PAGES, key="page")
        st.divider()
        stats = manager.global_stats()
        st.caption(f"{stats['compositions']} composición(es) · {stats['versions']} versión(es)")
        st.caption(f"Datos: {manager.storage_path.name}")
    show_flash()
    {
        "Panel principal": page_dashboard,
        "Editor musical": page_editor,
        "Variaciones": page_variation,
        "Explorador del árbol": page_explorer,
        "Historial y recuperación": page_history,
        "Comparador": page_comparator,
        "Exportar y escuchar": page_export,
    }[st.session_state.page](manager)


main()
