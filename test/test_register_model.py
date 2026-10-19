"""Database invariants; registration implementation tests live in CAESAR."""

import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CatalogTests(unittest.TestCase):
    def test_unique_immutable_identities_and_owners(self):
        catalog = json.loads((ROOT / "model_catalog.json").read_text())
        models = catalog["models"] + catalog.get("retired_models", [])
        for key in ("name", "registration_id", "id", "sha256", "filename"):
            self.assertEqual(len({model[key] for model in models}), len(models))
        for model in models:
            self.assertEqual(
                model["id"], f"ufl:{model['registration_id']}@sha256:{model['sha256']}"
            )
            self.assertGreater(model["owner_id"], 0)
            self.assertTrue(model["owner"])
            self.assertRegex(
                model["url"],
                r"^https://raw\.githubusercontent\.com/[^/]+/[^/]+/[0-9a-f]{40}/[A-Za-z0-9_-]+\.pt$",
            )
        self.assertIn(
            catalog["default_model"], {model["name"] for model in catalog["models"]}
        )

    def test_administrator_policy_has_stable_ids(self):
        policy = json.loads((ROOT / "registry_policy.json").read_text())
        self.assertEqual(policy["schema_version"], 1)
        self.assertIn(173562962, [admin["id"] for admin in policy["admins"]])


if __name__ == "__main__":
    unittest.main()
