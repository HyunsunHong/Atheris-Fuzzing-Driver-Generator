import os
import ast 
import sys 
import astor
from itertools import zip_longest

change_node = []
new_node_list = []
arg = sys.argv[1]

class PytestFixtureVisitor(ast.NodeVisitor):    
    def visit_FunctionDef(self, node):
        new_decorators = []
        has_fixture_decorator = False
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Attribute) and decorator.attr == "fixture":
                has_fixture_decorator = True
                change_node.append({node.name : node.body})
            else:
                new_decorators.append(decorator)
        if has_fixture_decorator:
                new_node = ast.FunctionDef(
                    name="fuzz_" + node.name,
                    args=node.args,
                    body=node.body,
                    decorator_list=new_decorators,
                    returns=node.returns,
                )
                global new_node_list
                new_node_list.append(new_node)

class SetFixtureVisitor(ast.NodeVisitor):    
    def visit_FunctionDef(self, node):
        new_decorators = []
        has_fixture_decorator = -1
        for decorator in node.decorator_list:
            if isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "fixture":
                has_fixture_decorator = 0
            elif isinstance(decorator, ast.Attribute) and decorator.attr == "classmethod":
                has_fixture_decorator = 1
            else:
                new_decorators.append(decorator)
        if has_fixture_decorator is not -1:
            new_node = ast.FunctionDef(
                name=node.name,
                args=node.args,
                body=node.body,
                decorator_list=new_decorators,
                returns=node.returns,
            )
            
            return new_node
        else:
            new_node = ast.FunctionDef(
                name=node.name,
                args=node.args,
                body=node.body,
                decorator_list=new_decorators,
                returns=node.returns,
            )

            return new_node

class CheckFixtureVisitor(ast.NodeVisitor):    
    def visit_FunctionDef(self, node):
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Attribute) and decorator.attr == "fixture":
                return True
            elif isinstance(decorator, ast.Attribute) and decorator.attr == "classmethod":
                return True

        return False

class ParamVisitor(ast.NodeVisitor):
    def __init__(self):
        self.params = []

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'parametrize':
            if isinstance(node.args[0], ast.Str):
                name = node.args[0].s.replace(" ", "").split(",")
                self.params.append(len(name))
                self.params.append(name)
                self.params.append([])
                try:
                    if len(name) == 1:
                        if isinstance(node.args[1].elts[0], ast.Str):
                            self.params[2].append("\'" + ast.literal_eval(node.args[1].elts[0]) + "\'")
                        else:
                            self.params[2].append(astor.to_source(node.args[1].elts[0])[:-1])
                    else:   
                        if isinstance(node.args[1], ast.List) or isinstance(node.args[1], ast.Tuple):
                            if isinstance(node.args[1].elts[0], ast.Tuple) or isinstance(node.args[1].elts[0], ast.List):
                                for e in node.args[1].elts[0].elts:
                                    if isinstance(e, ast.Str):
                                        self.params[2].append("\'" + ast.literal_eval(e) + "\'")
                                    elif isinstance(e, ast.JoinedStr):
                                        self.params[2].append(astor.to_source(e)[:-1].replace("\"\"\"", "'"))
                                    else:
                                        self.params[2].append(astor.to_source(e)[:-1])
                except:
                    print("error occured") 

pytestvisitor = PytestFixtureVisitor()
setupvisitor = SetFixtureVisitor()
checkvisitor = CheckFixtureVisitor()
visitor = ParamVisitor()

def find_fixture_in_project(dir):
    global new_node_list
    files = os.listdir(dir)
    for file in files :
        if os.path.isdir(dir + "/" + file) and not file.startswith(".") and not file.startswith("_"):
            find_fixture_in_project(dir + "/" + file)
        elif file.endswith(".py") and not file.startswith("fuzz") and not file.startswith("seed"):
            new_node_list = []
            with open(dir + "/" + file, 'r') as f:
                parsed = ast.parse(f.read())
                pytestvisitor.visit(parsed)

            if len(new_node_list) > 0:
                with open(dir + "/" + file, 'a') as f:
                    for node in new_node_list:
                        new_content = astor.to_source(node)
                        f.write("\n" + new_content)

