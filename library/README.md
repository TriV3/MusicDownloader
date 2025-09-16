# Library Output

This directory is used by the backend to store downloaded audio files.

- Default location can be changed via the `LIBRARY_DIR` environment variable.
- Files are named using the pattern `Artists - Title.ext`.
- During tests, when `DOWNLOAD_FAKE=1` is set, small placeholder files are created here.
- It is safe to delete files in this directory; the application will recreate them as needed.

If you plan to version-control this repository, consider ignoring audio files in this folder using a `.gitignore` entry such as:

```
/library/*
!/library/README.md
```
