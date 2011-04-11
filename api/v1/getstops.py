import os
import wsgiref.handlers
import logging
import time
import re

from django.utils import simplejson
from geo.geomodel import geotypes

from google.appengine.api import users
from google.appengine.api.urlfetch import DownloadError
from google.appengine.api.labs import taskqueue
from google.appengine.api.labs.taskqueue import Task
from google.appengine.ext import webapp
from google.appengine.ext import db

from google.appengine.runtime import apiproxy_errors
import bus
from api.v1 import utils
from data_model import StopLocation

class MainHandler(webapp.RequestHandler):
    
    def get(self):
      
      # validate the request parameters
      devStoreKey = validateRequest(self.request,utils.GETSTOPS)
      if devStoreKey is None:
          logging.debug("unable to validate the request parameters")
          self.response.headers['Content-Type'] = 'application/javascript'
          self.response.out.write(simplejson.dumps(utils.buildErrorResponse('-1','Illegal request parameters')))
          return
      
      # snare the inputs
      routeID = self.request.get('routeID')
      destination = self.request.get('destination')
      stopID = self.request.get('stopID')
      logging.debug('getstops request parameters...  routeID %s destination %s' % (routeID,destination))
      
      # route requests...
      if routeID is not '' and destination is '':
          response = routeRequest(routeID, None)
          utils.recordDeveloperRequest(devStoreKey,utils.GETSTOPS,self.request.query_string,self.request.remote_addr);
      elif routeID is not '' and destination is not '':
          response = routeRequest(routeID, destination)
          utils.recordDeveloperRequest(devStoreKey,utils.GETSTOPS,self.request.query_string,self.request.remote_addr);
      elif stopID is not '':
          response = stopLocationRequest(stopID)
          utils.recordDeveloperRequest(devStoreKey,utils.GETSTOPS,self.request.query_string,self.request.remote_addr);
      else:
          logging.debug("API: invalid request")
          response = utils.buildErrorResponse('-1','Invalid Request parameters. Did you forget to include a routeID?')
          utils.recordDeveloperRequest(devStoreKey,utils.GETSTOPS,self.request.query_string,self.request.remote_addr,'illegal query string combination');

      # encapsulate response in json
      logging.debug('API: json response %s' % response);
      self.response.headers['Content-Type'] = 'application/javascript'
      self.response.out.write(simplejson.dumps(response))
    
    def post(self):
        self.response.headers['Content-Type'] = 'application/javascript'
        self.response.out.write(simplejson.dumps(utils.buildErrorResponse('-1','The API does not support POST requests')))
        return

## end MainHandler

class GetNearbyStopsHandler(webapp.RequestHandler):
    
    def get(self):
      
      # validate the request parameters
      devStoreKey = validateRequest(self.request,utils.GETNEARBYSTOPS)
      if devStoreKey is None:
          logging.debug("unable to validate the request parameters")
          self.response.headers['Content-Type'] = 'application/json'
          self.response.out.write(simplejson.dumps(utils.buildErrorResponse('-1','Illegal request parameters')))
          return
      
      # snare the inputs
      lat = float(self.request.get('lat'))
      lon = float(self.request.get('lon'))
      radius = self.request.get('radius')
      routeID = self.request.get('routeID')
      destination = self.request.get('destination')
      
      # stop location requests...
      response = nearbyStops(lat,lon,radius,routeID)

      # encapsulate response in json
      logging.debug('API: json response %s' % response);
      self.response.headers['Content-Type'] = 'application/json'
      self.response.out.write(simplejson.dumps(response))
    
    def post(self):
        self.response.headers['Content-Type'] = 'application/json'
        self.response.out.write(simplejson.dumps(utils.buildErrorResponse('-1','The API does not support POST requests')))
        return

## end GetNearbyStopsHandler

class DebugHandler(webapp.RequestHandler):

    def get(self):
      # stop location requests...
      response = nearbyStops(43.0637457,-89.4188056,500,None)

      # encapsulate response in json
      logging.debug('API: json response %s' % response);
      self.response.headers['Content-Type'] = 'application/json'
      self.response.out.write(simplejson.dumps(response))

## end DebugHandler


class NotSupportedHandler(webapp.RequestHandler):
    
    def get(self):
      
      # validate the request parameters
      devStoreKey = validateRequest(self.request)
      if devStoreKey is None:
          logging.debug("API: unsupported method")
          self.response.headers['Content-Type'] = 'application/javascript'
          self.response.out.write(simplejson.dumps(utils.buildErrorResponse('-1','This method is not yet enabled')))
          return

    def post(self):
        self.response.headers['Content-Type'] = 'application/javascript'
        self.response.out.write(simplejson.dumps(utils.buildErrorResponse('-1','The API does not support POST requests')))
        return

## end NotSupportedHandler