def open_dir(dir) :
    files = os.listdir(dir)
    for file in files :
        if os.path.isdir(dir + "/" + file) and not file.startswith(".") and not file.startswith("_"):
            open_dir(dir + "/" + file)
        elif file.endswith(".py") and file.startswith("test_"):
            with open(dir + "/" + file, 'r') as f:
                parsed = ast.parse(f.read())
                initial(parsed, dir)

def parse_parametrize(node):
    visitor = ParamVisitor()
    visitor.visit(node)
    return visitor.params

def call_class(node, origin):
    origin[5] = ["a = " + node.name + "()"]

    # if len(origin[2]) > 0:

    for d in origin[2]:
        for key, value in d.items():
            if value == 0:
                origin[5].append(key)        

    if node.decorator_list:
        for decorator in node.decorator_list:
            origin[4] = parse_parametrize(decorator)

    return [origin[0].copy(), origin[1].copy(), origin[2].copy(), origin[3].copy(), origin[4].copy(), origin[5].copy()]

def check_change(arg, deco_list) :
    if deco_list is not None and len(deco_list) > 1:
        if arg in deco_list[1]:
            return 0

    for d in change_node:
        for key, value in d.items():
            if key == arg:
                for b in value:
                    if isinstance(b, ast.Expr) and isinstance(b.value, ast.Yield):
                        return 1
                    elif isinstance(b, ast.Return):
                        return 2  

    return -1


def call_function(node, origin):
    function_call = ""
    yield_start = []
    yield_end = []
    
    if node.decorator_list:
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == 'parametrize':
                if len(origin[4]) == 0:
                    origin[4] = parse_parametrize(decorator)

                else:
                    list2 = parse_parametrize(decorator)
                    origin[4] = [ origin[4][0] + list2[0], origin[4][1] + list2[1], origin[4][2] + list2[2]]

    for i in range(len(node.args.args)):
        if not node.args.args[i].arg == 'self':
            check = check_change(node.args.args[i].arg, origin[4])
            if check == 0:
                try :
                    flag = True
                    index = origin[4][1].index(node.args.args[i].arg)
                    function_call += origin[4][2][index] + ", "
                except :
                    print("deco index error")
                    function_call += node.args.args[i].arg + ", "
            elif check == 1:
                yield_start += ["gen" + str(i) + " = fuzz_" + node.args.args[i].arg + "()"]
                yield_end += ["try:", "\tgen" + str(i) + ".send(None)", "except:", "\tpass"]
                function_call += "next(gen" + str(i) + "), "
            elif check == 2:
                function_call += "fuzz_" + node.args.args[i].arg + "(), "
            else:
                function_call += node.args.args[i].arg + ", "
    
    if len(function_call) > 2 and function_call[-2] == ",":
        function_call = function_call[:-2]

    if len(origin[5]) < 1 :
        if len(yield_start) > 0:
            origin[5] += yield_start
        origin[5] += ["try:"]
        origin[5].append("\t" + node.name + "(" + function_call + ")")
        origin[5] += ["except:", "\tpass"]
        if len(yield_end) > 0:
            origin[5] += yield_end

    else :
        if len(yield_start) > 0:
            origin[5] += yield_start
        origin[5] += ["try:"]
        origin[5].append("\ta." + node.name + "(" + function_call + ")")
        origin[5] += ["except:", "\tpass"]
        if len(yield_end) > 0:
            origin[5] += yield_end

    print(origin[5])

    return [origin[0].copy(), origin[1].copy(), origin[2].copy(), origin[3].copy(), origin[4].copy(), origin[5].copy()]

