import os
import wsgiref.handlers
import logging
import urllib
import base64
import time

from google.appengine.api import urlfetch
from google.appengine.api import users
from google.appengine.api.urlfetch import DownloadError
from google.appengine.api.labs import taskqueue
from google.appengine.api.labs.taskqueue import Task
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.ext.webapp import template
from google.appengine.runtime import apiproxy_errors

import bus

BOTKEY = 'D56CE348-FEC4-4432-9005110B2D25A9D3'


class TwitterHandler(webapp.RequestHandler):
    def post(self):
        if self.request.get('channel').lower() != 'private':
            logging.debug("Someone (%s) tried to send a public Twitter request with, %s" % (user,requestBody))
            return

        user = self.request.get('user')
        userkey = self.request.get('userkey')
        network = self.request.get('network')
        requestBody = self.request.get('msg')
        
        if network.lower() != 'twitter':
          logging.debug("Someone (%s) tried to send a Twitter request using network %s with, %s" % (user,network,requestBody))
          return
      
        logging.debug("A new Twitter request from %s with the request, %s" % (user,requestBody))
        
        requestArgs = requestBody.split()
        logging.debug("email body arguments %s" % requestArgs)
        if len(requestArgs) == 1:
            # assume single argument requests are for a bus stop
            sid = user + str(time.time())
            handle = user + ":" + userkey
            bus.aggregateBuses(requestBody,sid,handle)
            return

        # pull the route and stopID out of the request body and
        # pad it with a zero on the front if the message forgot 
        # to include it (that's how they are stored in the DB)
        body = requestBody
        routeID = body.split()[0]
        if len(routeID) == 1:
          routeID = "0" + routeID
 
        stopID = body.split()[1]
        if len(stopID) == 3:
          stopID = "0" + stopID
    
        textBody = bus.findBusAtStop(routeID,stopID)
        handle = user + ":" + userkey    
        sendTwitterResponse(handle, textBody, stopID, routeID)
    
## end TwitterHandler()
    

def sendTwitterResponse(handle, textBody, stopID, routeID):
    
        url = "https://www.imified.com/api/bot/"
        
        user,userkey = handle.split(':')
        logging.debug("sending twitter response to %s for key %s" % (user,userkey))
        if routeID > -1:
          twitterMsg = "Route %s, Stop %s: " % (routeID,stopID) + textBody
        else:
          twitterMsg = textBody
          
        form_fields = {'botkey':BOTKEY,
                     'apimethod':'send',
                     'userkey':userkey,
                     'user':user,
                     'network':'Twitter',
                     'channel':'private',
                     'msg':twitterMsg,
                     }
        # Build the Basic Authentication string.  Don't forget the [:-1] at the end!
        base64string = base64.encodestring('%s:%s' % ('greg.tracy@att.net', 'Truman'))[:-1]
        authString = 'Basic %s' % base64string

        # Build the request post data.
        form_data = urllib.urlencode(form_fields)

        try:
          # Make the call to the service using GAE's urlfetch command.
          response = urlfetch.fetch(url=url, payload=form_data, method=urlfetch.POST, headers={'AUTHORIZATION' : authString})

          # Check the response of 200 and process as needed.
          if response.status_code == 200:
              logging.debug("Worked:Status Code 200.<br>")
              logging.info(response.content)
          else:
              logging.debug(response.status_code)

          # create an event to log the event
          task = Task(url='/loggingtask', params={'phone':handle,
                                                'inboundBody':'?',
                                                'sid':'twitter',
                                                'outboundBody':textBody,})
          task.add('phonelogger')
        except urlfetch.DownloadError:
          logging.error("Twitter post call failed but we're going to assume it sent correctly for %s" % handle)
          return

## end sendTwitterResponse

def main():
  logging.getLogger().setLevel(logging.DEBUG)
  application = webapp.WSGIApplication([('/twitter/request', TwitterHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
