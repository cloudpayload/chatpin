"""Conservative AST review signals, never a claim of maliciousness."""
from jinja2 import Environment, TemplateSyntaxError, nodes
from jinja2.ext import Extension
from .sources import ChatpinError


class Generation(Extension):
    tags = {"generation"}

    def parse(self, parser):
        token = next(parser.stream)
        body = parser.parse_statements(["name:endgeneration"], drop_needle=True)
        return nodes.Scope(body).set_lineno(token.lineno)


def analyze(text):
    try:
        tree = Environment(extensions=[Generation, "jinja2.ext.loopcontrols", "jinja2.ext.do"]).parse(text)
    except (TemplateSyntaxError, RecursionError) as error:
        raise ChatpinError(f"Cannot analyze template: {error}") from error
    findings = []
    aliases = set()

    def descendants(node):
        return [node, *node.find_all(nodes.Node)]

    def content(node):
        return any((isinstance(n, nodes.Getitem) and isinstance(n.arg, nodes.Const) and n.arg.value == "content")
                   or (isinstance(n, nodes.Getattr) and n.attr == "content")
                   or (isinstance(n, nodes.Name) and n.name in aliases)
                   for n in descendants(node))

    # Monotonic, conservative alias propagation; scope merges can over-report.
    assignments = list(tree.find_all(nodes.Assign))
    for _ in range(len(assignments) + 1):
        before = set(aliases)
        for node in assignments:
            if isinstance(node.target, nodes.Name) and content(node.node):
                aliases.add(node.target.name)
        if aliases == before:
            break

    def add(code, level, node, message):
        findings.append({"code": code, "severity": level, "line": node.lineno, "message": message})

    for node in tree.find_all((nodes.If, nodes.CondExpr, nodes.For)):
        test = node.test
        if test is not None and content(test):
            add("CP001", "review", node,
                "Control flow depends on message content. Review trigger and emitted instructions; legitimate formatting may do this.")
    for node in tree.find_all((nodes.Getattr, nodes.Getitem)):
        attr = node.attr if isinstance(node, nodes.Getattr) else (node.arg.value if isinstance(node.arg, nodes.Const) else None)
        if isinstance(attr, str) and attr.startswith("__"):
            add("CP002", "high", node, "Private/dunder attribute access requires review.")
    for node in tree.find_all((nodes.Import, nodes.FromImport, nodes.Include, nodes.Extends)):
        add("CP003", "high", node, "External template dependency is not covered by a single-template pin.")
    for node in tree.find_all(nodes.Filter):
        if node.name == "attr":
            add("CP004", "high", node, "Dynamic attribute access can obscure template behavior.")
    seen, unique = set(), []
    for finding in sorted(findings, key=lambda f: (f["line"], f["code"])):
        key = (finding["code"], finding["line"])
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return unique
