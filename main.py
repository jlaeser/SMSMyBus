import os
import wsgiref.handlers
import logging
import base64

from datetime import date
from datetime import timedelta
import time

from google.appengine.api import mail
from google.appengine.api import xmpp
from google.appengine.api import quota
from google.appengine.api import urlfetch
from google.appengine.api import memcache
from google.appengine.api.urlfetch import DownloadError
from google.appengine.api.labs import taskqueue
from google.appengine.api.labs.taskqueue import Task

from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

from google.appengine.runtime import apiproxy_errors

import twilio
import twitter
import bus
import rest

from data_model import PhoneLog
from data_model import RouteListing
from data_model import DestinationListing
from data_model import BusStopAggregation
from BeautifulSoup import BeautifulSoup, Tag

ACCOUNT_SID = "AC781064d8f9b6bd4621333d6226768a9f"
ACCOUNT_TOKEN = "5ec48a82949b90511c78c1967a04998d"
SALT_KEY = '2J86APQ0JIE81FA2NVMC48JXQS3F6VNC'
API_VERSION = '2008-08-01'
CALLER_ID = '6084671603'
#CALLER_ID = '4155992671'

class MainHandler(webapp.RequestHandler):

  def post(self):
      
      # this handler should never get called
      logging.error("The MainHandler should never get called... %s" % self.request)
      self.error(204)

  def get(self):
      self.post()
      
## end MainHandler()

class XmppHandler(webapp.RequestHandler):
    
    def post(self):
      message = xmpp.Message(self.request.POST)
      logging.info("XMPP request! Sent form %s with message %s" % (message.sender,message.body))
      if message.body[0:5].lower() == 'hello':
          message.reply("hey there!")

      # there are two valid formats for requests
      # <route> <stop id> : returns the next bus for that stop
      # <stop id> : returns the next N buses for that stop
      #
      body = message.body
      requestArgs = body.split()
      if len(requestArgs) == 1:
          if body.isdigit() == False:
              message.reply("hmm. not sure what this is. try sending just the bus stop (e.g. 1878) or a route and bus stop (e.g. 3 1878)")
              return
          # assume single argument requests are for a bus stop
          sid = message.sender + str(time.time())
          bus.aggregateBuses(body,sid,message.sender)
          message.reply("got it... give me a minute to look that one up for you.")
      else:
          # pull the route and stopID out of the request body and
          # pad it with a zero on the front if the message forgot 
          # to include it (that's how they are stored in the DB)
          routeID = body.split()[0]
          if len(routeID) == 1:
            routeID = "0" + routeID
 
          stopID = body.split()[1]
          if len(stopID) == 3:
            stopID = "0" + stopID
    
          if routeID.isdigit() == False or stopID.isdigit() == False:
              message.reply("hmm. not sure what this is. try sending just the bus stop (e.g. 1878) or a route and bus stop (e.g. 3 1878)")
              return
          textBody = bus.findBusAtStop(routeID,stopID)    
      
          # create an event to log the event
          task = Task(url='/loggingtask', params={'phone':message.sender,
                                                  'inboundBody':body,
                                                  'sid':'xmpp',
                                                  'outboundBody':textBody,})
          task.add('phonelogger')

          # reply to the chat request
          message.reply(textBody)

## end XmppHandler()


class EmailRequestHandler(webapp.RequestHandler):
    def post(self):
      logging.info("Processing inbound email request... %s" % self.request)
      message = mail.InboundEmailMessage(self.request.body)
      logging.info("Email request! Sent from %s with message subject %s" % (message.sender,message.subject))
      
      # there are two valid formats for requests
      # <route> <stop id> : returns the next bus for that stop
      # <stop id> : returns the next N buses for that stop
      #
      body = message.subject
      requestArgs = body.split()
      logging.debug("email body arguments %s" % requestArgs)
      if len(requestArgs) == 1:
          # assume single argument requests are for a bus stop
          sid = message.sender + str(time.time())
          bus.aggregateBuses(body,sid,message.sender)
      else:
          # pull the route and stopID out of the request body and
          # pad it with a zero on the front if the message forgot 
          # to include it (that's how they are stored in the DB)
          routeID = body.split()[0]
          if len(routeID) == 1:
            routeID = "0" + routeID
 
          stopID = body.split()[1]
          if len(stopID) == 3:
            stopID = "0" + stopID
    
          textBody = bus.findBusAtStop(routeID,stopID)    
          sendEmailResponse(message.sender, textBody)
      
          # create an event to log the event
          task = Task(url='/loggingtask', params={'phone':message.sender,
                                                  'inboundBody':message.bodies('text/plain'),
                                                  'sid':'email',
                                                  'outboundBody':textBody,})
          task.add('phonelogger')
        
## end EmailRequestHandler
    
