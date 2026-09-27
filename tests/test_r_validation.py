import os
import unittest
from unittest.mock import patch

from cttir_model.errors import ProjectError
from cttir_model.r_validation import parse_r, run_worker


class SandboxBoundaryTests(unittest.TestCase):
    def test_no_unsandboxed_fallback(self):
        with patch("cttir_model.r_validation.shutil.which", return_value=None):
            with self.assertRaisesRegex(ProjectError, "no unsandboxed fallback"):
                parse_r("base::sum(1)")


@unittest.skipUnless(os.environ.get("CTTIR_TEST_SANDBOX") == "1", "Explicit Linux R sandbox tier")
class RValidationTests(unittest.TestCase):
    def test_namespace_isolation_and_fixed_fixtures(self):
        self.assertIn("isolated", run_worker("isolation"))
        self.assertIn("fixture_passed", run_worker("fixture"))

    def test_parser_does_not_execute_input(self):
        value = parse_r('base::system(command="exit 77")')
        self.assertTrue(value["parsed"])
        self.assertFalse(value["executed"])
        self.assertFalse(value["api_checked"])

    def test_invalid_and_dynamic_code_fail_closed(self):
        self.assertFalse(parse_r("x <- (")["parsed"])
        for text in ['get("system")("bad")', 'base:::system("bad")', 'source("file.R")']:
            self.assertFalse(parse_r(text)["static_subset_supported"])

    def test_named_arguments_checked_against_explicit_catalog(self):
        catalog = {"fixtureR::align": {"approved": True, "version": "1.0", "arguments": ["x", "ids"]}}
        good = parse_r("fixtureR::align(x = data, ids = samples)", catalog)
        self.assertTrue(good["api_checked"])
        self.assertFalse(parse_r("fixtureR::align(unknown = samples)", catalog)["api_checked"])
        self.assertFalse(parse_r("fixtureR::invented(x = data)", catalog)["api_checked"])
