import os
import wsgiref.handlers
import logging
from operator import itemgetter
from datetime import date
from datetime import timedelta

from google.appengine.api import users
from google.appengine.api.urlfetch import DownloadError
from google.appengine.api.labs import taskqueue
from google.appengine.api.labs.taskqueue import Task
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.ext.webapp import template

from google.appengine.runtime import apiproxy_errors
from main import PhoneLog


class MainHandler(webapp.RequestHandler):
    def get(self, stopID=""):
      logging.debug('gadget definition request for stop %s' % stopID)
      template_values = {'stopID':stopID,
                         }
      path = os.path.join(os.path.dirname(__file__), 'metro_template.xml')
      self.response.out.write(template.render(path,template_values))
    
## end MainHandler()

def main():
  logging.getLogger().setLevel(logging.DEBUG)
  application = webapp.WSGIApplication([('/gadgets/metro/(.*).xml', MainHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
