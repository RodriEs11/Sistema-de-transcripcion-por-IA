"""Exportación del formato del editor: usa exclusivamente un informe ficticio."""
import sys
import json
from io import BytesIO
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docx import Document
from docx.oxml.ns import qn
from informe import aplicar_formato, escribir_docx, parrafos_docx, pagina


class EditorWordTest(unittest.TestCase):
    def test_margen_superior_predeterminado(self):
        cfg = json.loads((Path(__file__).resolve().parents[1] / "configuracion.ejemplo.json").read_text(encoding="utf-8"))
        self.assertEqual(pagina({})["margen_superior_cm"], 2.5)
        self.assertEqual(cfg["pagina"]["margen_superior_cm"], 2.5)
        self.assertEqual(cfg["lineas_vacias_para_encabezado"], 0)
        marcado = [{"segs": [("Informe ficticio", None, None)], "titulo": False, "linea": None}]
        archivo = BytesIO()
        escribir_docx(marcado, archivo, cfg)
        archivo.seek(0)
        doc = Document(archivo)
        self.assertAlmostEqual(doc.sections[0].top_margin.cm, 2.5, places=2)
        self.assertEqual(doc.paragraphs[0].text, "Informe ficticio")

    def test_formato_y_a4_en_word(self):
        cfg = {"fuente": "Tahoma", "tamano_fuente": 12, "lineas_vacias_para_encabezado": 6,
               "linea_vacia_entre_titulo_y_texto": True,
               "pagina": {"nombre": "A4", "ancho_cm": 21, "alto_cm": 29.7}}
        marcado = [{"segs": [(t, None, None)], "titulo": False, "linea": None}
                   for t in ["Informe ficticio", "", "", "Texto final."]]
        formato = {"v": 2, "parrafos": [{"t": "Informe ficticio", "a": "center", "r": [
            {"t": "Informe", "b": True, "i": True, "u": True, "x": True,
             "f": "Arial", "s": 24, "c": "#C00000", "h": "#FFFF00"}, {"t": " ficticio"}]}]}
        archivo = BytesIO()
        escribir_docx(marcado, archivo, cfg, formato)
        archivo.seek(0)
        doc = Document(archivo)
        self.assertAlmostEqual(doc.sections[0].page_width.cm, 21, places=2)
        self.assertAlmostEqual(doc.sections[0].page_height.cm, 29.7, places=2)
        p = doc.paragraphs[6]
        self.assertEqual(p.text, "Informe ficticio")
        r = p.runs[0]
        self.assertTrue(r.bold and r.italic and r.underline and r.font.strike)
        self.assertEqual(r.font.name, "Arial")
        self.assertEqual(r.font.size.pt, 24)
        self.assertEqual(str(r.font.color.rgb), "C00000")
        self.assertEqual(r._element.rPr.find(qn("w:shd")).get(qn("w:fill")), "FFFF00")
        self.assertEqual(doc.paragraphs[7].text, "")
        self.assertEqual(doc.paragraphs[8].text, "")
        self.assertEqual(doc.paragraphs[9].text, "Texto final.")

    def test_valida_formato_y_conserva_texto(self):
        pars = [{"segs": [("Texto", None, None)], "alin": "", "alin_def": "", "negrita": False}]
        aplicar_formato(pars, {"parrafos": [{"t": "Texto", "r": [
            {"t": "Texto", "s": 1000, "f": '<script>', "c": '<red>', "h": []}]}]})
        run = pars[0]["runs"][0]
        self.assertIsNone(run["s"])
        self.assertEqual(run["f"], "")
        self.assertEqual(run["c"], "")
        self.assertEqual(run["h"], "")
        self.assertEqual(run["t"], "Texto")


if __name__ == "__main__":
    unittest.main()
