#!/usr/bin/env python3
"""A JavaScript parser for the static guard (tools/fix-guard.py), with no dependency (2026-11-25).

The static guard reads an AI's change of I.K.E.'s own page scripts (fingerprint.js and the others) by
their syntax trees, not by their lines: rules on lines missed writes in other forms (a destructuring,
a loop's target, a second declarator) and reads of the page's environment in other spellings. The
guard runs from main on GitHub's runners, often copied alone into a temporary folder, so the parser
is a file of this repository: no package, no network, no Node at that time.

parse(source) returns the program as ESTree (the format of acorn and esprima): dictionaries with a
"type", "start" and "end" (offsets in the source) and the fields of each node. It reads the script
syntax of ECMAScript 2022 that a page script can use. It is strict where a difference from the browser
could hide code: anything it does not know is an error (JSSyntaxError), and so are the forms a page
script never needs and a reader can misread: a backslash outside a text (an escaped name: `\\u0073eed`
is `seed`), a line or paragraph separator outside a text (it ends a `//` comment in the browser), the
HTML-like comments `<!--` and `-->`, old octal numbers and escapes, and any character that is not ASCII
outside texts and comments. Checked against acorn 8.14 on every version of the page scripts in the
history of the repository (tests/test_no_regression.py runs the parser on today's).

    js-parse.py FILE        prints the tree as JSON
"""

import json
import re
import sys


class JSSyntaxError(Exception):
    pass


KEYWORDS = {"break", "case", "catch", "class", "const", "continue", "debugger", "default", "delete", "do",
            "else", "export", "extends", "finally", "for", "function", "if", "import", "in", "instanceof",
            "new", "return", "super", "switch", "this", "throw", "try", "typeof", "var", "void", "while",
            "with", "null", "true", "false", "enum"}
STRICT_RESERVED = {"implements", "interface", "package", "private", "protected", "public", "static", "yield",
                   "let"}
PUNCTUATORS = sorted("""{ } ( ) [ ] ; , < > <= >= == != === !== + - * / % ** ++ -- << >> >>> & | ^ ! ~ && || ??
? ?. : = += -= *= /= %= **= <<= >>= >>>= &= |= ^= &&= ||= ??= => . ...""".split(), key=len, reverse=True)
ASSIGN_OPS = {"=", "+=", "-=", "*=", "/=", "%=", "**=", "<<=", ">>=", ">>>=", "&=", "|=", "^=", "&&=", "||=",
              "??="}
BINARY = {"??": 1, "||": 1, "&&": 2, "|": 3, "^": 4, "&": 5, "==": 6, "!=": 6, "===": 6, "!==": 6,
          "<": 7, ">": 7, "<=": 7, ">=": 7, "instanceof": 7, "in": 7, "<<": 8, ">>": 8, ">>>": 8,
          "+": 9, "-": 9, "*": 10, "/": 10, "%": 10, "**": 11}
LOGICAL = {"||", "&&", "??"}
LINE_END = "\n\r"
ID_START = re.compile(r"[A-Za-z_$]")
ID_PART = re.compile(r"[A-Za-z0-9_$]*")
NUMBER = re.compile(r"0[xX][0-9a-fA-F](?:_?[0-9a-fA-F])*n?|0[oO][0-7](?:_?[0-7])*n?|0[bB][01](?:_?[01])*n?"
                    r"|(?:0|[1-9](?:_?[0-9])*)n"
                    r"|(?:(?:0|[1-9](?:_?[0-9])*)(?:\.(?:[0-9](?:_?[0-9])*)?)?|\.[0-9](?:_?[0-9])*)"
                    r"(?:[eE][+-]?[0-9](?:_?[0-9])*)?")
PUNCT = re.compile("|".join(re.escape(p) for p in PUNCTUATORS))


class Token:
    __slots__ = ("type", "value", "start", "end", "nl")

    def __init__(self, type_, value, start, end, nl):
        self.type, self.value, self.start, self.end, self.nl = type_, value, start, end, nl

    def __repr__(self):
        return "Token(%s %r @%d)" % (self.type, self.value, self.start)


def _check_chars(src):
    """Characters a page script never needs outside texts, that would read differently here and in the
    browser: refused by the lexer (they reach it only outside texts and comments) or here."""
    for i, ch in enumerate(src):
        if ch in "  ":
            # allowed inside a text only: the lexer refuses it elsewhere (a `//` comment ends there)
            continue
        if ord(ch) < 32 and ch not in "\t\n\r\x0b\x0c":
            raise JSSyntaxError("a control character at %d" % i)


