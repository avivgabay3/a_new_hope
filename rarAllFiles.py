"""Compatibility notice for the retired WinRAR post-processing utility.

Recordings are now finalized directly by :mod:`recording_service`. Requiring a
machine-specific WinRAR installation was a major source of data loss at shutdown.
"""


def main() -> None:
    print(
        "RAR post-processing is no longer used. "
        "A New Hope now finalizes each recording safely when it stops."
    )


if __name__ == "__main__":
    main()