class FuncCallModifier(ast.NodeTransformer):
    def visit_Call(self, node):
        new_args = []
        for arg in node.args:
            if isinstance(arg, ast.Str):
                new_arg = ast.Call(
                        func=ast.Name(id='func', ctx=ast.Load()),
                        args=[arg, ast.Call(func=ast.Name(id='fdp.ConsumeUnicode', ctx=ast.Load()), args=[ast.Num(n=len(arg.s))], keywords=[])],
                        keywords=[]
                        )
                new_args.append(new_arg)
            elif isinstance(arg, ast.Num) and isinstance(arg.n, int):
                new_arg = ast.Call(
                        func=ast.Name(id='func', ctx=ast.Load()), args=[arg, 
                            ast.Call(func=ast.Name(id='integer', ctx=ast.Load()), args=[
                                ast.Call(func=ast.Name(id='fdp.ConsumeUnicode', ctx=ast.Load()), args=[ast.Num(n=len(str(arg.n)))], keywords=[])
                                ], keywords=[])
                            ],keywords=[]
                        )
                new_args.append(new_arg)
            elif isinstance(arg, ast.Bytes) and isinstance(arg.s, bytes):
                new_arg = ast.Call(
                        func=ast.Name(id='func', ctx=ast.Load()),
                        args=[arg, ast.Call(func=ast.Name(id='fdp.ConsumeUnicode', ctx=ast.Load()), args=[ast.Num(n=len(arg.s))], keywords=[])],
                        keywords=[]
                        )
                new_args.append(new_arg)
            else:
                new_args.append(arg)
        node.args = new_args
        
        new_keywords = []
        for keyword in node.keywords:
            if isinstance(keyword.value, ast.Str):
                new_value = ast.Call(
                        func=ast.Name(id='func', ctx=ast.Load()),
                        args=[keyword.value, ast.Call(func=ast.Name(id='fdp.ConsumeUnicode', ctx=ast.Load()), args=[ast.Num(n=len(keyword.value.s))], keywords=[])],
                        keywords=[]
                        )
                new_keywords.append(ast.keyword(arg=keyword.arg, value=new_value))
            elif isinstance(keyword.value, ast.Num) and isinstance(keyword.value.n, int):
                new_value = ast.Call(
                        func=ast.Name(id='func', ctx=ast.Load()), args=[keyword.value,
                            ast.Call(func=ast.Name(id='integer', ctx=ast.Load()), args=[
                                ast.Call(func=ast.Name(id='fdp.ConsumeUnicode', ctx=ast.Load()), args=[ast.Num(n=len(str(keyword.value.n)))], keywords=[])
                                ], keywords=[])
                            ],keywords=[]
                        )
                new_keywords.append(ast.keyword(arg=keyword.arg, value=new_value))
            elif isinstance(keyword.value, ast.Bytes) and isinstance(keyword.value.s, bytes):
                new_value = ast.Call(
                        func=ast.Name(id='func', ctx=ast.Load()),
                        args=[keyword.value, ast.Call(func=ast.Name(id='fdp.ConsumeUnicode', ctx=ast.Load()), args=[ast.Num(n=len(keyword.value.s))], keywords=[])],
                        keywords = []
                        )
                new_keywords.append(ast.keyword(arg=keyword.arg, value=new_value))
            else:
                new_keywords.append(keyword)
        node.keywords = new_keywords

        '''
        for arg in ast.iter_child_nodes(node):
            if not(isinstance(arg, ast.Call) and hasattr(arg.func, "id") and arg.func.id is "func"):
                self.generic_visit(arg)
        '''
        return node


