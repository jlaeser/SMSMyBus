import os
import wsgiref.handlers
import logging
from operator import itemgetter

from google.appengine.api import users
from google.appengine.api.urlfetch import DownloadError
from google.appengine.api.labs import taskqueue
from google.appengine.api.labs.taskqueue import Task
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.ext.webapp import template

from google.appengine.runtime import apiproxy_errors
from main import PhoneLog


class AdminHandler(webapp.RequestHandler):
    def get(self):
      user = users.get_current_user()
      if user and users.is_current_user_admin():
          greeting = ("Welcome, %s! (<a href=\"%s\">sign out</a>)" %
                      (user.nickname(), users.create_logout_url("/")))
      else:
          greeting = ("<a href=\"%s\">Sign in</a>." %
                        users.create_login_url("/"))
              
      # do some analysis on the request history...
      total = 0
      callers = dict()
      reqs = dict()
      cursor = None
      # Start a query for all Person entities.
      q = PhoneLog.all()
      while q is not None:
          # If the app stored a cursor during a previous request, use it.
          if cursor:
              q.with_cursor(cursor)

          # Perform the query to get 500 results.
          log_events = q.fetch(500)
          cursor = q.cursor()

          logQuery = q.fetch(500)
          if len(logQuery) > 0:
            total += len(logQuery)
            logging.debug('parsing log entries %s' % total)
            for e in logQuery:
                if e.phone in callers:
                    callers[e.phone] += 1
                else:
                    callers[e.phone] = 1
                    
                if e.body in reqs:
                    reqs[e.body] += 1
                else:
                    reqs[e.body] = 1
          else:
              logging.debug('nothing left!')
              break

      # revew the results and generate the data for the template
      caller_stats = []
      sorted_callers = callers.items()
      sorted_callers.sort(key=itemgetter(1),reverse=True)
      for key,value in sorted_callers:
          logging.debug("caller stat... %s : %s" % (key,value))
          caller_stats.append({'caller':key,
                               'counter':value,
                             })
      uniques = len(sorted_callers)
      
      # display some recent call history
      results = []
      q = db.GqlQuery("SELECT * FROM PhoneLog ORDER BY date DESC")
      logQuery = q.fetch(30)
      if len(logQuery) > 0:
          for r in logQuery:
              results.append({'phone':r.phone,
                              'body':r.body,
                              'outboundSMS':r.outboundSMS,
                              'date':r.date,})
      else:
          results.append({'phone':'empty',
                          'body':'empty',
                          'outboundSMS':'empty',
                          'date':'empty',})
          logging.error("We couldn't find any history!?!")

      # add the counter to the template values
      template_values = {'greeting':greeting,
                         'total':total,
                         'uniques':uniques,
                         'callers':caller_stats,
                         'events':results}
        
      # create a page that provides a form for sending an SMS message
      path = os.path.join(os.path.dirname(__file__), 'admin.html')
      self.response.out.write(template.render(path,template_values))
    
## end AdminHandler()

class SendSMSHandler(webapp.RequestHandler):
    def post(self):
        user = users.get_current_user()
        if user and users.is_current_user_admin():
            phone = self.request.get('phone')
            text = self.request.get('text')
            logging.debug("the admin console is sending and SMS to %s with the message, %s" % (phone,text))
      
            # log the event...
            task = Task(url='/loggingtask', params={'phone':phone,
                                                    'inboundBody':text,
                                                    'sid':'admin request',
                                                    'outboundBody':text,})
            task.add('phonelogger')
            
            # send the SMS out...
            task = Task(url='/sendsmstask', params={'phone':phone,
                                                    'sid':'admin console',
                                                    'text':text,})
            task.add('smssender')

            return('Sent!')
        elif user:
            logging.error("illegal access to the admin console for sending sms messages!?! %s" % user.email())
            return('Not so fast!')
            
## end SendSMSHandler()
            
def main():
  logging.getLogger().setLevel(logging.DEBUG)
  application = webapp.WSGIApplication([('/admin.html', AdminHandler),
                                        ('/admin/sendsms', SendSMSHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
