#!/usr/bin/env python
"""Detect Python closures defined in loops.

Closures defined in loops are error prone, since if they reference variables from the loop scope
those variables are bound by name instead of being captured at the time of the function definition.

For example:

  funcs = []
  for i in range(5):
    funcs.append(lambda: print(i))
  for func in funcs:
    func()

will print "5 5 5 5 5" instead of "1 2 3 4 5".  functools.partial is useful to force early binding:
"funcs.append(functools.partial(print, i))" would work as expected.

Closures identified by this tool may be safe, provided one of the following is true:
* The closure does not reference any variables from the outer scope that change in the course of the loop.
* The closure is used and discarded within a single loop iteration.
"""

import ast
import sys

class Visitor(ast.NodeVisitor):
  def __init__(self, filename):
    self.filename = filename
    self.in_loop = False

  def _visit_loop(self, node):
    old_in_loop = self.in_loop
    self.in_loop = True
    self.generic_visit(node)
    self.in_loop = old_in_loop

  visit_For = visit_While = _visit_loop

  def _visit_closure(self, node):
    if self.in_loop:
      print >>sys.stderr, "%s:%d: closure defined in loop" % (self.filename, node.lineno)
    self.generic_visit(node)

  visit_FunctionDef = visit_ClassDef = visit_Lambda = _visit_closure

def check(filename):
  with open(filename) as f:
    contents = f.read()
  try:
    tree = ast.parse(contents, filename)
  except Exception:
    print >>sys.stderr, "%s: parse error" % filename
    return

  visitor = Visitor(filename)
  visitor.visit(tree)

def main():
  for arg in sys.argv[1:]:
    check(arg)

if __name__ == '__main__':
  main()
