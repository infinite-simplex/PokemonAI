#!/usr/bin/env python3
"""
Transpile C99-style variable declarations to C89-compatible form.
All declarations are hoisted to the top of their enclosing block.
For-loop init declarations are extracted and hoisted too.

Usage: modernize.py <file1.c> [file2.c ...]
Files are modified in-place.
"""

import re
import sys

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

TYPE_SPEC = (
    r"(?:void|char|short|int|long|float|double|"
    r"signed|unsigned|struct|union|enum|"
    r"const|volatile|static|extern|register|"
    r"typedef|bool)"
)

# Matches a full declaration statement, possibly with an initialiser.
# Group 1 = full declaration text (type + name + optional pointer stars/brackets).
DECL_RE = re.compile(
    r"^(\s*)"                            # leading whitespace (group 1)
    r"("                                 # group 2: the full declarator
    r"(?:" + TYPE_SPEC + r"\s+)+"        #   one or more type keywords
    r"\**\s*[A-Za-z_]\w*"               #   optional pointer stars + identifier
    r"(?:\s*\[[^\]]*\])?"               #   optional array brackets
    r")"
    r"(\s*=\s*.+?)?"                     # group 3: optional initialiser (lazy)
    r"\s*;\s*$",                         # semicolon
    re.MULTILINE,
)

# Matches the init clause inside   for ( <type> <name> = ... ;
FOR_DECL_RE = re.compile(
    r"^(\s*for\s*\(\s*)"                 # group 1: "for ("
    r"("                                 # group 2: the declarator
    r"(?:" + TYPE_SPEC + r"\s+)+"
    r"[A-Za-z_*]\w*"
    r")"
    r"(\s*=\s*[^;]+)?"                   # group 3: optional "= expr"
    r"(;)",                              # group 4: the semicolon
)

CONTROL_KEYWORDS = {"if", "else", "for", "while", "do", "switch",
                    "return", "break", "continue", "goto", "sizeof"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_declaration(line: str) -> bool:
    """Return True if the line is a plain variable/type declaration."""
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith(("#", "//", "typedef")):
        return False
    first = stripped.split()[0].rstrip("(")
    if first in CONTROL_KEYWORDS:
        return False
    return DECL_RE.match(line) is not None


def var_name_from_decl(decl_text: str) -> str:
    """Extract the bare variable name from a declarator string."""
    # Remove pointer stars, array brackets, then take the last word.
    cleaned = re.sub(r"[\*\[\]0-9]", " ", decl_text)
    return cleaned.split()[-1]


# ---------------------------------------------------------------------------
# Core: process one brace-delimited block
# ---------------------------------------------------------------------------

def process_block_lines(lines: list[str]) -> list[str]:
    """
    Given the *interior* lines of a single block (no outer braces),
    return them rewritten so that all declarations are hoisted to the top.

    Nested blocks are handled recursively.
    """
    hoisted_decls: list[str] = []   # "type name;"  lines (no initialisers)
    body_lines:    list[str] = []   # everything else (assignments, stmts …)

    i = 0
    while i < len(lines):
        line = lines[i]

        # ── Nested block: collect and recurse ───────────────────────────
        if "{" in line or (line.strip() == "{"):
            # Collect from the opening brace to the matching closing brace.
            block_lines, consumed = collect_block(lines, i)
            # block_lines[0]  = line containing "{"
            # block_lines[-1] = line containing "}"
            inner = block_lines[1:-1]
            processed_inner = process_block_lines(inner)
            body_lines.append(block_lines[0])
            body_lines.extend(processed_inner)
            body_lines.append(block_lines[-1])
            i += consumed
            continue

        # ── for-loop with an inline declaration ─────────────────────────
        m = FOR_DECL_RE.match(line)
        if m:
            prefix    = m.group(1)   # "    for ( "
            decl_text = m.group(2)   # "int i"
            init_expr = m.group(3)   # " = 0"  or None
            semi      = m.group(4)   # ";"

            indent = re.match(r"^\s*", line).group(0)
            var    = var_name_from_decl(decl_text)

            hoisted_decls.append(f"{indent}{decl_text.strip()};")

            if init_expr:
                # Replace "for (int i = 0;" → "for (i = 0;"
                new_line = FOR_DECL_RE.sub(
                    lambda _: f"{prefix}{var}{init_expr}{semi}", line, count=1
                )
            else:
                # No initialiser: "for (int i;" → "for (;"
                new_line = FOR_DECL_RE.sub(
                    lambda _: f"{prefix}{semi}", line, count=1
                )

            body_lines.append(new_line)
            i += 1
            continue

        # ── Plain declaration ────────────────────────────────────────────
        if is_declaration(line):
            stripped = line.strip()
            indent   = re.match(r"^\s*", line).group(0)

            mm = DECL_RE.match(line)
            if mm:
                decl_text = mm.group(2).strip()   # e.g. "int x"
                init_part = mm.group(3)            # e.g. " = 3"  or None

                hoisted_decls.append(f"{indent}{decl_text};")

                if init_part:
                    var = var_name_from_decl(decl_text)
                    rhs = init_part.strip().lstrip("=").strip()
                    body_lines.append(f"{indent}{var} = {rhs};")
                # else: pure declaration – no body line needed
            else:
                # Fallback: keep as-is
                body_lines.append(line)

            i += 1
            continue

        # ── Ordinary statement – keep verbatim ──────────────────────────
        body_lines.append(line)
        i += 1

    return hoisted_decls + body_lines


def collect_block(lines: list[str], start: int) -> tuple[list[str], int]:
    """
    Starting at `start` (a line that contains '{'), collect lines up to and
    including the matching '}'. Returns (block_lines, number_of_lines_consumed).
    """
    depth    = 0
    collected = []
    for j in range(start, len(lines)):
        line = lines[j]
        collected.append(line)
        depth += line.count("{") - line.count("}")
        if depth == 0:
            return collected, j - start + 1
    # Unmatched brace – return whatever we have
    return collected, len(lines) - start


# ---------------------------------------------------------------------------
# Top-level rewriter
# ---------------------------------------------------------------------------

def modernize(source: str) -> str:
    """Rewrite an entire C source file."""
    lines = source.splitlines(keepends=True)

    # Strip trailing newlines from each line for uniform processing,
    # then re-add them at the end.
    stripped = [l.rstrip("\n") for l in lines]

    result = _rewrite_lines(stripped)
    return "\n".join(result) + "\n"


def _rewrite_lines(lines: list[str]) -> list[str]:
    """
    Walk the top-level line list.  When we encounter a '{', recurse into
    that block, rewrite its interior, and emit it.
    """
    output = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # Does this line open a brace?  (Could be "{\n" alone, or "void f() {")
        if "{" in line:
            block_lines, consumed = collect_block(lines, i)
            # Rewrite the interior recursively
            inner    = [l.rstrip("\n") for l in block_lines[1:-1]]
            processed = process_block_lines(inner)

            output.append(block_lines[0])
            output.extend(processed)
            output.append(block_lines[-1])
            i += consumed
        else:
            output.append(line)
            i += 1

    return output


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("usage: modernize.py <file.c> [file2.c ...]", file=sys.stderr)
        sys.exit(1)

    for filename in sys.argv[1:]:
        try:
            with open(filename, "r", encoding="utf-8") as f:
                source = f.read()

            result = modernize(source)

            with open(filename, "w", encoding="utf-8") as f:
                f.write(result)

            print(f"modernized: {filename}")
        except OSError as e:
            print(f"error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
