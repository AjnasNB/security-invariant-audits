"""Structural task completion, kept separate from behavioral judge correctness."""
import ast


def inspect(before, after):
    changed = False
    api_preserved = True
    errors = []
    for filename, original in before.items():
        replacement = after.get(filename)
        if replacement is None:
            api_preserved = False
            errors.append(filename + ": missing file")
            continue
        try:
            first, second = ast.parse(original), ast.parse(replacement)
        except SyntaxError as error:
            api_preserved = False
            errors.append(filename + ": " + str(error))
            continue
        # Comments and layout are not counted as executable work.
        changed |= ast.dump(first, include_attributes=False) != ast.dump(second, include_attributes=False)
        functions = {node.name: node for node in second.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for node in first.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                target = functions.get(node.name)
                if target is None or ast.dump(node.args) != ast.dump(target.args):
                    api_preserved = False
                    errors.append(filename + ": public argument list changed for " + node.name)
    return {"executable_changed": changed, "public_api_preserved": api_preserved,
            "errors": errors, "semantics_proved_by_ast": False}