def file_write(pathname, filename, content_list):
    seed_dir = pathname + "/seed_" + filename 

    content_list[0] = ["import sys\n", "import os\n", "import logging\nlogging.basicConfig(filename='example.log', level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(message)s')\n\n", 
            "option = ''\nif \"-s\" in sys.argv:\n\toption = 's'\nelif \"-f\" in sys.argv:\n\toption = 'f'\n\n", "\nif option == 's':", "\ttry:", "\t\tos.mkdir(\"" + seed_dir + "\")", "\texcept:", "\t\tpass", "\n\tf = open(\"" + seed_dir + "/seed.txt\", 'w')\n\n"] + content_list[0]

    content_list[1] = ["def func(a, b):\n\tif option == 'f':\n\t\treturn b\n\telif option == 's':\n\t\tf.write('a' + str(a))\n\t\treturn a\n\n"] + ["def integer(str):\n", 
            "\ttry:", "\t\tint(str)", "\texcept:", "\t\treturn 0", "\treturn int(str)\n"] + content_list[1]

    content_list[2] = ["def TestOneInput(data):\n", "\tfdp = atheris.FuzzedDataProvider(data)\n", "\tif(len(data) is 0):", "\t\tprint('None')", "\telse:"] 

    content_list[3] += ["\n\nif option == 'f':\n\tatheris.Setup(sys.argv, TestOneInput)\n\tatheris.Fuzz()\n", "elif option == 's':\n\tfdp = atheris.FuzzedDataProvider(b'string')\n"]
    
    for line in content_list[5]:
        content_list[2] += ['\t\t' + line]
        content_list[3] += ['\t' + line]
                
    content_list[3] += ["\n\tf.close()\n\n"]

    with open(pathname + "/fuzz_" + filename + ".py", 'w') as f:
        for i in range(4):
            for line in content_list[i]:
                try:
                    f.write(line + "\n")
                except:
                    print("error occured2")


def test_parser(pathname, node, i, content_list, classname = ""):
    if len(classname) > 0:
        classname += "-" 
    filename = classname + node.name

    tab = ""
    for k in range(i):
        tab += "\t"

    func_list = []

    deco = "" 

    new_args = []
    for arg in node.args.args:
        new_args.append(arg)
    new_args.append(ast.arg(arg='fdp', annotation=None))
    node.args.args = new_args
    modifier = FuncCallModifier()
    for i, n in enumerate(node.body):
        if isinstance(n, ast.Assert):
            new_arg = ast.If(n.test, "pass", "")
            node.body[i] = new_arg

        modifier.visit(n)
    modified_code = astor.to_source(node)
    modified_code = tab + modified_code.replace('\n', '\n' + tab)
    func_list += modified_code.split('\n')

    content_list[1] += func_list
    content_list = call_function(node, content_list)

    file_write(pathname, filename, content_list)


def is_test(tree):
    # FunctionDef (leaf)
    if isinstance(tree, ast.FunctionDef):
        if tree.name.startswith("test_"):
            return True
    # Class (tree)
    elif isinstance(tree, ast.ClassDef):
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and is_test(node) == True:
                return True

            elif isinstance(node, ast.FunctionDef):
                if node.name.startswith("test_"):
                    return True

    return False
def check_deco(tree):
    if isinstance(tree, ast.FunctionDef):
        for decorator in tree.decorator_list:
            if isinstance(decorator, ast.Attribute) and decorator.attr == "fixture":
                return True
            elif isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "fixture":
                return True

        return False

def is_fixture(tree):
    if isinstance(tree, ast.FunctionDef) :
        if check_deco(tree) and tree.name.lower().startswith("setup"):
            return 0
        elif tree.name.startswith("setup_"):
            return 1
        elif tree.name.startswith("teardown_"):
            return 2
        else:
            return -1

def indentation(body, i):
    src_list = astor.to_source(body).split("\n")
    tap = ""
    for indent in range(i):
        tap += "\t"

    src_list = [tap + s for s in src_list]

    return src_list

