"""Client for listing and filtering local files."""

import glob
from pathlib import Path


class LocalFileClient:
    """Client for interacting with locally stored files"""

    def list_local_files(
        self,
        path: str,
        pattern: str | None = None,
        exclude_files: list[str] | None = None,
        limit: int | None = None,
    ) -> list[Path]:
        """
        List all files in a local directory, optionally filtering by extensions.

        Args:
            path (str): The directory path to list files from.
            pattern (str | None): The glob pattern to filter files.
            limit (int | None): The maximum number of files to return.

        Returns:
            list[Path]: A list of file paths.
        """
        # If path is a file, return it as a list
        if Path(path).is_file():
            return [Path(path)]

        files = (
            glob.glob(f"{path.rstrip('/')}/{pattern.lstrip('/')}")
            if pattern
            else glob.glob(f"{path.rstrip('/')}/*")
        )
        files = sorted(files)

        file_paths = []
        for f in files:
            if Path(f).is_file():
                if exclude_files and Path(f).name in exclude_files:
                    continue

                file_paths.append(Path(f))
                if limit and len(file_paths) >= limit:
                    break

        return file_paths
