"""Registration pull request checks against throwaway git repositories."""

import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import check_registration as checker

REPOSITORY = "UFcompressor/UFL_MODELS"
ADMIN = ("E53klasky", 173562962)
ALICE, BOB = ("Alice", 101), ("Bob", 102)


def variant(data, value=b"\x00\x00\x80\x3f"):
    """A distinct but valid checkpoint: one float of the first storage changed."""
    source, out = zipfile.ZipFile(io.BytesIO(data)), io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as target:
        for info in source.infolist():
            content = source.read(info)
            if info.filename.endswith("/data/0"):
                content = value + content[4:]
            target.writestr(info, content)
    return out.getvalue()


class PullRequestTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.repo = Path(self.directory.name)
        reference = json.loads((ROOT / "model_catalog.json").read_text())
        reference = next(
            m for m in reference["models"] if m["name"] == reference["default_model"]
        )["filename"]
        for name in (
            "model_catalog.json",
            "README.md",
            "registry_policy.json",
            reference,
        ):
            shutil.copy(ROOT / name, self.repo / name)
        (self.repo / "test").mkdir()
        shutil.copy(
            Path(__file__).with_name("check_registration.py"), self.repo / "test"
        )
        self.reference = (self.repo / reference).read_bytes()
        self.git("init", "--quiet", "-b", "main")
        self.commit("Database")

    def tearDown(self):
        self.directory.cleanup()

    def git(self, *args):
        return subprocess.run(
            [
                "git",
                "-C",
                str(self.repo),
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@t",
                *args,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", message)
        return self.git("rev-parse", "HEAD")

    def catalog(self):
        return json.loads((self.repo / "model_catalog.json").read_text())

    def write(self, catalog):
        (self.repo / "model_catalog.json").write_text(
            json.dumps(catalog, indent=2) + "\n"
        )
        readme = self.repo / "README.md"
        readme.write_text(checker.render_readme(catalog, readme.read_text()))

    def request(self, branch, author=ALICE, name="alice_model", data=None, **changes):
        """Build a branch the way register_model.py add does; return its head."""
        self.git("switch", "--quiet", "-c", branch, "main")
        filename = f"{name}.pt"
        data = variant(self.reference) if data is None else data
        (self.repo / filename).write_bytes(data)
        added = self.commit(f"Add {filename}")
        fields = dict(
            name=name,
            display_name="Alice's model",
            description="Fine-tuned for a test",
            filename=filename,
            sha256=hashlib.sha256(data).hexdigest(),
            min_dims=3,
            max_dims=5,
            owner=author[0],
            owner_id=author[1],
            url=f"https://raw.githubusercontent.com/{REPOSITORY}/{added}/{filename}",
        )
        catalog = checker.register(self.catalog(), **fields)
        catalog["models"][-1].update(changes)
        self.write(catalog)
        head = self.commit(f"Register {name}")
        self.git("switch", "--quiet", "main")
        return head

    def retirement(self, branch, name, default_model=None):
        self.git("switch", "--quiet", "-c", branch, "main")
        self.write(checker.retire(self.catalog(), name, default_model))
        head = self.commit(f"Retire {name}")
        self.git("switch", "--quiet", "main")
        return head

    def check(self, head, author=ALICE):
        return checker.check_pull_request(
            self.repo, "main", head, author[0], author[1], REPOSITORY
        )

    def merge(self, head):
        self.git("merge", "--quiet", "--no-ff", "-m", "Merge", head)

    def test_valid_registration_is_accepted(self):
        summary = self.check(self.request("a"))
        self.assertIn("register alice_model as ufl:6@sha256:", summary)
        self.assertIn("329 float32 tensors", summary)

    def test_owner_comes_from_the_pull_request_author(self):
        head = self.request("a", owner="E53klasky", owner_id=173562962)
        with self.assertRaisesRegex(
            ValueError, "Owner must be the pull request author"
        ):
            self.check(head)
        with self.assertRaisesRegex(
            ValueError, "Owner must be the pull request author"
        ):
            self.check(self.request("b", name="other"), author=BOB)

    def test_registration_number_and_fields_cannot_be_chosen(self):
        for branch, change, message in (
            (
                "number",
                dict(registration_id=99, id="ufl:99@sha256:" + "0" * 64),
                "SHA|number",
            ),
            ("extra", dict(registration_issue=1), "unexpected catalog fields"),
            ("arch", dict(architecture="other"), "architecture"),
        ):
            with self.subTest(branch=branch), self.assertRaisesRegex(
                ValueError, message
            ):
                self.check(self.request(branch, **change))

    def test_files_that_are_not_caesar_checkpoints_are_rejected(self):
        bad = {
            "text": b"not a model" * 558_000,
            "small": self.reference[: len(self.reference) // 2],
            "nan": variant(self.reference, b"\x00\x00\xc0\x7f"),
        }
        for name, data in bad.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.check(self.request(name, name=name, data=data))

    def test_only_the_catalog_readme_and_checkpoint_may_change(self):
        self.git("switch", "--quiet", "-c", "base-for-tamper", "main")
        head = self.request("tamper")
        self.git("switch", "--quiet", "tamper")
        (self.repo / "test" / "check_registration.py").write_text("print('Accepted')\n")
        head = self.commit("Also change the checks")
        self.git("switch", "--quiet", "main")
        with self.assertRaisesRegex(
            ValueError, "also changed: \\['test/check_registration.py'\\]"
        ):
            self.check(head)

    def test_url_must_name_the_commit_that_adds_the_checkpoint(self):
        base = self.git("rev-parse", "main")
        head = self.request(
            "a",
            url=f"https://raw.githubusercontent.com/{REPOSITORY}/{base}/alice_model.pt",
        )
        with self.assertRaisesRegex(ValueError, "commit that adds the checkpoint"):
            self.check(head)
        head = self.request("b", name="b", url="https://example.com/b.pt")
        with self.assertRaisesRegex(ValueError, "URL must be"):
            self.check(head)

    def test_stale_readme_is_rejected(self):
        head = self.request("a")
        self.git("switch", "--quiet", "a")
        (self.repo / "README.md").write_text("# Edited\n")
        head = self.commit("Edit README")
        self.git("switch", "--quiet", "main")
        with self.assertRaisesRegex(ValueError, "README"):
            self.check(head)

    def test_duplicate_name_or_checkpoint_is_rejected(self):
        self.merge(self.request("a"))
        with self.assertRaisesRegex(ValueError, "Duplicate name"):
            self.check(
                self.request("b", data=variant(self.reference, b"\x00\x00\x00\x40"))
            )
        with self.assertRaisesRegex(ValueError, "Duplicate sha256"):
            self.check(self.request("c", name="copy"))

    def test_owner_can_retire_and_other_users_cannot(self):
        self.merge(self.request("a"))
        head = self.retirement("retire", "alice_model")
        with self.assertRaisesRegex(ValueError, "Only the model owner"):
            self.check(head, author=BOB)
        self.assertIn("retire alice_model", self.check(head))
        self.assertIn("retire alice_model", self.check(head, author=ADMIN))
        with self.assertRaisesRegex(ValueError, "Only the model owner"):
            self.check(self.retirement("eels", "eelsM1"))

    def test_default_changes_require_an_administrator(self):
        head = self.retirement("default", "caesar_v2", default_model="caesar_v1")
        with self.assertRaisesRegex(ValueError, "Only the model owner"):
            self.check(head)
        self.assertIn("retire caesar_v2", self.check(head, author=ADMIN))
        with self.assertRaisesRegex(ValueError, "requires a replacement default"):
            checker.retire(self.catalog(), "caesar_v2")
        # The same change made by hand instead of with register_model.py
        catalog = checker.retire(self.catalog(), "caesar_v2", "caesar_v1")
        catalog["default_model"] = "caesar_v2"
        self.git("switch", "--quiet", "-c", "no-default", "main")
        self.write(dict(catalog, default_model="caesar_v1"))
        (self.repo / "model_catalog.json").write_text(
            json.dumps(catalog, indent=2) + "\n"
        )
        head = self.commit("Retire the default by hand")
        self.git("switch", "--quiet", "main")
        with self.assertRaisesRegex(ValueError, "Default must be an active model"):
            self.check(head, author=ADMIN)

    def test_retired_names_stay_reserved(self):
        self.merge(self.request("a"))
        self.merge(self.retirement("retire", "alice_model"))
        with self.assertRaisesRegex(ValueError, "Duplicate name"):
            self.check(
                self.request("again", data=variant(self.reference, b"\x00\x00\x00\x40"))
            )

    def test_requests_built_on_an_old_database_conflict(self):
        late = self.request("late", name="bob_model", author=BOB)
        self.merge(self.request("first"))
        with self.assertRaisesRegex(ValueError, "conflicts|registration number"):
            self.check(late, author=BOB)

    def test_pickled_code_is_refused(self):
        class Payload:
            def __reduce__(self):
                return (print, ("executed",))

        import pickle

        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as archive:
            archive.writestr("x/data.pkl", pickle.dumps({"w": Payload()}))
        with self.assertRaisesRegex(ValueError, "only float32 tensors"):
            checker.read_checkpoint(out.getvalue())

    def test_registered_checkpoints_match_the_default_network(self):
        catalog = json.loads((ROOT / "model_catalog.json").read_text())
        for model in catalog["models"]:
            path = ROOT / model["filename"]
            if path.exists():
                with self.subTest(model=model["name"]):
                    self.assertGreater(
                        checker.check_checkpoint(path.read_bytes(), self.reference), 0
                    )


if __name__ == "__main__":
    unittest.main()
