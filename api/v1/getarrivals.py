import os
import wsgiref.handlers
import logging
import time
import re

from google.appengine.api import users
from google.appengine.api import memcache
from google.appengine.api.urlfetch import DownloadError
from google.appengine.api.labs import taskqueue
from google.appengine.api.labs.taskqueue import Task
from google.appengine.ext import webapp
from google.appengine.ext import db

from google.appengine.runtime import apiproxy_errors
import bus
        
class MainHandler(webapp.RequestHandler):
    
    def get(self):
      
      # validate the request parameters
      devStoreKey = validateRequest(self.request)
      if devStoreKey is None:
          logging.debug("unable to validate the request parameters")
          xml = buildXMLErrorResponse()
          self.response.header['Content-Type'] = 'text/xml'
          self.response.out.write(xml)
          return
      
      # snare the inputs
      stopID = self.request.get('stopID')
      routeID = self.request.get('routeID')
      vehicleID = self.request.get('vehicleID')
      logging.debug('getarrivals request parameters...  stopID %s routeID %s vehicleID %s' % (stopID,routeID,vehicleID))
      
      # stopID requests...
      if stopID is not '' and routeID is '':
          logging.debug("stop request")
          xml = stopRequest(stopID, devStoreKey)
      elif stopID is not '' and routeID is not '':
          logging.debug("stop route request")
          xml = stopRouteRequest(stopID, routeID, devStoreKey)
      elif routeID is not '' and vehicleID is not '':
          logging.debug("route vehicle request")
          xml = routeVehicleRequest(routeID, vehicleID, devStoreKey)
      else:
          logging.debug("invalid request")
          xml = buildXMLErrorResponse()

      self.response.headers['Content-Type'] = 'text/xml'
      self.response.out.write(xml)

## end RequestHandler

def buildXMLErrorResponse():
    xml = '<SMSMyBusResponse><status>-1</status><description>Invalid request parameters</description></SMSMyBusResponse>'
    return xml
## end

def validateRequest(request):
    
    # validate the key
    devStoreKey = validateDevKey(request.get('key'))
    if devStoreKey is None:
        return None
    stopID = request.get('stopID')
    routeID = request.get('routeID')
    vehicleID = request.get('vehicleID')
    
    # a stopID or routeID is required
    if stopID is None and routeID is None:
        return None
    
    # the routeID requires either a vehicleID or stopID
    if routeID is not None:
        if vehicleID is None and stopID is None:
            return None
    
    # the vehicleID requires a routeID
    if vehicleID is not None:
        if routeID is None:
            return False
        
    logging.debug("successfully validated command parameters")
    return devStoreKey

## end validateRequest()

def validateDevKey(devKey):
    
    # special dev key
    if devKey == 'nomar': 
        logging.info("found the magic dev key...")
        return 1
    
    if devKey is None:
        return None
   
    storeKey = memcache.get(dev)
    if storeKey is None:
        q = db.GqlQuery("SELECT __key__ FROM DeveloperKeys WHERE developerKey = :1", devKey)
        storeKey = q.get()
        if storeKey is None:
            return None
        else:
            memcache.put(devKey, storeKey)
    
    return storeKey
    
## end validateDevKey()

def getLocalTimestamp():
    
    # get the local, server time
    ltime = time.localtime()
    ltime_hour = ltime.tm_hour - 5  # convert to madison time
    ltime_hour += 24 if ltime_hour < 0 else 0
    ltime_min = ltime_hour * 60 + ltime.tm_min
    logging.debug("local time... %s (%s:%s) day minutes %s" % (ltime,ltime_hour,ltime.tm_min,ltime_min))
    
    tstamp_min = str(ltime.tm_min) if ltime.tm_min >= 10 else ("0"+str(ltime.tm_min))
    tstamp_hour = str(ltime_hour) if ltime_hour <=12 else str(ltime_hour-12)
    tstamp_label = "pm" if ltime_hour > 11 else "am"

    return(tstamp_hour+':'+tstamp_min+tstamp_label)

## end getLocalTimestamp()

def computeCountdownMinutes(arrivalTime):

    # compute current time in minutes
    ltime = time.localtime()
    ltime_hour = ltime.tm_hour - 5
    ltime_hour += 24 if ltime_hour < 0 else 0
    ltime_min = ltime_hour * 60 + ltime.tm_min
    #logging.info("local time: %s hours %s minutes", (ltime_hour,ltime_min))
    
    # pull out the time
    m = re.search('(\d+):(\d+)\s(.*?)',arrivalTime)
    btime_hour = arrival_hour = int(m.group(1))
    btime_min = int(m.group(2))
    #logging.info("computing countdown with %s - %s hours %s minutes", (arrivalTime,btime_hour,btime_min))
                 
    # determine whether we're in the morning or afternoon
    # and adjust hours accordingly
    if arrivalTime.find('PM') > -1:
        btime_hour += 12 if btime_hour < 12 else 0
 
    delta_in_min = (btime_hour*60 + btime_min) - ltime_min
    return(delta_in_min)

## end computeCountdownMinutes()

