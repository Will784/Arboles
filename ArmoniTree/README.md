# 🎶 ArmoniTree

Aplicación en Python + Streamlit que organiza las versiones de una composición musical como un **árbol n-ario implementado a mano**. La composición original es la raíz; cada variación guardada es un nodo hijo de la versión de la que nació.

Proyecto para la asignatura *Estructuras de Datos* (tema: Árboles, según `Arboles.pdf`).

## 1. Ejecución local

Requiere Python 3.10 o superior.

```bash
cd ArmoniTree
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run App.py
```

Pruebas (solo biblioteca estándar, salvo `TestApp` que usa Streamlit):

```bash
python -m unittest Tests.TestMusicTree        # lógica del árbol, persistencia, exportación
python -m unittest Tests.TestApp              # humo de la interfaz (requiere streamlit)
python Tests/BenchmarkTree.py                 # mediciones con árboles de 1 000 a 100 000 nodos
```

Los datos se guardan en `Data/compositions.json` (se crea al guardar por primera vez). Se puede cambiar la ruta con la variable de entorno `ARMONITREE_DATA`. Está pensada para un solo usuario local.

## 2. Estructura del proyecto

```
ArmoniTree/
├── App.py                         Interfaz Streamlit (7 módulos)
├── Models/
│   ├── Errors.py                  Excepciones propias
│   ├── Note.py                    Nota inmutable (altura, octava, pulsos) y su parser
│   └── MusicNode.py               Nodo = una versión musical
├── Structures/MusicTree.py        Árbol n-ario y todos sus algoritmos
├── Services/
│   ├── CompositionManager.py      Bosque de composiciones + persistencia JSON
│   ├── VersionComparator.py       Comparación de dos versiones
│   └── MusicExporter.py           MIDI y WAV escritos con la biblioteca estándar
├── Utils/
│   ├── TreeVisualizer.py          Genera el diagrama (Graphviz DOT) desde el árbol real
│   └── DemoComposition.py         Composición de ejemplo, construida con la API real
├── Tests/                         TestMusicTree, TestApp, BenchmarkTree
├── .streamlit/config.toml         Tema visual
├── requirements.txt
└── README.md
```

## 3. Conceptos del PDF aplicados

| Concepto del PDF | Dónde se usa |
|---|---|
| Estructura jerárquica vs. lineal | Las versiones forman un árbol: una lista no expresa de qué versión nació cada variación |
| Raíz, padre, hijo, hermano, hoja, rama | `MusicTree.kind_of`, `siblings_of`, `parent_of`; colores del diagrama (raíz amarilla, rama azul, hoja verde, igual que las figuras del PDF) |
| Nivel (raíz = 1) y altura (niveles del camino más largo) | `level_of`, `height`. **Convención: raíz en nivel 1**, tal como el PDF (ejemplo con altura 4) |
| Peso | `weight` (cantidad de nodos) |
| Grado de un nodo / orden | `degree_of`, `max_degree`. Es un árbol **n-ario sin límite fijo de orden**; el grado máximo es el máximo observado |
| Árbol n-ario | Estructura elegida: una versión puede tener cualquier cantidad de variaciones |

**Árboles del PDF no implementados, y por qué:** binario/AVL/rojo-negro/B/segmentos se basan en ordenar *claves* para buscar rápido. Aquí los hijos no tienen orden de clave ni cardinalidad fija, así que forzarlos sería artificial. El n-ario es el que el PDF asocia a árboles genealógicos, que es justo el modelo de "versión derivada de otra".

**Ampliaciones técnicas (no vistas en el PDF):** recorridos DFS/BFS iterativos, ancestro común más cercano, serialización plana JSON, estrategias de eliminación y complejidad espacial. El PDF solo muestra el recorrido en orden de un árbol binario.

## 4. Diseño de la estructura de datos

