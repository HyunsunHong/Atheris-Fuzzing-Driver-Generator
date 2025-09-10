import os
import sys
import ast
import astor

change_node = []
new_node_list = []
arg = sys.argv[1]


# -----------------------------
# Visitors for AST Processing
# -----------------------------

class PytestFixtureVisitor(ast.NodeVisitor):
    """Find pytest fixtures and generate fuzz_ versions of them."""

    def visit_FunctionDef(self, node):
        new_decorators = []
        has_fixture_decorator = False

        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Attribute) and decorator.attr == "fixture":
                has_fixture_decorator = True
                change_node.append({node.name: node.body})
            else:
                new_decorators.append(decorator)

        if has_fixture_decorator:
            new_node = ast.FunctionDef(
                name="fuzz_" + node.name,
                args=node.args,
                body=node.body,
                decorator_list=new_decorators,
                returns=node.returns,
                type_comment=None,
            )
            new_node_list.append(new_node)


class SetFixtureVisitor(ast.NodeVisitor):
    """Clean up fixture and classmethod decorators in functions."""

    def visit_FunctionDef(self, node):
        new_decorators = []
        has_fixture_decorator = None

        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "fixture":
                has_fixture_decorator = 0
            elif isinstance(decorator, ast.Attribute) and decorator.attr == "classmethod":
                has_fixture_decorator = 1
            else:
                new_decorators.append(decorator)

        return ast.FunctionDef(
            name=node.name,
            args=node.args,
            body=node.body,
            decorator_list=new_decorators,
            returns=node.returns,
            type_comment=None,
        )


class CheckFixtureVisitor(ast.NodeVisitor):
    """Check whether a function has fixture/classmethod decorators."""

    def visit_FunctionDef(self, node):
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Attribute) and decorator.attr in {"fixture", "classmethod"}:
                return True
        return False


class ParamVisitor(ast.NodeVisitor):
    """Extract parameters from pytest.mark.parametrize decorators."""

    def __init__(self):
        self.params = []

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "parametrize":
            if isinstance(node.args[0], ast.Str):
                names = node.args[0].s.replace(" ", "").split(",")
                self.params = [len(names), names, []]

                try:
                    if len(names) == 1 and isinstance(node.args[1].elts[0], ast.Str):
                        self.params[2].append("'" + ast.literal_eval(node.args[1].elts[0]) + "'")
                    else:
                        if isinstance(node.args[1], (ast.List, ast.Tuple)):
                            first_elt = node.args[1].elts[0]
                            if isinstance(first_elt, (ast.Tuple, ast.List)):
                                for e in first_elt.elts:
                                    if isinstance(e, ast.Str):
                                        self.params[2].append("'" + ast.literal_eval(e) + "'")
                                    else:
                                        self.params[2].append(astor.to_source(e).strip())
                except Exception as e:
                    print("Error parsing parametrize:", e)


# Initialize visitors
pytestvisitor = PytestFixtureVisitor()
setupvisitor = SetFixtureVisitor()
checkvisitor = CheckFixtureVisitor()


# -----------------------------
# Core Functions
# -----------------------------

def find_fixture_in_project(dir_path):
    """Find and rewrite pytest fixtures to fuzz_ fixtures."""
    global new_node_list
    files = os.listdir(dir_path)

    for file in files:
        file_path = os.path.join(dir_path, file)

        if os.path.isdir(file_path) and not file.startswith((".", "_")):
            find_fixture_in_project(file_path)
        elif file.endswith(".py") and not file.startswith(("fuzz", "seed")):
            new_node_list = []
            with open(file_path, "r") as f:
                parsed = ast.parse(f.read())
                pytestvisitor.visit(parsed)

            if new_node_list:
                with open(file_path, "a") as f:
                    for node in new_node_list:
                        new_content = astor.to_source(node)
                        f.write("\n" + new_content)


def open_dir(dir_path):
    """Open test files and run initial AST parsing."""
    files = os.listdir(dir_path)
    for file in files:
        file_path = os.path.join(dir_path, file)

        if os.path.isdir(file_path) and not file.startswith((".", "_")):
            open_dir(file_path)
        elif file.endswith(".py") and file.startswith("test_"):
            with open(file_path, "r") as f:
                parsed = ast.parse(f.read())
                initial(parsed, dir_path)


# -----------------------------
# Entry Point
# -----------------------------

def main():
    find_fixture_in_project(arg)
    open_dir(arg)


if __name__ == "__main__":
    main()
