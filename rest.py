import os
import wsgiref.handlers
import logging
import time

from google.appengine.api import users
from google.appengine.api import memcache
from google.appengine.api.urlfetch import DownloadError
from google.appengine.api.labs import taskqueue
from google.appengine.api.labs.taskqueue import Task
from google.appengine.ext import webapp

from google.appengine.runtime import apiproxy_errors
import bus

        
class RequestHandler(webapp.RequestHandler):
    
    def get(self, routeID="", stopID=""):
      
      # validate the request parameters
      if len(routeID) == 0 or len(stopID) == 0:
        logging.info("Illegal web service call with route (%s) and stop (%s)", (routeID, stopID))
        self.response.out.write(errorResponse("Illegal request parameters"))
        return
    
      if len(routeID) == 1:
        routeID = "0" + routeID
      if len(stopID) == 3:
        stopID = "0" + stopID
    
      textBody = bus.findBusAtStop(routeID,stopID)

      # create an event to log the event
      input = "%s %s" % (routeID, stopID)
      task = Task(url='/loggingtask', params={'phone':'REST',
                                              'inboundBody':("%s:%s", (routeID,stopID)),
                                              'sid':'empty',
                                              'outboundBody':textBody,})
      task.add('phonelogger')

      xml = '<SMSMyBusResponse><route>' + routeID + '</route><stop>' + stopID + '</stop>'
      # transform the text a smidge so it can be pronounced more easily...
      textBody = textBody.replace('pm', '').replace('am', '')
      
      ltime = time.localtime()
      ltime_min = (ltime.tm_hour-5) * 60 + ltime.tm_min
      logging.debug("local time... %s day minutes %s" % (ltime,ltime_min))
            
      logging.debug("textBody.... %s" % textBody)
      tlist = textBody.split('\n')
      
      xml += '<estimates>'
      for t in tlist:
          logging.debug("convert %s" % t)
          if t.find(':') > -1:
              btime = t.split(':')
              #btime = time.strptime(t, "%H:%M ")
              logging.debug("formatted time... %s:%s" % (btime[0],btime[1]))
              btime_hour = int(btime[0])+12
              btime_min = int(btime[1])
              delta_in_min = (btime_hour*60+int(btime[1])) - ltime_min
              xml += '<minutes>' + str(delta_in_min) + '</minutes>'
      xml += '</estimates>'
                            
      
      self.response.headers['Content-Type'] = 'text/xml'
      self.response.out.write(xml+'</SMSMyBusResponse>')
                              
## end PhoneRequestStopHandler

            
def main():
  logging.getLogger().setLevel(logging.DEBUG)
  application = webapp.WSGIApplication([('/rest/(.*)/(.*)', RequestHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
