import os
import wsgiref.handlers
import logging
import time
import re

from google.appengine.api import users
from google.appengine.api import memcache
from google.appengine.api import datastore_errors
from google.appengine.api.urlfetch import DownloadError
from google.appengine.api.labs import taskqueue
from google.appengine.api.labs.taskqueue import Task
from google.appengine.ext import webapp
from google.appengine.ext import db

from google.appengine.runtime import apiproxy_errors
from api.v1 import utils

import data_model
        
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
    devStoreKey = utils.validateDevKey(request.get('key'))
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
from operator import attrgetter
def stopRequest(stopID, devStoreKey):

    logging.debug("Stop Request started")
    
    xml = '<SMSMyBusResponse><status>0</status>'
    xml += '<timestamp>'+utils.getLocalTimestamp()+'</timestamp>'
    xml += '<stop><stopID>'+stopID+'</stopID>'
    
    # query the live route store by stopID
    q = db.GqlQuery("SELECT * FROM LiveRouteStatus WHERE stopID = :1 ORDER BY dateAdded DESC LIMIT 24", stopID)
    routes = q.fetch(24)
    
    # run through the results and only preserve three results per route
    filter_routes = {}
    route_results = []
    for r in routes:
        if r.routeID in filter_routes:
            if filter_routes[r.routeID] < 3:
                logging.debug("found another route entry for %s" % r.arrivalTime)
                if utils.inthepast(r.arrivalTime):
                    logging.debug("... but it's in the past so ignore it")
                else:
                    filter_routes[r.routeID] += 1
                    route_results.append(r)
        elif utils.inthepast(r.arrivalTime) is False:
            logging.debug("found first route entry for route %s at %s" % (r.routeID,r.arrivalTime))
            filter_routes[r.routeID] = 1
            route_results.append(r)

    # sort the new list by time
    logging.debug("sorting the results list...")
    route_results = sorted(route_results, key=attrgetter('time'))
    for r in route_results:
        if r == route_results[0]:
            try:
                if r.stopLocation.location is not None:
                    xml += '<lat>'+str(r.stopLocation.location.lat)+'</lat><lon>'+str(r.stopLocation.location.lon)+'</lon>'
                else:
                    xml += '<lat>unknown</lat><lon>unknown</lon>'
            except datastore_errors.Error,e:
                if e.args[0] == "ReferenceProperty failed to be resolved":
                    xml += '<lat>unknown</lat><lon>unknown</lon>'
                else:
                    raise
                
            xml += '<intersection>'+r.intersection.replace('&','/')+'</intersection>'
            
        xml += '<route><routeID>'+r.routeID+'</routeID>'
        xml += '<vehicleID>unknown</vehicleID>'
        xml += '<minutes>'+str(utils.computeCountdownMinutes(r.arrivalTime))+'</minutes>'
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
    xml += '<timestamp>'+utils.getLocalTimestamp()+'</timestamp>'
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
        xml += '<minutes>'+str(utils.computeCountdownMinutes(r.arrivalTime))+'</minutes>'
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
    xml += '<timestamp>'+utils.getLocalTimestamp()+'</timestamp>'
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


class DevKeyHandler(webapp.RequestHandler):
    def get(self):
        dev = DeveloperKeys()
        dev.developerName = "Testing"
        dev.developerKey = "nomar"
        dev.developerEmail = "non"
        dev.requestCounter = 0
        dev.errorCounter = 0
        dev.put()
        
## end DevKeyHandler


def main():
  logging.getLogger().setLevel(logging.DEBUG)
  application = webapp.WSGIApplication([('/api/v1/getarrivals', MainHandler),
                                        ('/api/v1/createdevkey', DevKeyHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
