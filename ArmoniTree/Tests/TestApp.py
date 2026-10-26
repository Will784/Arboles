import os
import tempfile
import unittest
from pathlib import Path

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None

APP_PATH = str(Path(__file__).resolve().parent.parent / "App.py")
PAGES = (
    "Panel principal", "Editor musical", "Variaciones", "Explorador del árbol",
    "Historial y recuperación", "Comparador", "Exportar y escuchar",
)


@unittest.skipIf(AppTest is None, "Streamlit no está instalado")
class TestApp(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.data_file = Path(self.directory.name) / "compositions.json"
        os.environ["ARMONITREE_DATA"] = str(self.data_file)

    def tearDown(self):
        os.environ.pop("ARMONITREE_DATA", None)
        self.directory.cleanup()

    def run_app(self):
        app = AppTest.from_file(APP_PATH, default_timeout=60)
        app.run()
        return app

    def test_every_page_renders_empty_without_errors(self):
        app = self.run_app()
        for page in PAGES:
            app.session_state["page"] = page
            app.run()
            self.assertEqual(len(app.exception), 0, msg=f"{page}: {[e.value for e in app.exception]}")

    def test_demo_loading_and_every_page_with_data(self):
        app = self.run_app()
        next(button for button in app.button if button.label == "Cargar composición de ejemplo").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(self.data_file.exists())
        self.assertEqual(app.session_state["page"], "Explorador del árbol")
        for page in PAGES:
            app.session_state["page"] = page
            app.run()
            self.assertEqual(len(app.exception), 0, msg=f"{page}: {[e.value for e in app.exception]}")

    def test_variation_saved_from_text_mode(self):
        app = self.run_app()
        next(button for button in app.button if button.label == "Cargar composición de ejemplo").click().run()
        app.session_state["page"] = "Variaciones"
        app.run()
        next(radio for radio in app.radio if radio.label == "Modo de entrada de notas").set_value("Texto").run()
        next(area for area in app.text_area if area.label.startswith("¿Qué modificaste")).set_value("Cambio de prueba")
        next(area for area in app.text_area if area.label == "Secuencia").set_value("A4:1 C5:1 E5:4")
        next(button for button in app.button if button.label == "Guardar variación").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.error), 0, msg=[e.value for e in app.error])
        self.assertIn("Cambio de prueba", self.data_file.read_text(encoding="utf-8"))
        self.assertEqual(app.session_state["page"], "Explorador del árbol")


if __name__ == "__main__":
    unittest.main()