class RequestHandler(webapp.RequestHandler):

  def post(self):
      self.get()
      
  def get(self):

      # logging.info("The request from Twilio %s" % self.request)
      # validate it is in fact coming from twilio
      if ACCOUNT_SID != self.request.get('AccountSid'):
        logging.error("Inbound request was NOT VALID.  It might have been spoofed!")
        self.response.out.write(errorResponse("Illegal caller"))
        return

      smsBody = self.request.get('Body')
      # log every inbound request
      logging.info("New inbound request from %s with message, %s" % (self.request.get('From'),smsBody))
      
      # first look to see if this is an invite request
      if smsBody.lower().find('invite') > -1:
          sendInvite(self.request)
          return
      
      # there are two valid formats for requests
      # <route> <stop id> : returns the next bus for that stop
      # <stop id> : returns the next N buses for that stop
      #
      requestArgs = smsBody.split()
      logging.debug("smsBody arguments %s" % requestArgs)
      if len(requestArgs) == 1:
          # assume single argument requests are for a bus stop
          bus.aggregateBuses(smsBody,self.request.get('SmsSid'),self.request.get('From'))
          return

      # pull the route and stopID out of the request body and
      # pad it with a zero on the front if the message forgot 
      # to include it (that's how they are stored in the DB)
      routeID = smsBody.split()[0]
      if len(routeID) == 1:
        routeID = "0" + routeID
 
      stopID = smsBody.split()[1]
      if len(stopID) == 3:
        stopID = "0" + stopID
    
      textBody = bus.findBusAtStop(routeID,stopID)    
      
      # create an event to log the event
      task = Task(url='/loggingtask', params={'phone':self.request.get('From'),
                                              'inboundBody':self.request.get('Body'),
                                              'sid':self.request.get('SmsSid'),
                                              'outboundBody':textBody,})
      task.add('phonelogger')

      # setup the response SMS
      r = twilio.Response()
      smsBody = "Route %s, Stop %s" % (routeID, stopID) + "\n" + textBody 
      r.append(twilio.Sms(smsBody))
      self.response.out.write(r)

## end RecordingHandler

class PhoneLogEventHandler(webapp.RequestHandler):
    def post(self):
      # log this event...
      log = PhoneLog()
      log.phone = self.request.get('phone')
      log.body = self.request.get('inboundBody')
      log.smsID = self.request.get('sid')
      log.outboundSMS = self.request.get('outboundBody')
      log.put()
    
## end PhoneLogEventHandler


class CleanDBHandler(webapp.RequestHandler):
    
    def get(self):
        logging.error("Someone tried to run the DB cleaner!?! %s" % self.request)
        #query = RouteListing.all()
        for r in query.fetch(5000):
            #r.delete()
            return;
    
## end CleanDBHandler


# this handler is intended to send out SMS messages
# via Twilio's REST interface
class SendSMSHandler(webapp.RequestHandler):
    
    def post(self):
      logging.info("Outbound SMS for ID %s to %s" % 
                   (self.request.get('sid'), self.request.get('phone')))
      account = twilio.Account(ACCOUNT_SID, ACCOUNT_TOKEN)
      sms = {
             'From' : CALLER_ID,
             'To' : self.request.get('phone'),
             'Body' : self.request.get('text'),
             }
      try:
          account.request('/%s/Accounts/%s/SMS/Messages' % (API_VERSION, ACCOUNT_SID),
                          'POST', sms)
      except Exception, e:
          logging.error("Twilio REST error: %s" % e)
                        
## end SendSMSHandler

class DashboardHandler(webapp.RequestHandler):
    
    def get(self, routeID="", stopID=""):
      template_values = {'route':routeID,
                         'stop':stopID,
                        }
      
      # generate the html
      path = os.path.join(os.path.dirname(__file__), 'dashboard.html')
      self.response.out.write(template.render(path, template_values))

## end DashboardHandler

# 
# this handler is intended to be run by a cron job
# to clean up old records in the BusStopAggregation
# table. 
#
class CleanAggregatorHandler(webapp.RequestHandler):
    
    def get(self):
      dateCheck = date.today() - timedelta(days=2)
      dateCheck = dateCheck.isoformat()
      logging.info("Running the cleaner for the aggregation table... %s" % dateCheck)
      q = db.GqlQuery("SELECT * FROM BusStopAggregation WHERE dateAdded < DATE(:1)", dateCheck)
      cleanerQuery = q.fetch(100)
      msg = 'empty message'
      while len(cleanerQuery) > 0:
          msg = "getting ready to delete %s records!" % len(cleanerQuery)
          logging.debug(msg)
          db.delete(cleanerQuery)
          cleanerQuery = q.fetch(100)

      self.response.out.write(msg)
      return
    
## end CleanAggregatorHandlor

