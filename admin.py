import os
import wsgiref.handlers
import logging
from operator import itemgetter
from datetime import date
from datetime import timedelta

from google.appengine.api import mail
from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.api.labs.taskqueue import Task
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.ext.webapp import template

from google.appengine.runtime import apiproxy_errors
from main import PhoneLog

import config

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

          logQuery = q.fetch(500)
          cursor = q.cursor()
          if len(logQuery) > 0:
            total += len(logQuery)
            logging.debug('parsing log entries %s' % total)
            for e in logQuery:
                if e.phone in callers:
                    callers[e.phone] += 1
                else:
                    callers[e.phone] = 1
                    
                # add up all of the unique stop IDs
                requestString = e.body.split()
                if len(requestString) >= 2:
                    stopID = requestString[1]
                elif len(requestString) > 0:
                    stopID = requestString[0]
                    
                if len(requestString) > 0 and stopID.isdigit() and len(stopID) == 4:
                    if stopID in reqs:
                        reqs[stopID] += 1
                    else:
                        reqs[stopID] = 1
          else:
              logging.debug('nothing left!')
              break

      # review the results and generate the data for the template
      caller_stats = []
      sorted_callers = callers.items()
      sorted_callers.sort(key=itemgetter(1),reverse=True)
      for key,value in sorted_callers:
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
                         'events':results,
                         }
        
      # create a page that provides a form for sending an SMS message
      path = os.path.join(os.path.dirname(__file__), 'web/admin.html')
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
            task.add('eventlogger')
            
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

class Histogram(webapp.RequestHandler):
    def get(self):
      histogram = dict()
      output = ''
      
      startDate = date.today() - timedelta(days=7)
      endDate = date.today()
      for i in range(1,51):
          week = 'week'+str(i)
          s = startDate.isoformat()
          e = endDate.isoformat()
          logging.debug('checking between '+s+' and '+e)
          q = db.GqlQuery("SELECT * FROM PhoneLog WHERE date > DATE(:1) and date <= DATE(:2)", s,e)
          #q = db.GqlQuery("SELECT * FROM PhoneLog WHERE date >= DATE(:1)", s)
          result = q.fetch(500)
          weeklyCount = len(result)
          histogram[week] = weeklyCount
          output += '<p>'+str(i)+':'+str(weeklyCount)+'</p>'
          logging.debug('week '+str(i)+' had '+str(weeklyCount)+' requests')
          
          # bump the dates backwards
          #runningTotal = len(result)
          endDate = startDate
          startDate = endDate - timedelta(days=7)
          
      self.response.out.write(output)
## end 

        
#
# Every so often persist the API counters to the datastore
#
class PersistCounterHandler(webapp.RequestHandler):
  def get(self):
    logging.debug('persisting API counters to the datastore')
    devkeys_to_save = []
    devkeys = db.GqlQuery("SELECT * FROM DeveloperKeys").fetch(100)
    for dk in devkeys:
        counter_key = dk.developerKey + ':counter'
        count = memcache.get(counter_key)
        if count is not None:
            dk.requestCounter += count
            memcache.set(counter_key,0)
            devkeys_to_save.append(dk)
    
    if len(devkeys_to_save) > 0:
        db.put(devkeys_to_save)
        
    logging.debug('... done persisting %s counters' % str(len(devkeys_to_save)))
        
## end

#
# Daily reporting email
#
class DailyReportHandler(webapp.RequestHandler):

    def get(self):
      devkeys_to_save = []
      msg_body = '\n'
      
      # right now we're only reporting on the API counters
      devkeys = db.GqlQuery("SELECT * FROM DeveloperKeys").fetch(100)
      for dk in devkeys:
          msg_body += dk.developerName + '(%s) :  ' % dk.developerKey
          msg_body += str(dk.requestCounter)
          msg_body += '\n'
          
          # reset the daily counter
          if dk.requestCounter > 0:
            dk.requestCounter = 0
            devkeys_to_save.append(dk)
      
      # save the modified developer keys
      if len(devkeys_to_save) > 0:
          db.put(devkeys_to_save)
      
      # setup the response email
      message = mail.EmailMessage()
      message.sender = config.EMAIL_SENDER_ADDRESS
      message.to = config.EMAIL_REPORT_ADDRESS
      message.subject = 'SMSMyBus API counters'
      message.body = msg_body
      
      logging.debug('sending daily email report to %s' % message.to)
      message.send()

## end

def main():
  logging.getLogger().setLevel(logging.DEBUG)
  application = webapp.WSGIApplication([('/admin.html', AdminHandler),
                                        ('/admin/sendsms', SendSMSHandler),
                                        ('/admin/histogram', Histogram),
                                        ('/admin/persistcounters', PersistCounterHandler),
                                        ('/admin/dailyreport', DailyReportHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
