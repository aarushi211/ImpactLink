import unittest
from io import BytesIO

from docx import Document

from services.parser import _extract_docx_text


class DocxExtractionTests(unittest.TestCase):
    def test_extracts_paragraphs_and_table_content(self):
        document = Document()
        document.add_paragraph("Youth Community Access Grant Program")
        table = document.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "Outdoor education"
        table.cell(0, 1).text = "Los Angeles youth"

        file_bytes = BytesIO()
        document.save(file_bytes)

        extracted = _extract_docx_text(file_bytes.getvalue())

        self.assertIn("Youth Community Access Grant Program", extracted)
        self.assertIn("Outdoor education | Los Angeles youth", extracted)


if __name__ == "__main__":
    unittest.main()