#
# This handler is responsible for handling taskqueue requests 
# used to report STOP ID request results.
#
# After all the sub-tasks are completed, this job will run to
# aggregate the results and report on the results. 
#
# "Reporting" depends on how the request came in (sms, twitter, email, etc.)
#    
class AggregationSMSHandler(webapp.RequestHandler):
    def post(self):
      sid = self.request.get('sid')
      phone = self.request.get('caller')
      stopID = '-1'
      textBody = ''
      logging.debug("Time to report back to %s on results for %s..." % (phone,sid))
      
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
          logging.error("We couldn't find this SMS transaction information %s. Chances are there aren't any matches with the request." % sid)
          textBody = "Doesn't look good... Your bus isn't running right now!"
        
      if phone.find('@') > -1 and phone.find('/') > -1:
          # assuming that this is an XMPP request - not SMS
          sendXmppResponse(phone, textBody)
      elif phone.find('@') > -1:
          # assuming that this is an email request - not SMS
          sendEmailResponse(phone, textBody)          
      elif phone.find('prefetch') > -1:
          # assuming that this is a prefetch request - not SMS
          rest.postResults(sid, phone, textBody)
          return # don't log this event
      elif phone.isdigit() is False:
          # assuming that this is a twitter request - not SMS
          twitter.sendTwitterResponse(phone, textBody, stopID, routeID=-1)
      else:
          # it's an SMS request!
          logging.info("Initiating return SMS for ID %s from %s" % (sid,phone))
          account = twilio.Account(ACCOUNT_SID, ACCOUNT_TOKEN)
          sms = {
                 'From' : CALLER_ID,
                 'To' : phone,
                 'Body' : textBody,
                }
          try:
              account.request('/%s/Accounts/%s/SMS/Messages' % (API_VERSION, ACCOUNT_SID),
                              'POST', sms)
          except Exception, e:
              logging.error("Twilio REST error: %s" % e)
                        
      # create an event to log the event
      task = Task(url='/loggingtask', params={'phone':phone,
                                              'inboundBody':stopID,
                                              'sid':sid,
                                              'outboundBody':textBody,})
      task.add('phonelogger')

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
        logging.debug("aggregation fetch for %s stop %s route %s direction %s from caller %s" % 
                      (sid, stopID, routeID, directionID, caller))
        
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
              logging.debug("pulling out a timeslot from page... %s" % slot)
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
                logging.debug("chop up arrival time... %s" % arrival)
                hours = int(arrival.split(':')[0])
                if arrival.find('P.M.') > 0 and int(hours) < 12:
                    hours += 12
                minutes = int(arrival.split(':')[1].split()[0])
                arrivalMinutes = (hours * 60) + minutes
                logging.debug("chop up produced %s hours and %s minutes" % (hours,minutes))
                stop.time = arrivalMinutes
          
                stop.text = textBody + " toward %s" % directionLabel
                stop.put()

        # create the task that glues all the messages together when 
        # we've finished the fetch tasks
        counter = memcache.decr(sid)
        logging.debug("bus route processed... new counter is %s" % counter)
        if counter == 0:
            task = Task(url='/aggregationSMStask', 
                        params={'sid':sid,'caller':caller})
            task.add('aggregationSMS')
            logging.debug("Added new task to send out the aggregation data for ID %s, from caller %s" % (sid,caller))
            memcache.delete(sid)
          
        return;
    
## end AggregationHandler

def sendInvite(request):
    
      textBody = "You've been invited to use SMSMyBus to find real-time arrivals for your buses. Text your bus stop to this number to get started.(invited by " 
      textBody += request.get('From') + ')'
      
      smsBody = request.get('Body')
      requestArgs = smsBody.split()
      for r in requestArgs:
          phone = r.replace('(','').replace('}','').replace('-','')
          if phone.isdigit() == True:
            task = Task(url='/sendsmstask', params={'phone':phone,
                                                    'sid':request.get('SmsSid'),
                                                    'text':textBody,})
            task.add('smssender')
      
      # create an event to log the event
      task = Task(url='/loggingtask', params={'phone':request.get('From'),
                                              'inboundBody':smsBody,
                                              'sid':request.get('SmsSid'),
                                              'outboundBody':textBody,})
      task.add('phonelogger')

      return    
    
## end sendInvite()

def sendEmailResponse(email, textBody):
    
    header = "Thanks for your request! Here are your results...\n\n"             
    footer = "\n\nThank you for using SMSMyBus!\nhttp://www.smsmybus.com"
      
    logging.debug("Sending outbound email to %s with message %s" % (email,textBody))
    
    # setup the response email
    message = mail.EmailMessage()
    message.sender = 'request@smsmybus.com'
    message.bcc = 'greg.tracy@att.net'
    message.to = email
    message.subject = 'Your Metro schedule estimates'
    message.body = header + textBody + footer
    message.send()

## end sendEmailResponse()


def sendXmppResponse(user, textBody):
    
    xmpp.send_message(user,textBody)
    return

## end sendXmppResponse()

            
def main():
  logging.getLogger().setLevel(logging.INFO)
  application = webapp.WSGIApplication([('/', MainHandler),
                                        ('/request', RequestHandler),
                                        ('/dashboard/(.*)/(.*)', DashboardHandler),
                                        ('/_ah/mail/.+', EmailRequestHandler),
                                        ('/_ah/xmpp/message/chat/', XmppHandler),
                                        ('/cleandb', CleanAggregatorHandler),
                                        ('/aggregationtask', AggregationHandler),
                                        ('/aggregationSMStask', AggregationSMSHandler),
                                        ('/loggingtask', PhoneLogEventHandler),
                                        ('/sendsmstask', SendSMSHandler)
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
