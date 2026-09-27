import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cttir_model.books import chunk_pages, ingest_library, search_library, training_plan
from cttir_model.errors import ProjectError
from cttir_model.provenance import atomic_json, read_json


class BookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        raw = b'%PDF-1.4\nSynthetic metadata-only test fixture'
        (self.root/'book.pdf').write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        self.source = {'source_id': 'book:'+digest, 'path': 'book.pdf', 'sha256': digest,
                       'title': 'Synthetic book', 'pages': 2, 'bytes': len(raw),
                       'training_requested_by_user': True, 'rights_status': 'pending_review',
                       'redistribution_allowed': False, 'completeness': 'front_matter_only'}
        atomic_json(self.root/'manifest.json', {'schema_version':1,'visibility':'local_only','sources':[self.source]})

    def ingest(self):
        with patch('cttir_model.books.extract_text', return_value='Preface to statistics\fTable of contents\f'):
            return ingest_library(self.root)

    def test_citations_are_page_bound_and_not_api_approval(self):
        chunks=chunk_pages('First page\fSecond page\f',self.source)
        self.assertEqual([row['pdf_page'] for row in chunks],[1,2])
        self.assertTrue(all(row['local_only'] and not row['api_verification'] for row in chunks))
        with self.assertRaises(ProjectError): chunk_pages('Wrong page count',self.source)

    def test_idempotent_local_index_search_and_training_plan(self):
        self.assertEqual(self.ingest()['books'][0]['chunks'],2)
        with patch('cttir_model.books.extract_text',side_effect=AssertionError):
            self.assertTrue(ingest_library(self.root)['books'][0]['reused'])
        result=search_library(self.root,'statistics')
        self.assertEqual(result['chunks'][0]['pdf_page'],1)
        plan=training_plan(self.root)
        self.assertEqual(plan['sources'][0]['training_use'],'awaiting_body_chapters')
        self.assertFalse(plan['training_ready'])
        self.assertEqual(plan['training_examples_created'],0)

    def test_changed_source_index_and_path_escape_fail(self):
        self.ingest()
        index_path=next((self.root/'index').glob('*.json'))
        index=read_json(index_path)
        index['chunks'][0]['text']='tampered'
        atomic_json(index_path,index)
        with self.assertRaises(ProjectError): search_library(self.root,'statistics')
        (self.root/'book.pdf').write_bytes(b'changed')
        with self.assertRaises(ProjectError): self.ingest()
        self.source['path']='../outside.pdf'
        atomic_json(self.root/'manifest.json',{'schema_version':1,'visibility':'local_only','sources':[self.source]})
        with self.assertRaises(ProjectError): self.ingest()
