#!/usr/bin/env python3
"""
Generate module-specific firrtl-cover.h and firrtl-cover.cpp from GEN_w*.v files.

Parses the GEN_w*_<type>.v black-box files that the CoverPointTransform emits,
determines which cover types are actually instantiated in the module RTL, and
produces the corresponding C++ DPI-C implementations plus the FIRRTLCoverPoint
structures needed by module_emu.cpp.

Usage:
    python gen_firrtl_cover.py <module_rtl_dir>
"""

import os
import re
import sys
from pathlib import Path


def parse_gen_files(module_dir: Path) -> dict[str, int]:
    """Extract {cover_type: COVER_TOTAL} from GEN_w*_<type>.v files."""
    cover_types: dict[str, int] = {}

    for fpath in sorted(module_dir.glob("GEN_w*_*.v")):
        m = re.match(r"GEN_w\d+_(\w+)\.v", fpath.name)
        if not m:
            continue
        ctype = m.group(1)

        content = fpath.read_text()
        m_total = re.search(r"parameter\s+COVER_TOTAL\s*=\s*(\d+)", content)
        if not m_total:
            continue
        total = int(m_total.group(1))

        if ctype in cover_types:
            assert cover_types[ctype] == total, (
                f"Conflicting COVER_TOTAL for {ctype}: "
                f"{cover_types[ctype]} vs {total}"
            )
        cover_types[ctype] = total

    return cover_types


def get_instantiated_types(module_dir: Path) -> set[str]:
    """Return cover types actually instantiated in the module's .sv files."""
    instantiated: set[str] = set()
    for sv in module_dir.glob("*.sv"):
        content = sv.read_text()
        for m in re.finditer(r"GEN_w\d+_(\w+)\s+#", content):
            instantiated.add(m.group(1))
    return instantiated


def generate(module_dir: Path, cover_types: dict[str, int]) -> None:
    n = len(cover_types)

    # ── firrtl-cover.h ───────────────────────────────────────────────
    header = [
        "#ifndef __FIRRTL_COVER_H__",
        "#define __FIRRTL_COVER_H__",
        "",
        "#include <cstdint>",
        "",
        "typedef struct {",
        "        uint8_t* points;",
        "  const uint64_t total;",
        "  const char*    name;",
        "  const char**   point_names;",
        "} FIRRTLCoverPoint;",
        "",
        "typedef struct {",
        "  const FIRRTLCoverPoint cover;",
        "  bool is_feedback;",
        "} FIRRTLCoverPointParam;",
        "",
        f"extern FIRRTLCoverPointParam firrtl_cover[{n}];",
        "",
        "#endif // __FIRRTL_COVER_H__",
        "",
    ]
    (module_dir / "firrtl-cover.h").write_text("\n".join(header))

    # ── firrtl-cover.cpp ─────────────────────────────────────────────
    src: list[str] = []
    src.append('#include "firrtl-cover.h"')
    src.append("")
    src.append("typedef struct {")
    for ctype, total in cover_types.items():
        src.append(f"  uint8_t {ctype}[{total}];")
    src.append("} CoverPoints;")
    src.append("static CoverPoints coverPoints;")
    src.append("")

    for ctype in cover_types:
        src.append(f'extern "C" void v_cover_{ctype}(uint64_t index) {{')
        src.append(f"  coverPoints.{ctype}[index] = 1;")
        src.append("}")
        src.append("")

    for ctype, total in cover_types.items():
        src.append(f"static const char *{ctype}_NAMES[] = {{")
        for i in range(total):
            src.append(f'  "{ctype}[{i}]",')
        src.append("};")
        src.append("")

    src.append(f"FIRRTLCoverPointParam firrtl_cover[{n}] = {{")
    for i, (ctype, total) in enumerate(cover_types.items()):
        feedback = "true" if i == 0 else "false"
        src.append(
            f'  {{ {{ coverPoints.{ctype}, {total}UL, "{ctype}", '
            f"{ctype}_NAMES }}, {feedback} }},"
        )
    src.append("};")
    src.append("")
    (module_dir / "firrtl-cover.cpp").write_text("\n".join(src))


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <module_rtl_dir>", file=sys.stderr)
        sys.exit(1)

    module_dir = Path(sys.argv[1])
    if not module_dir.is_dir():
        print(f"Not a directory: {module_dir}", file=sys.stderr)
        sys.exit(1)

    all_types = parse_gen_files(module_dir)
    if not all_types:
        sys.exit(0)

    instantiated = get_instantiated_types(module_dir)
    cover_types = {k: v for k, v in all_types.items() if k in instantiated}

    if not cover_types:
        sys.exit(0)

    generate(module_dir, cover_types)
    types_str = ", ".join(f"{k}({v})" for k, v in cover_types.items())
    print(f"[gen_firrtl_cover] {module_dir.name}: {types_str}")


if __name__ == "__main__":
    main()
