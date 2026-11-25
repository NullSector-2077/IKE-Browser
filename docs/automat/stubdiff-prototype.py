"""Prototype: names (Class.member) removed/added between two PyQt .pyi stubs."""
import ast, sys
def names(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    out = {}
    def walk(node, prefix):
        for n in node.body:
            if isinstance(n, ast.ClassDef):
                out[prefix + n.name] = "class"; walk(n, prefix + n.name + ".")
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[prefix + n.name] = "def(%d)" % len(n.args.args)
            elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                out[prefix + n.target.id] = "attr"
            elif isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Name): out[prefix + t.id] = "attr"
    walk(tree, ""); return out
a, b = names(sys.argv[1]), names(sys.argv[2])
rem = sorted(set(a) - set(b)); add = sorted(set(b) - set(a))
print("removed %d, added %d" % (len(rem), len(add)))
print("REMOVED:", rem[:40]); print("ADDED:", add[:60])