def nearbyStops(lat,lon,radius,routeID):

    if routeID is None or routeID == "":
        logging.debug('nearbyStops (%s,%s,%s,%s)' % (lat,lon,radius,routeID))
        results = StopLocation.proximity_fetch(
             StopLocation.all(),
             geotypes.Point(lat,lon),  # Or db.GeoPt
             max_results=5,
             max_distance=500)
    else:
        results = StopLocation.proximity_fetch(
             StopLocation.all().filter('routeID =', routeID),  # Rich query!
             geotypes.Point(lat,lon),  # Or db.GeoPt
             max_results=5,
             max_distance=500)

    if results is None:
        response_dict = {'status':'0',
                         'info':'No stops found',
                        }
        return response_dict

    
    response_dict = {'status':'0',}
    stop_results = []
    for stop in results:
        stop_results.append(dict({
                            'stopID':stop.stopID,
                            'intersection':stop.intersection,
                            'latitude':stop.location.lat,
                            'longitude':stop.location.lon,
                            }))

    response_dict.update({'stop':stop_results})
        
    return response_dict


def routeRequest(routeID,destination):
    
    if destination is not None:
        q = db.GqlQuery('select * from StopLocation where routeID = :1 and direction = :2 order by routeID', routeID, destination)
    else:
        q = db.GqlQuery('select * from StopLocation where routeID = :1 order by routeID', routeID)
    stops = q.fetch(200)
    if stops is None:
        response_dict = {'status':'0',
                         'info':'No stops found'
                        }
        return response_dict
        
    response_dict = {'status':'0',
                    }    
    
    # there should only be results. we assume the results are sorted by time
    route_dict = {'routeID':routeID,}
    stop_results = []
    for s in stops:
        if s.location is None:
            logging.error('API: ERROR, no location!?')
        else:
            logging.error('API: latitude is %s' % s.location.lat)
            
        stop_results.append(dict({'stopID':s.stopID,
                          'intersection':s.intersection,
                          'latitude':'0.0' if s.location is None else s.location.lat,
                          'longitude':'0.0' if s.location is None else s.location.lon,
                          'destination':s.direction,                          
                          }))
    
    # add the populated stop details to the response
    route_dict.update({'stops':stop_results})
    response_dict.update({'stop':route_dict})
        
    return response_dict

## end routeRequest()

def stopLocationRequest(stopID):
    
    stop = db.GqlQuery('select * from StopLocation where stopID = :1', stopID).get()
    if stop is None:
        response_dict = {'status':'0',
                         'info':('Stop %s not found' % stopID)
                        }
        return response_dict
        
    return {'status':'0',
            'stopID':stopID,
            'intersection':stop.intersection,
            'latitude':stop.location.lat,
            'longitude':stop.location.lon,
           }    
    
## end stopLocationRequest()

def validateRequest(request,type):
    
    # validate the key
    devStoreKey = utils.validateDevKey(request.get('key'))
    if devStoreKey is None:
        utils.recordDeveloperRequest(None,utils.GETSTOPS,request.query_string,request.remote_addr,'illegal developer key specified');
        return None
    
    if type == utils.GETSTOPS:
        stopID = request.get('stopID')
        routeID = request.get('routeID')
        destination = request.get('destination')
        # a stopID or routeID is required
        if routeID is None and stopID is None:
            utils.recordDeveloperRequest(devStoreKey,type,request.query_string,request.remote_addr,'either a stopID or a routeID must be included');
            return None
        elif destination is not None and routeID is None:
            utils.recordDeveloperRequest(devStoreKey,type,request.query_string,request.remote_addr,'if a destination is specified, a routeID must be included');
            return None
    elif type == utils.GETNEARBYSTOPS:
        lat = request.get('lat')
        lon = request.get('lon')
        radius = request.get('radius')
        # lat/long is required
        if lat is None or lon is None:
            utils.recordDeveloperRequest(devStoreKey,type,request.query_string,request.remote_addr,'both latitude and longitude values must be specified');
            return None
        elif radius is not None and radius is not '' and radius > '5000':
            logging.debug('unable to validate getnearbystops call. illegal radius value of %s' % radius)
            utils.recordDeveloperRequest(devStoreKey,type,request.query_string,request.remote_addr,'radius must be less than 5,000');
            return None

    logging.debug("successfully validated command parameters")
    return devStoreKey

## end validateRequest()



def main():
  logging.getLogger().setLevel(logging.DEBUG)
  application = webapp.WSGIApplication([('/api/v1/getstops', MainHandler),
                                        ('/api/v1/getstoplocation', MainHandler),
                                        ('/api/v1/getvehicles', NotSupportedHandler),
                                        ('/api/v1/getnearbystops', GetNearbyStopsHandler),
                                        ('/api/v1/getdebug', DebugHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
