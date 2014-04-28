#!/usr/bin/env python2.7

import os
import uimodules

from tornado.options import options, define, parse_command_line
from tornado.ioloop import IOLoop
from tornado.web import Application, RequestHandler

define('port', default=8443)

class PolicyHandler(RequestHandler):
    def initialize(self, filename):
        self.filename = filename

    def get(self):
        self.render(self.filename, name=None)

class VerifyIdHandler(RequestHandler):
    def get(self):
        self.render('verify_id.html', may_have_app=(self.get_argument('may_have_app', 'True') == 'True'),
                    email_type='registration', title='Activation', screen_name='Activate Account',
                    # email_type='confirmation', title='Confirmation', screen_name='Confirm Account',
                    identity_key='Email:example@example.com',
                    access_token='123456789', code_1='123', code_2='456', code_3='789')

class IndexHandler(RequestHandler):
    def get(self):
        self.write("""
<ul>
<li><a href="/privacy">Privacy</a></li>
<li><a href="/terms">Terms</a></li>
<li><a href="/copyright">Copyright</a></li>
<li><a href="/faq">FAQ</a></li>
<li><a href="/iaq">IAQ</a></li>
<li><a href="/jobs">Jobs</a></li>
<li><a href="/prelaunch">Prelaunch landing page</a></li>
<li><a href="/verify_id">Activation</a></li>
<li><a href="/marketing">Marketing - Homepage</a></li>
<li><a href="/tour">Marketing - Tour</a></li>
<li><a href="/marketing/faq">Marketing - FAQ</a></li>
<li><a href="/marketing/terms">Marketing - Terms</a></li>
<li><a href="/marketing/privacy">Marketing - Privacy</a></li>

""")

def main():
    parse_command_line()

    handlers = [
        ('/tour', PolicyHandler, {'filename': 'marketing/tour.html'}),
        ('/iaq', PolicyHandler, {'filename': 'iaq.html'}),
        ('/jobs', PolicyHandler, {'filename': 'jobs.html'}),
        ('/prelaunch', PolicyHandler, {'filename': 'prelaunch.html'}),
        ('/', PolicyHandler, {'filename': 'marketing/homepage.html'}),
        ('/privacy', PolicyHandler, {'filename': 'marketing/privacy.html'}),
        ('/terms', PolicyHandler, {'filename': 'marketing/terms.html'}),
        ('/copyright', PolicyHandler, {'filename': 'marketing/copyright.html'}),
        ('/faq', PolicyHandler, {'filename': 'marketing/faq.html'}),
        ('/video', PolicyHandler, {'filename': 'marketing/homepage.html'}),
        ('/verify_id', VerifyIdHandler),
        ]

    settings = {
        'debug': True,
        'static_path': os.path.join(os.path.dirname(__file__), 'resources/static'),
        'template_path': os.path.join(os.path.dirname(__file__), 'resources/template'),
        'ui_modules': uimodules,
        }

    print "listening on http://localhost:8443"
    app = Application(handlers, **settings)
    app.listen(options.port)
    IOLoop.instance().start()

if __name__ == '__main__':
    main()
