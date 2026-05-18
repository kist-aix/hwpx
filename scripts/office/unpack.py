#!/usr/bin/env python3
"""Unpack an HWPX file into a directory with pretty-printed XML.

Usage:
    python unpack.py input.hwpx output_dir/
"""

import argparse
import os
import sys
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from lxml import etree

# Hardened parser: no external entity resolution, no DTD loading, no network
# access, bounded tree size — defends against XXE / billion-laughs payloads
# in untrusted .hwpx input. HWPX uses only the predefined XML entities, so
# this does not affect legitimate documents.
_SAFE_XML_PARSER = etree.XMLParser(
    resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False
)


def _safe_dest(output_root: Path, entry: str) -> Path:
    """Resolve a ZIP entry name under output_root, rejecting path traversal."""
    entry_path = PurePosixPath(entry)
    if entry_path.is_absolute() or any(part == ".." for part in entry_path.parts):
        raise SystemExit(f"Refusing unsafe archive entry: {entry!r}")
    dest = (output_root / entry).resolve()
    root = output_root.resolve()
    if dest != root and root not in dest.parents:
        raise SystemExit(f"Archive entry escapes output directory: {entry!r}")
    return dest


def unpack(hwpx_path: str, output_dir: str) -> None:
    """Extract HWPX archive and pretty-print all XML files."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    with ZipFile(hwpx_path, "r") as zf:
        for entry in zf.namelist():
            if entry.endswith("/"):
                continue  # directory entry
            data = zf.read(entry)
            dest = _safe_dest(output, entry)
            dest.parent.mkdir(parents=True, exist_ok=True)

            if entry.endswith(".xml") or entry.endswith(".hpf"):
                try:
                    tree = etree.fromstring(data, parser=_SAFE_XML_PARSER)
                    etree.indent(tree, space="  ")
                    pretty = etree.tostring(
                        tree,
                        pretty_print=True,
                        xml_declaration=True,
                        encoding="UTF-8",
                    )
                    dest.write_bytes(pretty)
                    continue
                except etree.XMLSyntaxError:
                    pass  # Fall through to raw write

            dest.write_bytes(data)

    print(f"Unpacked: {hwpx_path} -> {output_dir}")
    print(f"  Files: {len(list(output.rglob('*')))} entries")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unpack HWPX file into a directory with pretty-printed XML"
    )
    parser.add_argument("input", help="Path to .hwpx file")
    parser.add_argument("output", help="Output directory path")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    unpack(args.input, args.output)


if __name__ == "__main__":
    main()
