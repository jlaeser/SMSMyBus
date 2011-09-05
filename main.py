import os
import wsgiref.handlers
import logging
import base64
import time

from datetime import date
from datetime import timedelta

from google.appengine.api import mail
from google.appengine.api import xmpp
from google.appengine.api import quota
from google.appengine.api import memcache
from google.appengine.api.taskqueue import Task

from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

from google.appengine.runtime import apiproxy_errors

import twilio
import bus
import config

from data_model import PhoneLog
from data_model import RouteListing

from BeautifulSoup import BeautifulSoup, Tag

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
          logging.info('starting new asynchronous call')
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
          task.add('eventlogger')

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
          task.add('eventlogger')
        
## end EmailRequestHandler
  
  
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

class SMSRequestHandler(webapp.RequestHandler):

  def post(self):
      self.get()
      
  def get(self):

      # logging.info("The request from Twilio %s" % self.request)
      # validate it is in fact coming from twilio
      if config.ACCOUNT_SID != self.request.get('AccountSid'):
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
      
      # filter the troublemakers
      caller = self.request.get('From')
      if caller in config.ABUSERS:
          counter = memcache.get(caller)
          if counter is None:
              memcache.set(caller,1)
          elif int(counter) <= 3:
              memcache.incr(caller,1)
          else:
              # create an event to log the quota problem
              task = Task(url='/loggingtask', params={'phone':self.request.get('From'),
                                              'inboundBody':self.request.get('Body'),
                                              'sid':self.request.get('SmsSid'),
                                              'outboundBody':'exceeded quota',})
              task.add('eventlogger')
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
      task.add('eventlogger')

      # setup the response SMS
      r = twilio.Response()
      smsBody = "Route %s, Stop %s" % (routeID, stopID) + "\n" + textBody 
      r.append(twilio.Sms(smsBody))
      self.response.out.write(r)

## end RecordingHandler

class EventLoggingHandler(webapp.RequestHandler):
    def post(self):
      # log this event...
      log = PhoneLog()
      log.phone = self.request.get('phone')
      log.body = self.request.get('inboundBody')
      log.smsID = self.request.get('sid')
      log.outboundSMS = self.request.get('outboundBody')
      log.put()
    
## end EventLoggingHandler

# this handler is intended to send out SMS messages
# via Twilio's REST interface
class SendSMSHandler(webapp.RequestHandler):
    
    def post(self):
      logging.info("Outbound SMS for ID %s to %s" % 
                   (self.request.get('sid'), self.request.get('phone')))
      account = twilio.Account(config.ACCOUNT_SID, config.ACCOUNT_TOKEN)
      sms = {
             'From' : config.CALLER_ID,
             'To' : self.request.get('phone'),
             'Body' : self.request.get('text'),
             }
      try:
          account.request('/%s/Accounts/%s/SMS/Messages' % (config.API_VERSION, config.ACCOUNT_SID),
                          'POST', sms)
      except Exception, e:
          logging.error("Twilio REST error: %s" % e)
                        
## end SendSMSHandler

class ResetQuotaHandler(webapp.RequestHandler):
    def get(self):
        logging.info("deleting the memcached quotas for the day...")
        memcache.delete_multi(config.ABUSERS)
        self.response.set_status(200)
        return
        
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
      task.add('eventlogger')

      return    
    
## end sendInvite()
        
def main():
  logging.getLogger().setLevel(logging.DEBUG)
  application = webapp.WSGIApplication([('/', MainHandler),
                                        ('/request', SMSRequestHandler),
                                        ('/_ah/mail/.+', EmailRequestHandler),
                                        ('/_ah/xmpp/message/chat/', XmppHandler),
                                        ('/loggingtask', EventLoggingHandler),
                                        ('/sendsmstask', SendSMSHandler),
                                        ('/resetquotas', ResetQuotaHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