- **`MusicNode`**: id único, nombre, `parent_id`, notas (tupla inmutable de `Note`), tempo, compás, tonalidad opcional, descripción, fecha y referencias a sus hijos. Las versiones son **inmutables**: crear una variación nunca modifica la versión base (requisito de no sobrescribir el historial). Los hijos solo se manipulan desde `MusicTree` (métodos internos con `_`); desde fuera `children` es una tupla de solo lectura.
- **`MusicTree`**: un árbol por composición. Sin diccionarios de índice: toda búsqueda, inserción y recorrido navega nodos reales.
- **`CompositionManager`**: administra el *bosque* (una lista de árboles, una raíz por composición), genera ids únicos, valida reglas de negocio y guarda. Cada mutación hace snapshot, ejecuta, guarda y **revierte si falla el guardado**.
- **Persistencia**: JSON plano (lista de registros con `parent_id`, en orden BFS). Al cargar, un diccionario temporal enlaza padres e hijos (solo para reconstruir), luego se **valida**: una raíz, sin ids duplicados, sin padres inexistentes, sin ciclos ni nodos desconectados. Si el archivo está corrupto se informa y no se sobrescribe. Escritura atómica (`.tmp` + `os.replace`).
- **Recorridos iterativos** (pila / cola explícita): un árbol en forma de cadena de 100 000 nodos no provoca `RecursionError`.
- **MIDI y WAV sin dependencias**: el MIDI se escribe a mano (formato 0, instrumento *Pan Flute*) y el WAV se sintetiza con `wave`. Por eso `music21` no es necesario y la exportación nunca falla por una biblioteca ausente. 1 pulso = 1 negra.
- **Visualización**: `st.graphviz_chart` con DOT generado recorriendo el árbol en memoria (no hay una estructura gráfica paralela).

## 5. Algoritmos y complejidad

Sea *n* = nodos del árbol, *h* = altura, *w* = ancho máximo de un nivel, *d* = grado del nodo. Los árboles **no están balanceados**, por eso no se afirma complejidad logarítmica: en el peor caso (cadena de versiones) *h = n*.

| Algoritmo | Método | Tiempo | Espacio extra |
|---|---|---|---|
| Inserción | `insert` | O(n): recorre todo el árbol para verificar id único y ubicar al padre | O(h) |
| Búsqueda por id | `find_by_id` | O(n) peor caso | O(h) |
| Búsqueda por nombre | `find_by_name` | O(n · L), L = largo del nombre; devuelve todas las coincidencias, sin tildes ni mayúsculas | O(h + k) |
| DFS (preorden) | `dfs` | O(n) | O(h) en cadena, hasta O(n) en estrella (la pila guarda hermanos) |
| BFS | `bfs`, `bfs_levels` | O(n) | O(w) |
| Nivel / camino / padre | `level_of`, `path_to` | O(n) | O(h) |
| Altura, peso, hojas, grado máx. | `height`, `weight`, `leaf_count`, `max_degree` | O(n) | O(h) |
| Grado de un nodo | `degree_of` | O(n) por la búsqueda; O(1) una vez localizado | O(h) |
| Descendientes de todos los nodos | `profiles` | O(n) (una pasada inversa del preorden) | O(n) |
| Eliminación | `delete_node` | O(n) (`path_to`) + O(tamaño de la rama) en modo rama; O(d) en modo reasignar | O(h) |
| Comparación | `VersionComparator.compare` | O(a·b) peor caso (`difflib`), a y b = notas | O(a+b) |
| Carga JSON | `from_records` | O(n) | O(n) |

### Resultados medidos (`python Tests/BenchmarkTree.py`, tiempos en ms, mejor de 3)

| forma | n | altura | buscar último | DFS | BFS | stats | insertar |
|---|---:|---:|---:|---:|---:|---:|---:|
| balanceado (4 hijos) | 1 000 | 6 | 0.64 | 0.66 | 0.38 | 1.57 | 0.98 |
| balanceado | 10 000 | 8 | 1.93 | 3.03 | 1.82 | 7.62 | 4.19 |
| balanceado | 100 000 | 10 | 5.60 | 32.54 | 21.11 | 75.01 | 41.88 |
| estrella | 1 000 | 2 | 0.29 | 0.28 | 0.17 | 0.69 | 0.38 |
| estrella | 10 000 | 2 | 2.97 | 2.82 | 1.78 | 7.80 | 4.70 |
| estrella | 100 000 | 2 | 34.94 | 33.57 | 21.88 | 94.50 | 170.02 |
| cadena | 1 000 | 1 000 | 0.31 | 0.30 | 0.19 | 0.72 | 0.41 |
| cadena | 10 000 | 10 000 | 3.49 | 3.17 | 1.92 | 7.58 | 4.31 |
| cadena | 100 000 | 100 000 | 36.54 | 32.94 | 23.48 | 81.22 | 45.55 |