class Parser:
    def __init__(self, src):
        _check_chars(src)
        self.src = src
        self.pos = 0
        self.tok = None
        self.prev_end = 0
        self.in_function = False
        self.in_generator = False
        self.in_async = False
        self.labels = []
        self.pending_shorthand = set()
        self.next()

    # --- lexer ---------------------------------------------------------------------------------

    def error(self, what, at=None):
        at = self.tok.start if at is None and self.tok is not None else (at or 0)
        line = self.src.count("\n", 0, at) + 1
        raise JSSyntaxError("%s (line %d)" % (what, line))

    def skip_space(self):
        """Skips white space and comments; True when a line ended on the way."""
        src, n, nl = self.src, len(self.src), False
        i = self.pos
        while i < n:
            ch = src[i]
            if ch in " \t\x0b\x0c﻿":
                i += 1
            elif ch in LINE_END:
                nl = True
                i += 1
            elif ch == "/" and src.startswith("//", i):
                j = i + 2
                while j < n and src[j] not in LINE_END:
                    if src[j] in "  ":
                        self.error("a line separator in a comment", j)
                    j += 1
                i = j
            elif ch == "/" and src.startswith("/*", i):
                j = src.find("*/", i + 2)
                if j < 0:
                    self.error("an unterminated comment", i)
                body = src[i + 2:j]
                if " " in body or " " in body:
                    self.error("a line separator in a comment", i)
                if "\n" in body or "\r" in body:
                    nl = True
                i = j + 2
            elif ch == "<" and src.startswith("<!--", i):
                self.error("an HTML-like comment", i)
            elif ch == "-" and src.startswith("-->", i) and (nl or i == 0):
                self.error("an HTML-like comment", i)
            else:
                break
        self.pos = i
        return nl

    def next(self):
        if self.tok is not None:
            self.prev_end = self.tok.end
        nl = self.skip_space()
        self.tok = self.read_token(nl)
        return self.tok

    def read_token(self, nl):
        src, i = self.src, self.pos
        if i >= len(src):
            return Token("eof", None, i, i, nl)
        ch = src[i]
        if ID_START.match(ch):
            j = ID_PART.match(src, i + 1).end()
            if j < len(src) and (src[j] == "\\" or ord(src[j]) > 127):
                self.error("an escaped or non-ASCII name", j)
            self.pos = j
            return Token("name", src[i:j], i, j, nl)
        if ch == "#":
            m = re.compile(r"#[A-Za-z_$][A-Za-z0-9_$]*").match(src, i)
            if not m:
                self.error("a stray #", i)
            self.pos = m.end()
            return Token("private", m.group(0)[1:], i, m.end(), nl)
        if ch.isdigit() or (ch == "." and i + 1 < len(src) and src[i + 1].isdigit()):
            m = NUMBER.match(src, i)
            if not m:
                self.error("a number", i)
            j = m.end()
            if src[i] == "0" and j - i > 1 and src[i + 1].isdigit():
                self.error("an old octal number", i)
            if j < len(src) and (ID_START.match(src[j]) or src[j].isdigit() or src[j] == "\\"):
                self.error("a name right after a number", j)
            self.pos = j
            return Token("num", m.group(0), i, j, nl)
        if ch in "'\"":
            return self.read_string(ch, nl)
        if ch == "`":
            return self.read_template(i + 1, i, nl)
        m = PUNCT.match(src, i)
        if m:
            p = m.group(0)
            if p == "?." and i + 2 < len(src) and src[i + 2].isdigit():
                p = "?"
            self.pos = i + len(p)
            return Token("punct", p, i, i + len(p), nl)
        if ch == "\\":
            self.error("a backslash outside a text", i)
        if ch in "  ":
            self.error("a line separator outside a text", i)
        self.error("an unexpected character %r" % ch, i)

    def read_escape(self, i, template=False):
        """The escape sequence at src[i] (after the backslash): (cooked text, next index)."""
        src = self.src
        if i >= len(src):
            self.error("an unterminated escape", i)
        ch = src[i]
        simple = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v"}
        if ch in simple:
            return simple[ch], i + 1
        if ch == "\r":
            return "", i + 2 if src.startswith("\r\n", i) else i + 1
        if ch in "\n  ":
            return "", i + 1
        if ch == "x":
            m = re.compile(r"[0-9a-fA-F]{2}").match(src, i + 1)
            if not m:
                self.error("a bad \\x escape", i)
            return chr(int(m.group(0), 16)), m.end()
        if ch == "u":
            m = re.compile(r"[0-9a-fA-F]{4}|\{([0-9a-fA-F]{1,6})\}").match(src, i + 1)
            if not m:
                self.error("a bad \\u escape", i)
            code = int(m.group(1) or m.group(0), 16)
            if code > 0x10FFFF:
                self.error("a bad \\u escape", i)
            return chr(code), m.end()
        if ch == "0" and not (i + 1 < len(src) and src[i + 1].isdigit()):
            return "\0", i + 1
        if ch.isdigit():
            self.error("an old octal escape", i)
        return ch, i + 1

    def read_string(self, quote, nl):
        src, start = self.src, self.pos
        i, out = start + 1, []
        while True:
            if i >= len(src) or src[i] in LINE_END:
                self.error("an unterminated text", start)
            ch = src[i]
            if ch == quote:
                break
            if ch == "\\":
                text, i = self.read_escape(i + 1)
                out.append(text)
            else:
                out.append(ch)
                i += 1
        self.pos = i + 1
        return Token("string", "".join(out), start, i + 1, nl)

    def read_template(self, i, start, nl):
        """A template part from src[i] to the next `${` or the closing backquote."""
        src, out, raw_start = self.src, [], i
        while True:
            if i >= len(src):
                self.error("an unterminated template", start)
            ch = src[i]
            if ch == "`":
                self.pos = i + 1
                return Token("template", ("".join(out), src[raw_start:i].replace("\r\n", "\n"), True), start,
                             i + 1, nl)
            if ch == "$" and src.startswith("${", i):
                self.pos = i + 2
                return Token("template", ("".join(out), src[raw_start:i].replace("\r\n", "\n"), False), start,
                             i + 2, nl)
            if ch == "\\":
                text, i = self.read_escape(i + 1, True)
                out.append(text)
            elif ch == "\r":
                out.append("\n")
                i += 2 if src.startswith("\r\n", i) else 1
            else:
                out.append(ch)
                i += 1

    def read_regex(self):
        """Re-reads the current `/` or `/=` token as a regular expression."""
        src, start = self.src, self.tok.start
        i, in_class = start + 1, False
        while True:
            if i >= len(src) or src[i] in LINE_END or src[i] in "  ":
                self.error("an unterminated pattern", start)
            ch = src[i]
            if ch == "\\":
                i += 2
                continue
            if ch == "[":
                in_class = True
            elif ch == "]":
                in_class = False
            elif ch == "/" and not in_class:
                break
            i += 1
        body = src[start + 1:i]
        m = re.compile(r"[a-z]*").match(src, i + 1)
        flags = m.group(0)
        if len(set(flags)) != len(flags) or set(flags) - set("dgimsuyv"):
            self.error("bad pattern flags", i)
        end = m.end()
        if end < len(src) and (src[end] == "\\" or ID_START.match(src[end]) or src[end].isdigit()):
            self.error("a bad pattern", end)
        self.pos = end
        self.tok = Token("regex", (body, flags), start, end, self.tok.nl)

    def continue_template(self):
        """After `${ expression`, the current token is `}`: the template goes on from there."""
        if not (self.tok.type == "punct" and self.tok.value == "}"):
            self.error("a template's expression not closed")
        tok = self.read_template(self.tok.start + 1, self.tok.start, self.tok.nl)
        self.prev_end = self.tok.end
        self.tok = tok

    def save(self):
        return (self.pos, self.tok, self.prev_end, set(self.pending_shorthand))

    def restore(self, state):
        self.pos, self.tok, self.prev_end, self.pending_shorthand = state[0], state[1], state[2], set(state[3])

    def peek(self):
        state = self.save()
        self.next()
        tok = self.tok
        self.restore(state)
        return tok

    # --- helpers -------------------------------------------------------------------------------

    def node(self, type_, start, **fields):
        d = {"type": type_, "start": start, "end": self.prev_end}
        d.update(fields)
        return d

    def is_p(self, value):
        return self.tok.type == "punct" and self.tok.value == value

    def is_n(self, value):
        return self.tok.type == "name" and self.tok.value == value

    def eat(self, value):
        if self.is_p(value):
            self.next()
            return True
        return False

    def expect(self, value):
        if not self.is_p(value):
            self.error("expected %r, found %r" % (value, self.tok.value))
        self.next()

    def expect_name(self, value):
        if not self.is_n(value):
            self.error("expected %r, found %r" % (value, self.tok.value))
        self.next()

    def semicolon(self):
        if self.eat(";"):
            return
        if self.is_p("}") or self.tok.type == "eof" or self.tok.nl:
            return
        self.error("expected ';', found %r" % (self.tok.value,))

    def ident(self, allow_reserved=False):
        if self.tok.type != "name":
            self.error("expected a name, found %r" % (self.tok.value,))
        name = self.tok.value
        if not allow_reserved and (name in KEYWORDS or (name == "yield" and self.in_generator)):
            self.error("a reserved word as a name (%s)" % name)
        if name == "await" and self.in_async:
            self.error("await as a name in an async function")
        start = self.tok.start
        self.next()
        return self.node("Identifier", start, name=name)

    # --- statements ----------------------------------------------------------------------------

    def parse_program(self):
        body = self.statement_list(top=True)
        if self.tok.type != "eof":
            self.error("unexpected %r" % (self.tok.value,))
        if self.pending_shorthand:
            self.error("a shorthand with a default outside a pattern")
        return {"type": "Program", "start": 0, "end": len(self.src), "body": body, "sourceType": "script"}

    def statement_list(self, top=False):
        out = []
        while not (self.tok.type == "eof" or (not top and self.is_p("}"))):
            out.append(self.statement(declaration=True))
        return out

    def statement(self, declaration=False):
        t = self.tok
        start = t.start
        if t.type == "punct":
            if t.value == "{":
                return self.block()
            if t.value == ";":
                self.next()
                return self.node("EmptyStatement", start)
        if t.type == "name":
            v = t.value
            if v in ("var", "const") or (v == "let" and self.let_declaration()):
                if v != "var" and not declaration:
                    self.error("a lexical declaration here")
                decl = self.var_declaration(v)
                self.semicolon()
                decl["end"] = self.prev_end
                return decl
            if v == "function":
                if not declaration:
                    self.error("a function declaration here")
                return self.function(start, statement=True)
            if v == "async" and self.peek().type == "name" and self.peek().value == "function" and \
                    not self.peek().nl:
                if not declaration:
                    self.error("a function declaration here")
                self.next()
                return self.function(start, statement=True, is_async=True)
            if v == "class":
                if not declaration:
                    self.error("a class declaration here")
                return self.class_(start, statement=True)
            if v == "if":
                self.next()
                test = self.paren_expression()
                cons = self.statement()
                alt = self.statement() if self.is_n("else") and self.next() else None
                return self.node("IfStatement", start, test=test, consequent=cons, alternate=alt)
            if v == "for":
                return self.for_statement(start)
            if v == "while":
                self.next()
                test = self.paren_expression()
                body = self.loop_body()
                return self.node("WhileStatement", start, test=test, body=body)
            if v == "do":
                self.next()
                body = self.loop_body()
                self.expect_name("while")
                test = self.paren_expression()
                self.eat(";")
                return self.node("DoWhileStatement", start, body=body, test=test)
            if v == "return":
                if not self.in_function:
                    self.error("return outside a function")
                self.next()
                arg = None
                if not (self.is_p(";") or self.is_p("}") or self.tok.type == "eof" or self.tok.nl):
                    arg = self.expression()
                self.semicolon()
                return self.node("ReturnStatement", start, argument=arg)
            if v in ("break", "continue"):
                self.next()
                label = None
                if self.tok.type == "name" and not self.tok.nl and self.tok.value not in KEYWORDS:
                    label = self.ident()
                self.semicolon()
                return self.node("BreakStatement" if v == "break" else "ContinueStatement", start, label=label)
            if v == "throw":
                self.next()
                if self.tok.nl:
                    self.error("a line break after throw")
                arg = self.expression()
                self.semicolon()
                return self.node("ThrowStatement", start, argument=arg)
            if v == "try":
                return self.try_statement(start)
            if v == "switch":
                return self.switch_statement(start)
            if v == "debugger":
                self.next()
                self.semicolon()
                return self.node("DebuggerStatement", start)
            if v == "with":
                self.next()
                obj = self.paren_expression()
                body = self.statement()
                return self.node("WithStatement", start, object=obj, body=body)
            if v in ("import", "export") and not (v == "import" and self.peek().type == "punct" and
                                                  self.peek().value in ("(", ".")):
                self.error("modules are not page scripts")
            if v not in KEYWORDS and self.peek().type == "punct" and self.peek().value == ":":
                label = self.ident()
                self.expect(":")
                self.labels.append(label["name"])
                try:
                    body = self.statement()
                finally:
                    self.labels.pop()
                return self.node("LabeledStatement", start, label=label, body=body)
        expr = self.expression()
        self.semicolon()
        return self.node("ExpressionStatement", start, expression=expr)

    def let_declaration(self):
        nxt = self.peek()
        return (nxt.type == "name" and nxt.value not in ("in", "instanceof", "of")) or \
            (nxt.type == "punct" and nxt.value in ("[", "{"))

    def loop_body(self):
        return self.statement()

    def block(self):
        start = self.tok.start
        self.expect("{")
        body = self.statement_list()
        self.expect("}")
        return self.node("BlockStatement", start, body=body)

    def paren_expression(self):
        self.expect("(")
        e = self.expression()
        self.expect(")")
        return e

    def var_declaration(self, kind, no_in=False):
        start = self.tok.start
        self.next()
        decls = []
        while True:
            dstart = self.tok.start
            target = self.binding_target()
            init = None
            if self.eat("="):
                init = self.assign(no_in=no_in)
            decls.append(self.node("VariableDeclarator", dstart, id=target, init=init))
            if not self.eat(","):
                break
        return self.node("VariableDeclaration", start, declarations=decls, kind=kind)

    def binding_target(self):
        if self.is_p("[") or self.is_p("{"):
            start = self.tok.start
            expr = self.primary()
            return self.to_pattern(expr, binding=True, start=start)
        return self.ident()

    def for_statement(self, start):
        self.next()
        is_await = False
        if self.is_n("await"):
            if not self.in_async:
                self.error("for await outside an async function")
            is_await = True
            self.next()
        self.expect("(")
        init = None
        if self.is_p(";"):
            pass
        elif self.tok.type == "name" and (self.tok.value in ("var", "const") or
                                          (self.tok.value == "let" and self.let_declaration())):
            init = self.var_declaration(self.tok.value, no_in=True)
            if (self.is_n("of") or self.is_n("in")) and len(init["declarations"]) == 1 and \
                    init["declarations"][0]["init"] is None:
                return self.for_in_of(start, init, is_await)
        else:
            istart = self.tok.start
            init = self.expression(no_in=True)
            if self.is_n("of") or self.is_n("in"):
                return self.for_in_of(start, self.to_pattern(init, start=istart), is_await)
        self.expect(";")
        test = None if self.is_p(";") else self.expression()
        self.expect(";")
        update = None if self.is_p(")") else self.expression()
        self.expect(")")
        body = self.loop_body()
        return self.node("ForStatement", start, init=init, test=test, update=update, body=body)

    def for_in_of(self, start, left, is_await):
        of = self.is_n("of")
        self.next()
        right = self.assign() if of else self.expression()
        self.expect(")")
        body = self.loop_body()
        if of:
            return self.node("ForOfStatement", start, left=left, right=right, body=body, **{"await": is_await})
        return self.node("ForInStatement", start, left=left, right=right, body=body)

    def try_statement(self, start):
        self.next()
        block = self.block()
        handler = finalizer = None
        if self.is_n("catch"):
            cstart = self.tok.start
            self.next()
            param = None
            if self.eat("("):
                param = self.binding_target()
                self.expect(")")
            body = self.block()
            handler = self.node("CatchClause", cstart, param=param, body=body)
        if self.is_n("finally"):
            self.next()
            finalizer = self.block()
        if handler is None and finalizer is None:
            self.error("try without catch or finally")
        return self.node("TryStatement", start, block=block, handler=handler, finalizer=finalizer)

    def switch_statement(self, start):
        self.next()
        disc = self.paren_expression()
        self.expect("{")
        cases = []
        while not self.is_p("}"):
            cstart = self.tok.start
            if self.is_n("case"):
                self.next()
                test = self.expression()
            elif self.is_n("default"):
                self.next()
                test = None
            else:
                self.error("expected case or default")
            self.expect(":")
            body = []
            while not (self.is_p("}") or self.is_n("case") or self.is_n("default")):
                body.append(self.statement(declaration=True))
            cases.append(self.node("SwitchCase", cstart, test=test, consequent=body))
        self.expect("}")
        return self.node("SwitchStatement", start, discriminant=disc, cases=cases)

    # --- functions and classes -----------------------------------------------------------------

    def function(self, start, statement=False, is_async=False, method=False):
        if not method:
            self.expect_name("function")
        generator = self.eat("*")
        fid = None
        if statement or (not method and self.tok.type == "name"):
            fid = self.ident()
        params, body = self.function_rest(is_async, generator)
        kind = "FunctionDeclaration" if statement else "FunctionExpression"
        return self.node(kind, start, id=fid, expression=False, generator=generator, params=params, body=body,
                         **{"async": is_async})

    def function_rest(self, is_async, generator):
        saved = (self.in_function, self.in_async, self.in_generator, self.labels)
        self.in_function, self.in_async, self.in_generator, self.labels = True, is_async, generator, []
        try:
            params = self.params()
            body = self.block()
        finally:
            self.in_function, self.in_async, self.in_generator, self.labels = saved
        return params, body

    def params(self):
        self.expect("(")
        out = []
        while not self.is_p(")"):
            pstart = self.tok.start
            if self.eat("..."):
                arg = self.binding_target()
                out.append(self.node("RestElement", pstart, argument=arg))
                if not self.is_p(")"):
                    self.error("a rest parameter not last")
                break
            target = self.binding_target()
            if self.eat("="):
                target = self.node("AssignmentPattern", pstart, left=target, right=self.assign())
            out.append(target)
            if not self.is_p(")"):
                self.expect(",")
        self.expect(")")
        return out

    def property_key(self):
        """(key, computed) of an object literal's or a class's member."""
        t = self.tok
        if self.eat("["):
            key = self.assign()
            self.expect("]")
            return key, True
        if t.type in ("string", "num"):
            self.next()
            return self.literal_of(t), False
        if t.type == "name":
            self.next()
            return self.node("Identifier", t.start, name=t.value), False
        if t.type == "private":
            self.next()
            return self.node("PrivateIdentifier", t.start, name=t.value), False
        self.error("expected a property name, found %r" % (t.value,))

    def class_(self, start, statement=False):
        self.expect_name("class")
        cid = None
        if statement or (self.tok.type == "name" and self.tok.value != "extends"):
            cid = self.ident()
        sup = None
        if self.is_n("extends"):
            self.next()
            sup = self.unary_or_higher()
        bstart = self.tok.start
        self.expect("{")
        members = []
        while not self.is_p("}"):
            if self.eat(";"):
                continue
            members.append(self.class_member())
        self.expect("}")
        body = self.node("ClassBody", bstart, body=members)
        return self.node("ClassDeclaration" if statement else "ClassExpression", start, id=cid, superClass=sup,
                         body=body)

    def class_member(self):
        start = self.tok.start
        static = False
        if self.is_n("static") and not (self.peek().type == "punct" and self.peek().value in ("(", "=", ";", "}")):
            static = True
            self.next()
            if self.is_p("{"):
                saved = (self.in_function, self.labels)
                self.in_function, self.labels = False, []
                try:
                    blk = self.block()
                finally:
                    self.in_function, self.labels = saved
                return self.node("StaticBlock", start, body=blk["body"])
        kind, is_async, generator = "method", False, False
        if self.is_n("async") and not self.peek().nl and not (self.peek().type == "punct" and
                                                               self.peek().value in ("(", "=", ";", "}")):
            is_async = True
            self.next()
        if self.eat("*"):
            generator = True
        if (self.is_n("get") or self.is_n("set")) and not is_async and not generator and \
                not (self.peek().type == "punct" and self.peek().value in ("(", "=", ";", "}")):
            kind = self.tok.value
            self.next()
        key, computed = self.property_key()
        if self.is_p("("):
            fstart = self.tok.start
            params, body = self.function_rest(is_async, generator)
            value = self.node("FunctionExpression", fstart, id=None, expression=False, generator=generator,
                              params=params, body=body, **{"async": is_async})
            if kind == "method" and not static and not computed and key.get("name") == "constructor":
                kind = "constructor"
            return self.node("MethodDefinition", start, static=static, computed=computed, key=key, kind=kind,
                             value=value)
        if kind != "method" or is_async or generator:
            self.error("a class member")
        value = None
        if self.eat("="):
            saved = (self.in_function, self.labels)
            self.in_function, self.labels = False, []
            try:
                value = self.assign()
            finally:
                self.in_function, self.labels = saved
        self.semicolon()
        return self.node("PropertyDefinition", start, static=static, computed=computed, key=key, value=value)

    # --- expressions ---------------------------------------------------------------------------

    def expression(self, no_in=False):
        start = self.tok.start
        e = self.assign(no_in)
        if self.is_p(","):
            items = [e]
            while self.eat(","):
                items.append(self.assign(no_in))
            return self.node("SequenceExpression", start, expressions=items)
        return e

    def arrow_ahead(self):
        """Whether an arrow function starts here: `x =>`, `(...) =>`, `async x =>`, `async (...) =>`."""
        t = self.tok
        if t.type == "name" and t.value not in KEYWORDS:
            nxt = self.peek()
            if nxt.type == "punct" and nxt.value == "=>" and not nxt.nl:
                return True
            if t.value == "async" and not nxt.nl and (nxt.type == "name" or (nxt.type == "punct" and
                                                                             nxt.value == "(")):
                state = self.save()
                try:
                    self.next()
                    return self.paren_then_arrow()
                except JSSyntaxError:
                    return False
                finally:
                    self.restore(state)
            return False
        if self.is_p("("):
            state = self.save()
            try:
                return self.paren_then_arrow()
            except JSSyntaxError:
                return False
            finally:
                self.restore(state)
        return False

    def paren_then_arrow(self):
        if self.tok.type == "name":
            self.next()
        else:
            depth = 0
            while True:
                if self.tok.type == "eof":
                    return False
                if self.tok.type == "punct" and self.tok.value in ("(", "[", "{"):
                    depth += 1
                elif self.tok.type == "punct" and self.tok.value in (")", "]", "}"):
                    depth -= 1
                    if depth == 0:
                        self.next()
                        break
                if self.tok.type == "template" and not self.tok.value[2]:
                    self.skip_template()
                    continue
                self.next_skipping_regex()
        return self.is_p("=>") and not self.tok.nl

    def skip_template(self):
        """While scanning ahead: past a template with expressions (its current token is the head)."""
        depth = 0
        self.next()
        while True:
            if self.tok.type == "eof":
                return
            if self.is_p("{"):
                depth += 1
            elif self.is_p("}"):
                if depth == 0:
                    self.continue_template()
                    if self.tok.value[2]:
                        self.next()
                        return
                    self.next()
                    continue
                depth -= 1
            elif self.tok.type == "template" and not self.tok.value[2]:
                self.skip_template()
                continue
            self.next_skipping_regex()

    def next_skipping_regex(self):
        """While scanning ahead: the next token, a `/` after an operator read as a pattern."""
        prev = self.tok
        self.next()
        if self.tok.type == "punct" and self.tok.value in ("/", "/=") and (
                prev.type == "punct" and prev.value not in (")", "]", "}") or
                prev.type == "name" and prev.value in KEYWORDS - {"this", "super", "null", "true", "false"}):
            self.read_regex()

    def arrow(self, start):
        is_async = False
        if self.is_n("async") and not (self.peek().type == "punct" and self.peek().value == "=>"):
            is_async = True
            self.next()
        saved = (self.in_function, self.in_async, self.in_generator, self.labels)
        self.in_function, self.in_async, self.in_generator, self.labels = True, is_async, False, []
        try:
            if self.tok.type == "name":
                params = [self.ident()]
            else:
                params = self.params()
            if self.tok.nl:
                self.error("a line break before =>")
            self.expect("=>")
            if self.is_p("{"):
                body, expression = self.block(), False
            else:
                body, expression = self.assign(), True
        finally:
            self.in_function, self.in_async, self.in_generator, self.labels = saved
        return self.node("ArrowFunctionExpression", start, id=None, expression=expression, generator=False,
                         params=params, body=body, **{"async": is_async})

    def assign(self, no_in=False):
        start = self.tok.start
        if self.is_n("yield") and self.in_generator:
            self.next()
            delegate = self.eat("*")
            arg = None
            if delegate or not (self.tok.nl or self.tok.type == "eof" or
                                (self.tok.type == "punct" and self.tok.value in (")", "]", "}", ",", ";", ":"))):
                arg = self.assign(no_in)
            return self.node("YieldExpression", start, delegate=delegate, argument=arg)
        if self.arrow_ahead():
            return self.arrow(start)
        left = self.conditional(no_in)
        if self.tok.type == "punct" and self.tok.value in ASSIGN_OPS:
            op = self.tok.value
            if op == "=":
                left = self.to_pattern(left, start=start)
            elif left["type"] not in ("Identifier", "MemberExpression"):
                self.error("a bad assignment target")
            self.next()
            right = self.assign(no_in)
            return self.node("AssignmentExpression", start, operator=op, left=left, right=right)
        return left

    def conditional(self, no_in):
        start = self.tok.start
        test = self.binary(0, no_in)
        if self.eat("?"):
            cons = self.assign()
            self.expect(":")
            alt = self.assign(no_in)
            return self.node("ConditionalExpression", start, test=test, consequent=cons, alternate=alt)
        return test

    def binary_op(self, no_in):
        t = self.tok
        if t.type == "punct" and t.value in BINARY:
            return t.value
        if t.type == "name" and t.value in ("instanceof", "in") and not (no_in and t.value == "in"):
            return t.value
        return None

    def binary(self, min_prec, no_in):
        start = self.tok.start
        left = self.unary_or_higher()
        return self.binary_rest(left, start, min_prec, no_in)

    def binary_rest(self, left, start, min_prec, no_in):
        while True:
            op = self.binary_op(no_in)
            if op is None:
                return left
            prec = BINARY[op]
            if prec <= min_prec:
                return left
            if op == "**" and left["type"] == "UnaryExpression" and not left.get("_paren"):
                self.error("a unary operand of **")
            self.next()
            rstart = self.tok.start
            right = self.unary_or_higher()
            # ** is right-associative: what follows at the same level binds to the right
            right = self.binary_rest(right, rstart, prec - 1 if op == "**" else prec, no_in)
            kind = "LogicalExpression" if op in LOGICAL else "BinaryExpression"
            left = self.node(kind, start, operator=op, left=left, right=right)

    def unary_or_higher(self):
        start = self.tok.start
        t = self.tok
        if t.type == "punct" and t.value in ("!", "~", "+", "-", "++", "--") or \
                t.type == "name" and t.value in ("typeof", "void", "delete"):
            op = t.value
            self.next()
            arg = self.unary_or_higher()
            if op in ("++", "--"):
                if arg["type"] not in ("Identifier", "MemberExpression"):
                    self.error("a bad update target")
                return self.node("UpdateExpression", start, operator=op, prefix=True, argument=arg)
            return self.node("UnaryExpression", start, operator=op, prefix=True, argument=arg)
        if t.type == "name" and t.value == "await" and self.in_async:
            self.next()
            arg = self.unary_or_higher()
            return self.node("AwaitExpression", start, argument=arg)
        expr = self.postfix()
        return expr

    def postfix(self):
        start = self.tok.start
        expr = self.call_member()
        if self.tok.type == "punct" and self.tok.value in ("++", "--") and not self.tok.nl:
            if expr["type"] not in ("Identifier", "MemberExpression"):
                self.error("a bad update target")
            op = self.tok.value
            self.next()
            return self.node("UpdateExpression", start, operator=op, prefix=False, argument=expr)
        return expr

    def arguments(self):
        self.expect("(")
        out = []
        while not self.is_p(")"):
            astart = self.tok.start
            if self.eat("..."):
                out.append(self.node("SpreadElement", astart, argument=self.assign()))
            else:
                out.append(self.assign())
            if not self.is_p(")"):
                self.expect(",")
        self.expect(")")
        return out

    def call_member(self, no_call=False):
        start = self.tok.start
        if self.is_n("new"):
            expr = self.new_expression()
        else:
            expr = self.primary()
        chained = False
        while True:
            if self.is_p("."):
                self.next()
                prop = self.member_name()
                expr = self.node("MemberExpression", start, object=expr, property=prop, computed=False,
                                 optional=False)
            elif self.is_p("?."):
                if no_call:
                    self.error("an optional chain after new")
                chained = True
                self.next()
                if self.is_p("("):
                    expr = self.node("CallExpression", start, callee=expr, arguments=self.arguments(),
                                     optional=True)
                elif self.eat("["):
                    prop = self.expression()
                    self.expect("]")
                    expr = self.node("MemberExpression", start, object=expr, property=prop, computed=True,
                                     optional=True)
                else:
                    prop = self.member_name()
                    expr = self.node("MemberExpression", start, object=expr, property=prop, computed=False,
                                     optional=True)
            elif self.is_p("["):
                self.next()
                prop = self.expression()
                self.expect("]")
                expr = self.node("MemberExpression", start, object=expr, property=prop, computed=True,
                                 optional=False)
            elif self.is_p("(") and not no_call:
                expr = self.node("CallExpression", start, callee=expr, arguments=self.arguments(), optional=False)
            elif self.tok.type == "template":
                if chained:
                    self.error("a tagged template in an optional chain")
                quasi = self.template()
                expr = self.node("TaggedTemplateExpression", start, tag=expr, quasi=quasi)
            else:
                break
        if chained:
            expr = self.node("ChainExpression", start, expression=expr)
        return expr

    def member_name(self):
        t = self.tok
        if t.type == "name":
            self.next()
            return self.node("Identifier", t.start, name=t.value)
        if t.type == "private":
            self.next()
            return self.node("PrivateIdentifier", t.start, name=t.value)
        self.error("expected a property name after '.'")

    def new_expression(self):
        start = self.tok.start
        self.next()
        if self.is_p("."):
            self.next()
            prop = self.ident(allow_reserved=True)
            if prop["name"] != "target" or not self.in_function:
                self.error("new.%s" % prop["name"])
            return self.node("MetaProperty", start, meta=self.node("Identifier", start, name="new"), property=prop)
        if self.is_n("new"):
            callee = self.new_expression()
        else:
            cstart = self.tok.start
            callee = self.primary()
            while True:
                if self.is_p("."):
                    self.next()
                    prop = self.member_name()
                    callee = self.node("MemberExpression", cstart, object=callee, property=prop, computed=False,
                                       optional=False)
                elif self.is_p("["):
                    self.next()
                    prop = self.expression()
                    self.expect("]")
                    callee = self.node("MemberExpression", cstart, object=callee, property=prop, computed=True,
                                       optional=False)
                elif self.tok.type == "template":
                    callee = self.node("TaggedTemplateExpression", cstart, tag=callee, quasi=self.template())
                else:
                    break
        args = self.arguments() if self.is_p("(") else []
        return self.node("NewExpression", start, callee=callee, arguments=args)

    def literal_of(self, t):
        if t.type == "string":
            return self.node("Literal", t.start, value=t.value, raw=self.src[t.start:t.end])
        raw = t.value
        if raw.endswith("n"):
            return self.node("Literal", t.start, value=None, raw=raw, bigint=raw[:-1].replace("_", ""))
        clean = raw.replace("_", "")
        low = clean.lower()
        if low.startswith("0x"):
            value = int(clean, 16)
        elif low.startswith("0o"):
            value = int(clean[2:], 8)
        elif low.startswith("0b"):
            value = int(clean[2:], 2)
        else:
            value = float(clean)
            if value.is_integer() and abs(value) < 2 ** 53:
                value = int(value)
        return self.node("Literal", t.start, value=value, raw=raw)

    def template(self):
        start = self.tok.start
        quasis, exprs = [], []
        while True:
            t = self.tok
            cooked, raw, tail = t.value
            qstart = t.start + 1 if not quasis else t.start + 1
            quasis.append({"type": "TemplateElement", "start": qstart,
                           "end": t.end - (1 if tail else 2), "value": {"raw": raw, "cooked": cooked},
                           "tail": tail})
            if tail:
                self.next()
                break
            self.next()
            exprs.append(self.expression())
            self.continue_template()
        return self.node("TemplateLiteral", start, expressions=exprs, quasis=quasis)

    def primary(self):
        t = self.tok
        start = t.start
        if t.type == "punct" and t.value in ("/", "/="):
            self.read_regex()
            t = self.tok
            self.next()
            body, flags = t.value
            return self.node("Literal", start, value={}, raw=self.src[t.start:t.end],
                             regex={"pattern": body, "flags": flags})
        if t.type in ("num", "string"):
            self.next()
            return self.literal_of(t)
        if t.type == "template":
            return self.template()
        if t.type == "punct":
            if t.value == "(":
                self.next()
                e = self.expression()
                self.expect(")")
                e = dict(e)
                e["_paren"] = True
                return e
            if t.value == "[":
                return self.array_literal()
            if t.value == "{":
                return self.object_literal()
        if t.type == "name":
            v = t.value
            if v == "this":
                self.next()
                return self.node("ThisExpression", start)
            if v in ("null", "true", "false"):
                self.next()
                return self.node("Literal", start, value={"null": None, "true": True, "false": False}[v], raw=v)
            if v == "function":
                return self.function(start)
            if v == "async" and self.peek().type == "name" and self.peek().value == "function" and \
                    not self.peek().nl:
                self.next()
                return self.function(start, is_async=True)
            if v == "class":
                return self.class_(start)
            if v == "super":
                self.next()
                if not (self.is_p(".") or self.is_p("[") or self.is_p("(")):
                    self.error("super")
                return self.node("Super", start)
            if v == "import":
                self.next()
                if self.eat("("):
                    src = self.assign()
                    self.expect(")")
                    return self.node("ImportExpression", start, source=src)
                self.error("import outside a module")
            if v == "new":
                return self.new_expression()
            return self.ident()
        self.error("unexpected %r" % (t.value,))

    def array_literal(self):
        start = self.tok.start
        self.expect("[")
        elements = []
        while not self.is_p("]"):
            if self.is_p(","):
                self.next()
                elements.append(None)
                continue
            estart = self.tok.start
            if self.eat("..."):
                elements.append(self.node("SpreadElement", estart, argument=self.assign()))
            else:
                elements.append(self.assign())
            if not self.is_p("]"):
                self.expect(",")
        self.expect("]")
        return self.node("ArrayExpression", start, elements=elements)

    def object_literal(self):
        start = self.tok.start
        self.expect("{")
        props = []
        while not self.is_p("}"):
            pstart = self.tok.start
            if self.eat("..."):
                props.append(self.node("SpreadElement", pstart, argument=self.assign()))
            else:
                props.append(self.object_member(pstart))
            if not self.is_p("}"):
                self.expect(",")
        self.expect("}")
        return self.node("ObjectExpression", start, properties=props)

    def object_member(self, start):
        is_async = generator = False
        kind = "init"
        nxt = self.peek()
        ends_name = nxt.type == "punct" and nxt.value in (",", ":", "(", "}", "=")
        if self.is_n("async") and not ends_name and not nxt.nl:
            is_async = True
            self.next()
        if self.eat("*"):
            generator = True
        if (self.is_n("get") or self.is_n("set")) and not is_async and not generator and not ends_name:
            kind = self.tok.value
            self.next()
        key_tok = self.tok
        key, computed = self.property_key()
        if self.is_p("("):
            fstart = self.tok.start
            params, body = self.function_rest(is_async, generator)
            value = self.node("FunctionExpression", fstart, id=None, expression=False, generator=generator,
                              params=params, body=body, **{"async": is_async})
            return self.node("Property", start, method=kind == "init", shorthand=False, computed=computed, key=key,
                             value=value, kind=kind)
        if kind != "init" or is_async or generator:
            self.error("an object member")
        if self.eat(":"):
            value = self.assign()
            return self.node("Property", start, method=False, shorthand=False, computed=computed, key=key,
                             value=value, kind="init")
        if key_tok.type != "name" or computed or key_tok.value in KEYWORDS:
            self.error("an object member")
        ident = self.node("Identifier", key_tok.start, name=key_tok.value)
        ident["end"] = key_tok.end
        if self.is_p("="):
            self.next()
            right = self.assign()
            value = self.node("AssignmentPattern", key_tok.start, left=dict(ident), right=right)
            prop = self.node("Property", start, method=False, shorthand=True, computed=False, key=ident,
                             value=value, kind="init")
            self.pending_shorthand.add(id(prop))
            prop["_shorthand_assign"] = True
            return prop
        return self.node("Property", start, method=False, shorthand=True, computed=False, key=ident,
                         value=dict(ident), kind="init")

    # --- patterns ------------------------------------------------------------------------------

    def to_pattern(self, e, binding=False, start=None):
        """An expression read before `=` (or a for-in/of's left side, a parameter) as a pattern."""
        t = e["type"]
        if t == "Identifier":
            if e["name"] in ("eval", "arguments"):
                self.error("an assignment to %s" % e["name"], e["start"])
            return e
        if t == "MemberExpression" and not binding:
            if e.get("optional"):
                self.error("an assignment to an optional chain", e["start"])
            return e
        if e.get("_paren") and t in ("ObjectExpression", "ArrayExpression"):
            self.error("a parenthesized pattern", e["start"])
        if t == "ObjectExpression":
            props = []
            for i, p in enumerate(e["properties"]):
                if p["type"] == "SpreadElement":
                    if i != len(e["properties"]) - 1:
                        self.error("a rest element not last", p["start"])
                    props.append(dict(p, type="RestElement", argument=self.to_pattern(p["argument"], binding)))
                    continue
                if p["kind"] != "init" or p["method"]:
                    self.error("a method in a pattern", p["start"])
                self.pending_shorthand.discard(id(p))
                q = dict(p, value=self.to_pattern(p["value"], binding))
                q.pop("_shorthand_assign", None)
                props.append(q)
            return dict(e, type="ObjectPattern", properties=props)
        if t == "ArrayExpression":
            elems = []
            for i, x in enumerate(e["elements"]):
                if x is None:
                    elems.append(None)
                elif x["type"] == "SpreadElement":
                    if i != len(e["elements"]) - 1:
                        self.error("a rest element not last", x["start"])
                    elems.append(dict(x, type="RestElement", argument=self.to_pattern(x["argument"], binding)))
                else:
                    elems.append(self.to_pattern(x, binding))
            return dict(e, type="ArrayPattern", elements=elems)
        if t == "AssignmentExpression" and e["operator"] == "=" and not e.get("_paren"):
            out = dict(e, type="AssignmentPattern", left=self.to_pattern(e["left"], binding))
            out.pop("operator")
            return out
        if t == "AssignmentPattern":
            return dict(e, left=self.to_pattern(e["left"], binding))
        if t in ("ObjectPattern", "ArrayPattern"):
            return e
        self.error("a bad assignment target", e["start"])


def _clean(node):
    """Drops the parser's own marks."""
    if isinstance(node, dict):
        for k in [k for k in node if k.startswith("_")]:
            del node[k]
        for v in node.values():
            _clean(v)
    elif isinstance(node, list):
        for v in node:
            _clean(v)
    return node


def parse(source):
    """The program as ESTree; JSSyntaxError for anything this parser does not read as the browser would."""
    try:
        return _clean(Parser(source).parse_program())
    except RecursionError:
        raise JSSyntaxError("nested too deeply") from None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    with open(argv[0], encoding="utf-8") as f:
        src = f.read()
    try:
        tree = parse(src)
    except JSSyntaxError as e:
        print("syntax error: %s" % e, file=sys.stderr)
        return 1
    json.dump(tree, sys.stdout, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
