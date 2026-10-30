"""Regression checks for rejection handling and malformed tensor metadata."""

import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import check_registration as checker


class ValidationRegressions(unittest.TestCase):
    def test_workflow_preserves_checker_failure_despite_forged_success_line(self):
        workflow = (
            Path(__file__).resolve().parents[1] / ".github/workflows/model-registry.yml"
        ).read_text()
        step = workflow.split("      - name: Check the request\n", 1)[1]
        script = step.split("        run: |\n", 1)[1].split("\n  merge:", 1)[0]
        script = "\n".join(line[10:] for line in script.splitlines())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "test").mkdir()
            (root / "test/check_registration.py").write_text(
                "print('Rejected: invalid checkpoint')\n"
                "print('Accepted: forged success')\n"
                "raise SystemExit(1)\n"
            )
            result = subprocess.run(
                ["bash", "-e", "-c", script],
                cwd=root,
                env={
                    "PATH": "/usr/bin:/bin",
                    "AUTHOR_TYPE": "User",
                    "HEAD_SHA": "unused",
                    "AUTHOR": "Alice",
                    "AUTHOR_ID": "101",
                    "REPOSITORY": "UFcompressor/UFL_MODELS",
                    "GITHUB_OUTPUT": str(root / "outputs"),
                },
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_archive_size_does_not_define_network_compatibility(self):
        reference = b"small archive"
        data = b"larger archive" * 100
        with patch.object(checker, "read_checkpoint", return_value={"w": (2, 3)}):
            self.assertEqual(checker.check_checkpoint(data, reference), 1)
        with patch.object(checker, "read_checkpoint", side_effect=[
            {"w": (2, 4)}, {"w": (2, 3)}
        ]):
            with self.assertRaisesRegex(ValueError, "wrong-shape"):
                checker.check_checkpoint(data, reference)

    def test_invalid_tensor_layouts_are_rejected(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as archive:
            archive.writestr("archive/data.pkl", b"unused")
            archive.writestr("archive/data/0", b"\0" * 4)
        for offset, shape, stride in (
            (-1, (1,), (1,)),
            (0, (-1,), (1,)),
            (0, (1,), (-1,)),
            (0, (1,), ()),
            (0.5, (1,), (1,)),
        ):
            tensor = checker._Tensor(("0", 1), offset, shape, stride)
            with self.subTest(offset=offset, shape=shape, stride=stride):
                with patch.object(checker, "_Unpickler") as unpickler:
                    unpickler.return_value.load.return_value = {"x": tensor}
                    with self.assertRaisesRegex(ValueError, "invalid tensor layout"):
                        checker.read_checkpoint(out.getvalue())


if __name__ == "__main__":
    unittest.main()