Los tiempos crecen aproximadamente de forma lineal con *n*, como predice O(n). La búsqueda del último nodo en el árbol balanceado es más rápida que en cadena/estrella solo porque el último nodo en preorden queda antes de terminar el recorrido; no es una ventaja logarítmica. Los valores dependen del equipo en que se midieron.

### Eliminación controlada

- **Raíz**: nunca se elimina como variación (`ProtectedRootError`). Para borrar una composición hay que **escribir su nombre exacto**.
- **Hoja**: se elimina sola, con confirmación.
- **Con descendientes** el usuario elige: **(a) eliminar la rama completa** o **(b) eliminar solo esa versión y reasignar sus hijos al padre** (sus `parent_id` se actualizan y los niveles bajan en 1). Ambas requieren confirmación y se verifica la integridad en las pruebas.

## 6. Uso de la aplicación

1. **Panel principal**: estadísticas, lista de composiciones y estado vacío con botón para cargar el ejemplo.
2. **Editor musical**: nombre, tonalidad (opcional), tempo, compás, descripción y notas (tabla o texto `C4:1 F#3:0.5 Bb4:2 R:1`).
3. **Variaciones**: elige cualquier versión; las notas vienen precargadas para editarlas. La descripción del cambio es obligatoria y no se acepta una variación idéntica a su base.
4. **Explorador del árbol**: diagrama, detalle (padre, hermanos, ramas), recorridos DFS/BFS, tabla de propiedades, búsqueda y eliminación.
5. **Historial y recuperación**: linaje raíz → versión, ramas que nacen de ella, tabla cronológica y botón «usar como base».
6. **Comparador**: atributos, notas alineadas, similitud y ancestro común.
7. **Exportar y escuchar**: descarga MIDI y vista previa de audio WAV.

## 7. Composición de ejemplo

El botón del panel principal ejecuta `build_demo`, que usa la API real (`create_composition` / `add_variation`). Son datos de demostración, marcados como «(ejemplo)». Salida real:

```
Motivo andino (ejemplo)
    └── Versión lenta
        └── Lenta con adorno
        └── Lenta en octava grave
    └── Ritmo en 6/8
        └── 6/8 con síncopa
            └── 6/8 síncopa con final largo
    └── Transposición a D menor
```
Altura 4, peso 8, grado máximo 3, 4 hojas, 3 ramas (además de la raíz).

## 8. Validación realizada

- `python -m unittest Tests.TestMusicTree`: **55 pruebas, OK** (notas, nodos, inserción, búsqueda, DFS/BFS, propiedades, eliminación en ambas estrategias, protección de raíz, integridad, comparación, JSON de ida y vuelta, archivos corruptos, ciclos, rollback ante fallo de guardado, MIDI decodificado, WAV).
- `python -m unittest Tests.TestApp`: **3 pruebas, OK**. Usan `streamlit.testing`: renderizan las 7 páginas sin errores, cargan el ejemplo y guardan una variación real. **No** simulan el uso de la tabla editable (`st.data_editor`) ni clics sobre el diagrama.
- El servidor `streamlit run` arrancó y respondió HTTP 200.
- **Capturas de pantalla: no se generaron.** El entorno de desarrollo no tenía navegador. Se recomienda revisar visualmente la interfaz al ejecutarla localmente.
- La reproducción del MIDI en un reproductor externo no se verificó; se comprobó la estructura decodificándolo con un lector propio en las pruebas.

## 9. Funcionalidades

**Implementadas:** árbol n-ario propio; inserción, búsqueda por id y por nombre, DFS, BFS, propiedades, eliminación controlada, comparación, persistencia JSON, 7 módulos de interfaz, exportación MIDI y audio WAV.

**Ampliaciones posibles (no implementadas):** clic sobre los nodos del diagrama, edición de nombre/descripción de una versión, transposición automática, partitura, soporte multiusuario/concurrente, deshacer, notas simultáneas (acordes), múltiples instrumentos, importación de MIDI.