def class_parser(pathname, node, i, origin) :
    name = ""
    if node.decorator_list:
        for tap in range(i):
            name += "\t"
        for n in node.decorator_list:
            my_list = astor.to_source(n).split("\n")
            name += "@" + astor.to_source(n).replace("\n", "")
        name += "\n"
        
    for tap in range(i):
        name += "\t"
    name += "class " +  node.name

    if node.bases :
        name += "("
        for n in node.bases[:-1]:
            if hasattr(n, 'id'):
                name += n.id + ", "
        
        for n in node.bases[-1:]:
            if hasattr(n, 'id'):
                name += n.id 
        name += ")"
    
    name += ":"
    
    origin[1].append(name)

    for n in node.body:
        if not is_test(n):
            check = is_fixture(n)
            if check == 0:
                new_node = setupvisitor.visit(n)
                origin[2].append({'a.' + new_node.name + '()': 0})
                src_list = indentation(new_node, i + 1)

                for s in src_list:
                    origin[1].append(s)
                
            elif check == 1:
                new_node = setupvisitor.visit(n)
                origin[2].append({'a.' + new_node.name + '()': 1})
                src_list = indentation(new_node, i + 1)

                for s in src_list:
                    origin[1].append(s)

            elif check == 2:
                new_node = setupvisitor.visit(n)
                origin[3].append({'a.' + new_node.name + '()': 2})
                src_list = indentation(new_node, i + 1)

                for s in src_list:
                    origin[1].append(s)
            
            else:
                src_list = indentation(n, i + 1)

                for s in src_list:
                    origin[1].append(s)    

    for n in node.body:
        if is_test(n):
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_"):
                test_parser(pathname, n, i + 1, call_class(node,[origin[0].copy(), origin[1].copy(), origin[2].copy(), origin[3].copy(), origin[4].copy(), origin[5].copy()]), node.name)
            elif isinstance(n, ast.ClassDef):
                class_parser(pathname, n, i + 1, [origin[0].copy(), origin[1].copy(), origin[2].copy(), origin[3].copy(), origin[4].copy(), origin[5].copy()])

def initial(parsed, pathname):
    i = 0
    imp = None
    import_list = ["import atheris","import sys"]
    source_list = []
    setup_list = []
    teardown_list = []

    path = os.getcwd()
    directory = path + "/" + sys.argv[1]
    import_list.append("sys.path.remove(r'/usr/lib/python3/dist-packages')")
    import_list.append("sys.path.append(\"" + directory + "\")")
    for d in os.listdir(directory):
        if os.path.isdir(directory + "/" + d):
            if d.startswith("."):
                continue
            import_list.append("sys.path.append(\"" + directory + "/" + d + "\")")
    import_list.append("sys.path.append(r'/usr/lib/python3/dist-packages')")
    import_list.append("with atheris.instrument_imports():")

    for node in parsed.body :
        if not is_test(node) :
            source = astor.to_source(node)
            if "import" in source:
                raw_src = astor.to_source(node)[:-1]
                raw_src = raw_src.split(" ")
                if raw_src[1].startswith('.') and not all(char == "." for char in raw_src[1]):
                    raw_src[1] = raw_src[1].lstrip(".")
                raw_source = ""
                for value in raw_src:
                    raw_source += value + " "
                source = raw_source + "\n"
                
                flag = True
                for d in change_node:
                    keys = list(d.keys())
                    if keys[0] in source:
                        flag = False
                        import_list.append('\t' + source.replace(keys[0], "fuzz_" + keys[0]).replace('\n', '\n\t'))

                if flag:
                    import_list.append('\t' + source.replace('\n', '\n\t'))
            else:
                check = is_fixture(node)
                if check == 0:
                    setup_list.append({node.name + "()" : 0})
                elif check == 1:
                    setup_list.append({node.name + "()" : 1})
                elif check == 2:
                    teardown_list.append({node.name + "()" : 2})
    
                source_list.append(source)

    for node in parsed.body:
        if is_test(node):
            if isinstance(node, ast.FunctionDef):
                test_parser(pathname, node, i, [import_list.copy(), source_list.copy(), setup_list.copy(), teardown_list.copy(), [], []])
            elif isinstance(node, ast.ClassDef):
                class_parser(pathname, node, i, [import_list.copy(), source_list.copy(), setup_list.copy(), teardown_list.copy(), [], []])

find_fixture_in_project(sys.argv[1])
open_dir(sys.argv[1])


