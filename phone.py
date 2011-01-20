import os
import wsgiref.handlers
import logging

from google.appengine.api import users
from google.appengine.api import memcache
from google.appengine.api.urlfetch import DownloadError
from google.appengine.api.labs import taskqueue
from google.appengine.api.labs.taskqueue import Task
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.ext.webapp import template

from google.appengine.runtime import apiproxy_errors
import twilio
import bus

ACCOUNT_SID = "AC781064d8f9b6bd4621333d6226768a9f"
ACCOUNT_TOKEN = "5ec48a82949b90511c78c1967a04998d"
SALT_KEY = '2J86APQ0JIE81FA2NVMC48JXQS3F6VNC'
API_VERSION = '2008-08-01'
CALLER_ID = '6084671603'
#CALLER_ID = '4155992671'

#URL_BASE = 'http://7.latest.smsmybus.appspot.com/'
URL_BASE = 'http://smsmybus.appspot.com/'

class PhoneRequestStartHandler(webapp.RequestHandler):
    
    def post(self):
        self.get()
        
    def get(self):
      # logging.info("The request from Twilio %s" % self.request)
      # validate it is in fact coming from twilio
      if ACCOUNT_SID == self.request.get('AccountSid'):
        logging.debug("PHONE request was confirmed to have come from Twilio.")
      else:
        logging.error("was NOT VALID.  It might have been spoofed!")
        self.response.out.write("Illegal caller")
        return

      # setup the response to get the recording from the caller
      r = twilio.Response()
      g = r.append(twilio.Gather(action=URL_BASE+"phone/listenforbus",
                                 method=twilio.Gather.GET,
                                 timeout=10,
                                 finishOnKey="#"))
      g.append(twilio.Say("Welcome to SMS My Bus!"))
      g.append(twilio.Say("Enter the bus number using the keypad. Press the pound key to submit.", 
                          voice=twilio.Say.MAN,
                          language=twilio.Say.ENGLISH, 
                          loop=1))
      #r.append(twilio.Record("http://smsmybus.appspot.com/listen", twilio.Record.GET, maxLength=120))
      logging.debug("now asking the caller to enter their bus route...")
      self.response.out.write(r)
        
## end PhoneRequestStartHandler


class PhoneRequestBusHandler(webapp.RequestHandler):
    
    def get(self):
      
      # logging.info("The request from Twilio %s" % self.request)
      # validate it is in fact coming from twilio
      if ACCOUNT_SID == self.request.get('AccountSid'):
        logging.debug("PHONE request was confirmed to have come from Twilio.")
      else:
        logging.error("was NOT VALID.  It might have been spoofed!")
        self.response.out.write(errorResponse("Illegal caller"))
        return

      routeID = self.request.get('Digits')
      if len(routeID) == 1:
        routeID = "0" + routeID
      memcache.add(self.request.get('AccountSid'), routeID)

      # setup the response to get the recording from the caller
      r = twilio.Response()
      g = r.append(twilio.Gather(action=URL_BASE+"phone/listenforstop",
                                 method=twilio.Gather.GET,
                                 timeout=5,
                                 numDigits=4,
                                 finishOnKey="#"))
      g.append(twilio.Say("Enter the four digit stop number using the keypad. Press the pound key to submit.", 
                          voice=twilio.Say.MAN,
                          language=twilio.Say.ENGLISH, 
                          loop=1))

      logging.debug("now asking the caller to enter their stop number...")
      self.response.out.write(r)
        
## end PhoneRequestBusHandler
        
class PhoneRequestStopHandler(webapp.RequestHandler):
    
    def get(self):
      
      # logging.info("The request from Twilio %s" % self.request)
      # validate it is in fact coming from twilio
      if ACCOUNT_SID == self.request.get('AccountSid'):
        logging.debug("PHONE request was confirmed to have come from Twilio.")
      else:
        logging.error("was NOT VALID.  It might have been spoofed!")
        self.response.out.write(errorResponse("Illegal caller"))
        return
    
      # pull the route and stopID out of the request body and
      # pad it with a zero on the front if the message forgot 
      # to include it (that's how they are stored in the DB)
      routeID = memcache.get(self.request.get('AccountSid'))
      memcache.delete(self.request.get('AccountSid'))
 
      stopID = self.request.get('Digits')
      if len(stopID) == 3:
        stopID = "0" + stopID
    
      textBody = bus.findBusAtStop(routeID,stopID)    

      # create an event to log the event
      input = "%s %s" % (routeID, stopID)
      task = Task(url='/loggingtask', params={'phone':self.request.get('Caller'),
                                              'inboundBody':input,
                                              'sid':self.request.get('SmsSid'),
                                              'outboundBody':textBody,})
      task.add('eventlogger')

      # transform the text a smidge so it can be pronounced more easily...
      # 1. strip the colons
      textBody = textBody.replace(':', ' ')
      # 2. add a space between p-and-m and a-and-m
      textBody = textBody.replace('pm', 'p m').replace('am', 'a m')
      
      # setup the response
      r = twilio.Response()
      r.append(twilio.Say(textBody, 
                          voice=twilio.Say.MAN,
                          language=twilio.Say.ENGLISH, 
                          loop=1))
      #r.append(twilio.Record("http://smsmybus.appspot.com/listen", twilio.Record.GET, maxLength=120))
      
      
      logging.debug("now telling the caller their schedule...")
      self.response.out.write(r)

## end PhoneRequestStopHandler

            
def main():
  logging.getLogger().setLevel(logging.DEBUG)
  application = webapp.WSGIApplication([('/phone/request', PhoneRequestStartHandler),
                                        ('/phone/listenforbus', PhoneRequestBusHandler),
                                        ('/phone/listenforstop', PhoneRequestStopHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
