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

      if textBody.find('route') > -1:
          xml = '<SMSMyBusResponse><status>-1</status></SMSMyBusResponse>'
          self.response.headers['Content-Type'] = 'text/xml'
          self.response.out.write(xml)
          return

      xml = '<SMSMyBusResponse><status>0</status><route>' + routeID + '</route><stop>' + stopID + '</stop>'
      # transform the text a smidge so it can be pronounced more easily...
      #textBody = textBody.replace('pm', '').replace('am', '')
      
      ltime = time.localtime()
      ltime_hour = ltime.tm_hour - 5
      ltime_hour += 24 if ltime_hour < 0 else 0
      ltime_min = ltime_hour * 60 + ltime.tm_min
      logging.debug("local time... %s (%s:%s) day minutes %s" % (ltime,ltime_hour,ltime.tm_min,ltime_min))
            
      logging.debug("textBody.... %s" % textBody)
      tlist = textBody.split('\n')
      
      tstamp_min = str(ltime.tm_min) if ltime.tm_min >= 10 else ("0"+str(ltime.tm_min))
      tstamp_hour = str(ltime_hour) if ltime_hour <=12 else str(ltime_hour-12)
      tstamp_label = "pm" if ltime_hour > 11 else "am"
      xml += '<timestamp>'+tstamp_hour+':'+tstamp_min+tstamp_label+'</timestamp>'
      
      xml += '<estimates>'
      for t in tlist:
          logging.debug("convert %s" % t)
          if t.find(':') > -1:
              if t.find('pm') > -1:
                  t = t.replace('pm', '')
                  adjust = 12 if int(t.split(':')[0]) < 12 else 0
              else:
                  t = t.replace('am', '')
                  adjust = 0
              btime = t.split(':')
              btime_hour = int(btime[0])+adjust
              btime_min = int(btime[1])
              delta_in_min = (btime_hour*60+int(btime[1])) - ltime_min
              xml += '<minutes>' + str(delta_in_min) + '</minutes>'
      xml += '</estimates>'
                            
      
      self.response.headers['Content-Type'] = 'text/xml'
      self.response.out.write(xml+'</SMSMyBusResponse>')
                              
## end PhoneRequestStopHandler

            
def main():
  logging.getLogger().setLevel(logging.DEBUG)
  application = webapp.WSGIApplication([('/rest/(.*)/(.*)/', RequestHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
