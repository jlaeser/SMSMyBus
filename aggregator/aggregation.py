import os
import wsgiref.handlers
import logging
from datetime import date, time
from datetime import timedelta

from google.appengine.api import mail
from google.appengine.api import urlfetch
from google.appengine.api import memcache
from google.appengine.api import xmpp
from google.appengine.api.labs.taskqueue import Task
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.ext.webapp.util import run_wsgi_app

from BeautifulSoup import BeautifulSoup, Tag

from data_model import BusStopAggregation

import twilio
import bus
import twitter
import email
import config

from data_model import BusStopAggregation

# 
# this handler is intended to be run by a cron job
# to clean up old records in the BusStopAggregation
# table. 
#
class CleanAggregatorHandler(webapp.RequestHandler):
    
    def get(self):
      dateCheck = date.today() - timedelta(days=2)
      dateCheck = dateCheck.isoformat()
      #logging.info("Running the cleaner for the aggregation table... %s" % dateCheck)
      q = db.GqlQuery("SELECT * FROM BusStopAggregation WHERE dateAdded < DATE(:1)", dateCheck)
      cleanerQuery = q.fetch(100)
      msg = 'empty message'
      while len(cleanerQuery) > 0:
          #logging.debug("getting ready to delete %s records!" % len(cleanerQuery))
          db.delete(cleanerQuery)
          cleanerQuery = q.fetch(100)

      self.response.out.write(msg)
      return
    
## end CleanAggregatorHandler

#
# This handler is responsible for handling taskqueue requests 
# used to report STOP ID request results.
#
# After all the sub-tasks are completed, this job will run to
# aggregate the results and report on the results. 
#
# "Reporting" depends on how the request came in (sms, twitter, email, etc.)
#    
class AggregationResultHandler(webapp.RequestHandler):
    def post(self):
      sid = self.request.get('sid')
      phone = self.request.get('caller')
      stopID = '-1'
      textBody = ''
      #logging.debug("Time to report back to %s on results for %s..." % (phone,sid))
      
      # if this request is via email or is the prefetcher, grab multiple results
      num_records = 4
      if phone.find('@') > -1 or phone.find('prefetch') > -1:
          num_records = 10
          
      q = db.GqlQuery("SELECT * FROM BusStopAggregation WHERE sid = :1 ORDER BY time", sid)
      routeQuery = q.fetch(num_records)
      if len(routeQuery) > 0:
          stopID = routeQuery[0].stopID
          textBody = "Stop %s\n" % routeQuery[0].stopID
          for r in routeQuery:
              textBody += "Route %s " % r.routeID + " %s" % r.text + "\n"
      else:
          logging.debug("We couldn't find this transaction information %s. Chances are there aren't any matches with the request." % sid)
          textBody = "Doesn't look good... Your bus isn't running right now!"
        
      if phone.find('@') > -1 and phone.find('/') > -1:
          # assuming that this is an XMPP request - not SMS
          #sendXmppResponse(phone, textBody)
          # native call through the xmpp library
          xmpp.send_message(phone,textBody)
      elif phone.find('@') > -1:
          # assuming that this is an email request - not SMS
          sendEmailResponse(phone, textBody)          
      elif phone.isdigit() is False:
          # it's an SMS request!
          logging.info("Initiating return SMS for ID %s from %s" % (sid,phone))
          account = twilio.Account(config.ACCOUNT_SID, config.ACCOUNT_TOKEN)
          sms = {
                 'From' : config.CALLER_ID,
                 'To' : phone,
                 'Body' : textBody,
                }
          try:
              account.request('/%s/Accounts/%s/SMS/Messages' % (config.API_VERSION, config.ACCOUNT_SID),
                              'POST', sms)
          except Exception, e:
              logging.error("Twilio REST error: %s" % e)
      else:
          # assuming that this is a twitter request - not SMS
          twitter.sendTwitterResponse(phone, textBody, stopID, routeID=-1)
                        
      # create an event to log the event
      task = Task(url='/loggingtask', params={'phone':phone,
                                              'inboundBody':stopID,
                                              'sid':sid,
                                              'outboundBody':textBody,})
      task.add('eventlogger')

      return
  
