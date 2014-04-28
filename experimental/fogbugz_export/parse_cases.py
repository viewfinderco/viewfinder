#!/usr/bin/env python
"""Converts fogbugz xml into a more useful format.

When run from the command line, prints the data.  May also be imported for the parse_cases function.
"""

from tornado import escape
from tornado.ioloop import IOLoop
from tornado.options import define, options, parse_command_line
from xml.etree import ElementTree

# Maps fogbugz users to bitbucket users.
USER_MAP = {
  'CLOSED': '',
  'All Engineers': '',
  'Andrew Kimball': 'andy_kimball',
  'Ben Darnell': 'bdarnell',
  'Brett Eisenman': 'beisenman',
  'Brian McGinnis': 'jbrianmcg',
  'Chris Schoenbohm': 'cschoenbohm',
  'Dan Shin': 'danshin',
  'Harry Clarke': 'hsclarke',
  'Marc Berhault': 'mberhault',
  'Matt Tracy': 'bdarnell',  # assign matt's bugs to ben until he gets back from vacation and sets up his account
  'Mike Purtell': 'mikepurt',
  'Peter Mattis': 'peter_mattis',
  'Spencer Kimball': 'spencerkimball',
}

def parse_cases(filename):
  """Parses the fogbugz data in the file.

  Returns a list of (subject, assigned_to, body) tuples.
  """
  results = []

  tree = ElementTree.parse(filename)

  for case in tree.find('cases').findall('case'):
    subject = 'FB%s: %s' % (case.get('ixBug'), case.findtext('sTitle'))
    body = []
    assigned_to = case.findtext('sPersonAssignedTo')
    body.append('Assigned to: %s' % assigned_to)
    body.append('Project: %s' % case.findtext('sProject'))
    body.append('Area: %s' % case.findtext('sArea'))
    body.append('Priority: %s (%s)' % (case.findtext('ixPriority'), case.findtext('sPriority')))
    body.append('Category: %s' % case.findtext('sCategory'))
    body.append('')
    for event in case.find('events').findall('event'):
      body.append( '%s at %s' % (event.findtext('evtDescription'), event.findtext('dt')))
      if event.findtext('s'):
        body.append('')
        body.append(event.findtext('s'))
        body.append('')
      if event.find('rgAttachments') is not None:
        for attachment in event.find('rgAttachments').findall('attachment'):
          body.append('Attachment: %s' % escape.xhtml_unescape(attachment.findtext('sURL')))
    results.append((subject, USER_MAP[assigned_to], '\n'.join(body)))
  return results

def main():
  define('filename', default='cases.xml')
  parse_command_line()

  for subject, assigned_to, body in parse_cases(options.filename):
    print subject
    print 'assigned to: ', assigned_to
    print
    print body
    print

if __name__ == '__main__':
  IOLoop.instance().run_sync(main)
