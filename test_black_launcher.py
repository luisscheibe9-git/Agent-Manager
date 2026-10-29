import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import black_launcher


class LauncherTests(unittest.TestCase):
    def test_explicit_data_directory_is_preserved(self):
        with tempfile.TemporaryDirectory() as path:
            with patch.object(black_launcher.subprocess, "run") as git:
                self.assertEqual(black_launcher.data_directory(environ={"AGENT_MANAGER_DATA_DIR": path}), Path(path).resolve())
                git.assert_not_called()

    def test_worktree_reuses_primary_checkout_data(self):
        with tempfile.TemporaryDirectory() as primary:
            result = subprocess.CompletedProcess([], 0, stdout=f"worktree {primary}\nHEAD abc\nbranch refs/heads/main\n\nworktree other\n")
            with patch.object(black_launcher.subprocess, "run", return_value=result):
                self.assertEqual(black_launcher.data_directory(environ={}), Path(primary).resolve())

    def test_without_git_uses_the_project_directory(self):
        with tempfile.TemporaryDirectory() as source:
            with patch.object(black_launcher.subprocess, "run", side_effect=OSError):
                self.assertEqual(black_launcher.data_directory(source, {}), Path(source).resolve())


if __name__ == "__main__":
    unittest.main()