def stopRequest(stopID, devStoreKey):

    logging.debug("Stop Request started")
    
    xml = '<SMSMyBusResponse><status>0</status>'
    xml += '<timestamp>'+getLocalTimestamp()+'</timestamp>'
    xml += '<stop><stopID>'+stopID+'</stopID>'
    
    # query the live route store by stopID
    q = db.GqlQuery("SELECT * FROM LiveRouteStatus WHERE stopID = :1 ORDER BY dateAdded DESC LIMIT 24", stopID)
    routes = q.fetch(24)
    
    # run through the results and only preserve three results per route
    filter_routes = {}
    routes_min = []
    for r in routes:
        if r.routeID in filter_routes:
            if filter_routes[r.routeID] < 3:
                logging.debug("found another route entry for %s" % r.arrivalTime)
                filter_routes[r.routeID] += 1
                routes_min.append(r)
        else:
            logging.debug("found first route entry for route %s" % r.routeID)
            filter_routes[r.routeID] = 1
            routes_min.append(r)

                    
    for r in routes_min:
        if r == routes_min[0]:
            if r.stopLocation.location is not None:
                xml += '<lat>'+str(r.stopLocation.location.lat)+'</lat><lon>'+str(r.stopLocation.location.lon)+'</lon>'
            else:
                xml += '<lat>unknown</lat><lon>unknown</lon>'
            xml += '<intersection>'+r.intersection.replace('&','/')+'</intersection>'
        xml += '<route><routeID>'+r.routeID+'</routeID>'
        xml += '<vehicleID>unknown</vehicleID>'
        xml += '<minutes>'+str(computeCountdownMinutes(r.arrivalTime))+'</minutes>'
        xml += '<arrivalTime>'+r.arrivalTime+'</arrivalTime>'
        xml += '<destination>'+r.destination+'</destination>'
        xml += '<direction>'+r.routeQualifier+'</direction>'
        xml += '</route>'
    # end for
    xml += '</stop></SMSMyBusResponse>'
    
    logging.debug("Stop Request: %s" % xml)
    return xml

## end stopRequest()


def stopRouteRequest(stopID, routeID, devStoreKey):
    logging.debug("Stop/Route Request started")
    
    xml = '<SMSMyBusResponse><status>0</status>'
    xml += '<timestamp>'+getLocalTimestamp()+'</timestamp>'
    xml += '<stop><stopID>'+stopID+'</stopID>'
    
    # query the live route store by stopID
    q = db.GqlQuery("SELECT * FROM LiveRouteStatus WHERE stopID = :1 and routeID = :2 ORDER BY dateAdded DESC LIMIT 3", stopID, routeID)
    routes = q.fetch(3)
    for r in routes:
        if r == routes[0]:
            xml += '<lat>'+str(r.stopLocation.location.lat)+'</lat><lon>'+str(r.stopLocation.location.lon)+'</lon>'
            xml += '<intersection>'+r.intersection.replace('&','/')+'</intersection>'
        xml += '<route><routeID>'+r.routeID+'</routeID>'
        xml += '<vehicleID>unknown</vehicleID>'
        xml += '<minutes>'+str(computeCountdownMinutes(r.arrivalTime))+'</minutes>'
        xml += '<arrivalTime>'+r.arrivalTime+'</arrivalTime>'
        xml += '<destination>'+r.destination+'</destination>'
        xml += '<direction>'+r.routeQualifier+'</direction>'
        xml += '</route>'
    # end for
    xml += '</stop></SMSMyBusResponse>'
    
    logging.debug("Stop/Route Request: %s" % xml)
    return xml

## end stopRouteRequest()

def routeVehicleRequest(routeID, vehicleID, devStoreKey):
    logging.debug("Route/Vehicle Request started for %s, route %s vehicle %s" % (devStoreKey,routeID,vehicleID))
    
    xml = '<SMSMyBusResponse><status>0</status>'
    xml += '<timestamp>'+getLocalTimestamp()+'</timestamp>'
    xml += '<route><routeID>'+routeID+'</routeID>'
    
    # query the live route store by routeID and vehicleID
    q = db.GqlQuery("SELECT * FROM LiveVehicleStatus WHERE routeID = :1 and vehicleID = :2 ORDER BY dateAdded", routeID,vehicleID)
    vehicles = q.fetch(10)
    for v in vehicles:
        xml += '<vehicle><vehicleID>'+v.vehicleID+'</vehicleID>'
        xml += '<lat>'+str(v.location.lat)+'</lat><lon>'+str(v.location.lon)+'</lon>'
        xml += '<nextTimepoint>'+v.nextTimepoint.replace('&','/')+'</nextTimepoint>'
        xml += '<destination>'+v.destination+'</destination>'
        xml += '</vehicle>'
    # end for
    xml += '</route></SMSMyBusResponse>'
    
    logging.debug("Route/Vehicle Request: %s" % xml)
    return xml

## end stopRouteRequest()



def main():
  logging.getLogger().setLevel(logging.DEBUG)
  application = webapp.WSGIApplication([('/api/v1/getarrivals', MainHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
