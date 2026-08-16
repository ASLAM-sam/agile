r"""Extract PDF attachments from a PST file.

Usage:
    python "import pypff, os.py"
    python "import pypff, os.py" --pst C:\path\mailbox.pst --out C:\Evidence\PDFs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterator

import pypff


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
DEFAULT_PST_PATH = PROJECT_DIR / "245123733173@mvsrec.edu.in.pst"
DEFAULT_OUTPUT_DIR = BACKEND_DIR / "extracted_pdfs"


def iter_folders(folder: pypff.folder) -> Iterator[pypff.folder]:
    """Yield a folder tree while skipping unreadable subfolders."""
    yield folder
    try:
        count = folder.get_number_of_sub_folders()
    except Exception as exc:
        print(f"Skipping unreadable folder: {exc}")
        return

    for index in range(count):
        try:
            child = folder.get_sub_folder(index)
        except Exception as exc:
            print(f"Skipping unreadable subfolder {index}: {exc}")
            continue
        yield from iter_folders(child)


def extract_pdfs(pst_path: Path, output_dir: Path) -> int:
    if not pst_path.exists():
        raise FileNotFoundError(f"PST file does not exist: {pst_path}")
    if pst_path.stat().st_size == 0:
        raise ValueError(f"PST file is empty: {pst_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    pst = pypff.file()
    extracted = 0
    message_number = 0

    try:
        pst.open(str(pst_path))
        for folder in iter_folders(pst.get_root_folder()):
            for message_index in range(folder.get_number_of_sub_messages()):
                message_number += 1
                try:
                    message = folder.get_sub_message(message_index)
                except Exception as exc:
                    print(f"Skipping unreadable message {message_number}: {exc}")
                    continue

                for attachment_index in range(message.get_number_of_attachments()):
                    try:
                        attachment = message.get_attachment(attachment_index)
                        size = attachment.get_size()
                        if size <= 0:
                            continue
                        data = attachment.read_buffer(size)
                    except Exception as exc:
                        print(
                            "Skipping unreadable attachment "
                            f"{message_number}:{attachment_index}: {exc}"
                        )
                        continue

                    if data[:4] != b"%PDF":
                        continue

                    output_path = output_dir / f"{message_number:04d}_{attachment_index}.pdf"
                    output_path.write_bytes(data)
                    extracted += 1
    finally:
        pst.close()

    return extracted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pst", type=Path, default=DEFAULT_PST_PATH, help="PST file path")
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUTPUT_DIR, help="PDF output directory"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(f"Reading PST: {args.pst}")
    print(f"Writing PDFs to: {args.out}")
    try:
        count = extract_pdfs(args.pst, args.out)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"Error: {exc}")
        return 1
    print(f"Done. Extracted {count} PDF file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
