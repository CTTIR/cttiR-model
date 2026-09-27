import json
import unittest

from cttir_model.errors import ProjectError
from cttir_model.models import resolve_model
from cttir_model.training import RESUME_KEYS, assistant_labels, check_resume


class ModelToolsTests(unittest.TestCase):
    def test_metadata_resolution_never_fetches_weight_or_remote_code(self):
        urls = []
        def fetch(url):
            urls.append(url)
            if '/api/models/' in url:
                return json.dumps({'sha': 'a' * 40, 'cardData': {'license': 'apache-2.0'},
                                   'siblings': [{'rfilename': name} for name in
                                                ['config.json', 'README.md', 'model.safetensors', 'custom.py']]}).encode()
            if url.endswith('config.json'):
                return b'{"model_type":"mistral3","quantization_config":{"quant_method":"fp8"}}'
            return b'Test-only metadata'
        result = resolve_model('owner/model', fetch=fetch)
        self.assertEqual(result['revision'], 'a' * 40)
        self.assertFalse(result['training_compatible'])
        self.assertIsNone(result['effective_base_fingerprint'])
        self.assertFalse(any(url.endswith(('.py', '.safetensors')) for url in urls))
        self.assertTrue(all('a' * 40 in url for url in urls[1:]))

    def test_mutable_and_wrong_pins_fail(self):
        with self.assertRaises(ProjectError):
            resolve_model('owner/model', 'main')
        with self.assertRaises(ProjectError):
            resolve_model('owner/model', 'b' * 40, fetch=lambda url: b'{"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}')

    def test_loss_mask_excludes_source_padding_and_does_not_truncate(self):
        self.assertEqual(assistant_labels([1, 2, 3, 4, 0], [0, 0, 1, 1, 0], [1, 1, 1, 1, 0], 8),
                         [-100, -100, 3, 4, -100])
        for arguments in [([1, 2], [0, 0], [1, 1], 4), ([1, 2], [0, 1], [1, 1], 1),
                          ([1], [1], [1], 4), ([1, 2], [0, 2], [1, 1], 4)]:
            with self.assertRaises(ProjectError):
                assistant_labels(*arguments)

    def test_resume_refuses_changed_tokenizer_data_or_optimizer(self):
        saved = {key: 'a' * 64 for key in RESUME_KEYS}
        check_resume(saved, dict(saved))
        for key in RESUME_KEYS:
            with self.assertRaises(ProjectError):
                check_resume(saved, {**saved, key: 'b' * 64})
