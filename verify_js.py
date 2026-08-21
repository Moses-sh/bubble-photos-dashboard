#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify all JS passed to Playwright page.evaluate() has valid syntax.

Catches the class of bug where Python string escapes get mangled and the
runtime JS string becomes invalid (e.g. bare quotes inside double-quoted
strings → 'SyntaxError: missing ) after argument list').

Usage:
    python3 verify_js.py [file.py ...]     # default: photos_update.py

Exit code 0 = all evaluate() JS blocks are syntactically valid.
Exit code 1 = at least one broken JS block (BLOCK DEPLOY).
"""
import ast
import os
import subprocess
import sys
import tempfile

DEFAULT_TARGET = 'photos_update.py'


def extract_js_blocks(src: str):
    """Return [(lineno, js_string)] for every self.page.evaluate(...) call."""
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != 'evaluate':
            continue
        if not node.args:
            continue
        arg = node.args[0]
        try:
            if isinstance(arg, ast.Constant):
                js = arg.value
            else:
                # string concatenation (e.g. 'a' + 'b') — evaluate at "compile time"
                js = eval(compile(ast.Expression(arg), '<js-expr>', 'eval'), {})
        except Exception:
            continue
        if isinstance(js, str) and js.strip():
            out.append((node.lineno, js))
    return out


def check_js(js: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, 'chunk.js')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(js)
        r = subprocess.run(['node', '--check', path], capture_output=True, text=True)
        return r.returncode == 0, r.stderr


def main() -> int:
    targets = sys.argv[1:] or [DEFAULT_TARGET]
    total_fail = 0
    for target in targets:
        if not os.path.exists(target):
            print(f'❌ {target}: file not found')
            total_fail += 1
            continue
        src = open(target, encoding='utf-8').read()
        blocks = extract_js_blocks(src)
        if not blocks:
            print(f'⚠️ {target}: no page.evaluate() calls found')
            continue
        print(f'🔎 {target}: {len(blocks)} evaluate() block(s)')
        file_fail = 0
        for lineno, js in blocks:
            ok, err = check_js(js)
            if ok:
                print(f'  ✅ line {lineno}: JS OK ({len(js)} chars)')
            else:
                file_fail += 1
                print(f'  ❌ line {lineno}: JS SYNTAX ERROR')
                for line in err.strip().splitlines()[:6]:
                    print(f'     {line}')
        total_fail += file_fail
        print(f'  → {len(blocks) - file_fail}/{len(blocks)} valid')
    if total_fail:
        print(f'\n❌❌ {total_fail} broken evaluate() block(s) — FIX BEFORE DEPLOY')
        return 1
    print('\n✅✅ All evaluate() JS blocks valid — safe to deploy')
    return 0


if __name__ == '__main__':
    sys.exit(main())
