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
import utils
        
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
      routeID = self.request.get('routeID')
      destination = self.request.get('destination')
      logging.debug('getstops request parameters...  routeID %s destination %s' % (routeID,destination))
      
      xml = '<SMSMyBusResponse><status>0</status>'
      xml += '<timestamp>'+getLocalTimestamp()+'</timestamp>'
      xml += '<stop><stopID>'+stopID+'</stopID>'
    
      # query the stoplocationID
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
    routeID = request.get('routeID')
    destination = request.get('destination')
    
    # a stopID or routeID is required
    if routeID is None:
        return None
            
    logging.debug("successfully validated command parameters")
    return devStoreKey

## end validateRequest()

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
  application = webapp.WSGIApplication([('/api/v1/getstops', MainHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
