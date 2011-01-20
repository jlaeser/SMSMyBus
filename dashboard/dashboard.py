import os
import wsgiref.handlers
import logging
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

#
# This handler is designed to display an activity dashboard for 
# a route/stop combination. Should be expanded to do all routes
# at a stop.
#
# Currently, all logic is actually in the html page's javascript
#
class DashboardHandler(webapp.RequestHandler):
    
    def get(self, routeID="", stopID=""):
      template_values = {'route':routeID,
                         'stop':stopID,
                        }
      
      # generate the html
      path = os.path.join(os.path.dirname(__file__), 'dashboard.html')
      self.response.out.write(template.render(path, template_values))

## end DashboardHandler

        
def main():
  logging.getLogger().setLevel(logging.DEBUG)
  application = webapp.WSGIApplication([('/dashboard/(.*)/(.*)', DashboardHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