## end AggregationSMSHandler
    
class AggregationHandler(webapp.RequestHandler):
    def post(self):
        sid = self.request.get('sid')
        stopID = self.request.get('stop')
        routeID = self.request.get('route')
        directionID = self.request.get('direction')
        scheduleURL = self.request.get('url')
        caller = self.request.get('caller')
        #logging.debug("aggregation fetch for %s stop %s route %s direction %s from caller %s" % 
        #              (sid, stopID, routeID, directionID, caller))
        
        directionLabel = bus.getDirectionLabel(directionID)
        loop = 0
        done = False
        result = None
        while not done and loop < 3:
           try:
             # go fetch the webpage for this route/stop!
             result = urlfetch.fetch(scheduleURL)
             done = True;
           except urlfetch.DownloadError:
             logging.error("Error loading page (%s)... sleeping" % loop)
             if result:
                logging.error("Error status: %s" % result.status_code)
                logging.error("Error header: %s" % result.headers)
                logging.error("Error content: %s" % result.content)
             time.sleep(3)
             loop = loop+1
           
        arrival = '0'
        textBody = 'unknown'
        valid = False
        if result is None or result.status_code != 200:
           logging.error("Exiting early: error fetching URL: " + result.status_code)
           textBody = routeID + " (unknown)"
        else:
           soup = BeautifulSoup(result.content)
           for slot in soup.html.body.findAll("a","ada"):
              #logging.debug("pulling out a timeslot from page... %s" % slot)
              # only take the first time entry
              if slot['title'].split(':')[0].isdigit():
                arrival = slot['title']
                textBody = arrival.replace('P.M.','pm').replace('A.M.','am')
                valid = True
                # add these results to datastore until we're ready to put
                # them all together
                stop = BusStopAggregation()
                stop.stopID = stopID
                stop.routeID = routeID
                stop.sid = sid
          
                # turn the arrival time into absolute minutes
                #logging.debug("chop up arrival time... %s" % arrival)
                hours = int(arrival.split(':')[0])
                if arrival.find('P.M.') > 0 and int(hours) < 12:
                    hours += 12
                minutes = int(arrival.split(':')[1].split()[0])
                arrivalMinutes = (hours * 60) + minutes
                #logging.debug("chop up produced %s hours and %s minutes" % (hours,minutes))
                stop.time = arrivalMinutes
          
                stop.text = textBody + " toward %s" % directionLabel
                stop.put()

        # create the task that glues all the messages together when 
        # we've finished the fetch tasks
        counter = memcache.decr(sid)
        #logging.debug("bus route processed... new counter is %s" % counter)
        if counter == 0:
            task = Task(url='/aggr/aggregationResultTask', 
                        params={'sid':sid,'caller':caller})
            task.add('aggregationSMS')
            #logging.debug("Added new task to send out the aggregation data for ID %s, from caller %s" % (sid,caller))
            memcache.delete(sid)
          
        return;
    
## end AggregationHandler


def sendEmailResponse(email, textBody):
    
    header = "Thanks for your request! Here are your results...\n\n"             
    footer = "\n\nThank you for using SMSMyBus!\nhttp://www.smsmybus.com"
      
    logging.debug("Sending outbound email to %s with message %s" % (email,textBody))
    
    # setup the response email
    message = mail.EmailMessage()
    message.sender = 'request@smsmybus.com'
    message.bcc = 'gtracy@gmail.com'
    message.to = email
    message.subject = 'Your Metro schedule estimates'
    message.body = header + textBody + footer
    message.send()

## end sendEmailResponse()

def main():
  logging.getLogger().setLevel(logging.DEBUG)
  application = webapp.WSGIApplication([('/aggr/cleandb', CleanAggregatorHandler),
                                        ('/aggr/aggregationtask', AggregationHandler),
                                        ('/aggr/aggregationResultTask', AggregationResultHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
