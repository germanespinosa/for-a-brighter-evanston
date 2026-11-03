"""End-to-end PDF generation and freshness checks in a disposable repository."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'build_help_pdf.py'

class HelpDocsTests(unittest.TestCase):
    def test_pdf_build_and_stale_manual_detection(self):
        self.assertTrue(SCRIPT.exists(), 'Help PDF builder is not implemented')
        spec = importlib.util.spec_from_file_location('build_help_pdf', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in module.TRACKED:
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('# Working with Fabian\n\nNews approval and website voting.\n', encoding='utf-8')
            module.build(root)
            self.assertEqual(module.stale(root), [])
            from pypdf import PdfReader
            pdf = PdfReader(root / module.PDF)
            self.assertIn('News approval', ''.join(p.extract_text() for p in pdf.pages))
            changed = root / 'docs/agents/fabian-news.md'
            changed.write_text('Changed approval procedure', encoding='utf-8')
            self.assertIn('docs/agents/fabian-news.md', module.stale(root))
            changed = root / module.PDF
            changed.write_bytes(b'corrupt')
            self.assertIn(module.PDF, module.stale(root))

if __name__ == '__main__':
    unittest.main()
