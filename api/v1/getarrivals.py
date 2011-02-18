import os
import wsgiref.handlers
import logging
import time
import re

from google.appengine.api import users
from google.appengine.api import datastore_errors
from google.appengine.api.urlfetch import DownloadError
from google.appengine.api.labs import taskqueue
from google.appengine.api.labs.taskqueue import Task
from google.appengine.ext import webapp
from google.appengine.ext import db

from google.appengine.runtime import apiproxy_errors

from django.utils import simplejson

from api.v1 import utils
from api import asynch

import data_model

class MainHandler(webapp.RequestHandler):
    # POST not support by the API
    def post(self):
        self.response.headers['Content-Type'] = 'application/javascript'
        self.response.out.write(simplejson.dumps(utils.buildErrorResponse('-1','The API does not support POST requests')))
        return
    
    def get(self):
      
      # validate the request parameters
      devStoreKey = validateRequest(self.request)
      if devStoreKey is None:
          self.response.headers['Content-Type'] = 'application/javascript'
          self.response.out.write(simplejson.dumps(utils.buildErrorResponse('-1','Illegal developer key received')))
          return
      
      # snare the inputs
      stopID = self.request.get('stopID')
      routeID = self.request.get('routeID')
      vehicleID = self.request.get('vehicleID')
      logging.debug('getarrivals request parameters...  stopID %s routeID %s vehicleID %s' % (stopID,routeID,vehicleID))
      
      # stopID requests...
      if stopID is not '' and routeID is '':
          response = stopRequest(stopID, devStoreKey)
      elif stopID is not '' and routeID is not '':
          response = stopRouteRequest(stopID, routeID, devStoreKey)
      elif routeID is not '' and vehicleID is not '':
          response = routeVehicleRequest(routeID, vehicleID, devStoreKey)
      else:
          logging.debug("API: invalid request")
          response = utils.buildXMLErrorResponse('-1','Invalid Request parameters')

      # encapsulate response in json
      logging.debug('API: json response %s' % response);
      self.response.headers['Content-Type'] = 'application/javascript'
      self.response.out.write(simplejson.dumps(response))

## end RequestHandler

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
def stopRequest(stopID, devStoreKey):

    logging.debug("Stop Request started")
    response_dict = {'status':'0',
                     'timestamp':utils.getLocalTimestamp()
                     }    
    
    # @todo the really busy stops have their data cached. hook this up
    # q = db.GqlQuery("SELECT * FROM LiveRouteStatus WHERE stopID = :1 ORDER BY dateAdded DESC LIMIT 24", stopID)
    # routes = q.fetch(24)
    
    # got fetch all of the data for this stop
    sid = stopID + str(devStoreKey) + str(time.time())
    routes = asynch.aggregateBusesAsynch(sid,stopID)

    # get the stop details
    stop_dict = {'stopID':stopID,}
    
    # take the first 10 results. we assume the results are sorted by time
    #route_results = sorted(route_results, key=attrgetter('time'))
    route_results = []
    for r in routes:
        if not utils.inthepast(r.arrivalTime):
            route_results.append(dict({'routeID':r.routeID,
                          'vehicleID':'unknown',
                          'minutes':str(utils.computeCountdownMinutes(r.arrivalTime)),
                          'arrivalTime':r.arrivalTime,
                          'destination':r.destination,
                          }))            
    
    # add the populated stop details to the response
    stop_dict.update({'route':route_results});
    response_dict.update({'stop':stop_dict})
        
    return response_dict

## end stopRequest()


def stopRouteRequest(stopID, routeID, devStoreKey):
    logging.debug("Stop/Route Request started")

    # got fetch all of the data for this stop
    sid = stopID + str(devStoreKey) + str(time.time())
    routes = asynch.aggregateBusesAsynch(sid,stopID,routeID)
    if routes is None:
        response_dict = {'status':'0',
                         'timestamp':utils.getLocalTimestamp(),
                         'info':'No routes found'
                        }
        return response_dict
    
    # query the live route store by stopID
    #q = db.GqlQuery("SELECT * FROM LiveRouteStatus WHERE stopID = :1 and routeID = :2 ORDER BY dateAdded DESC LIMIT 3", stopID, routeID)
    #routes = q.fetch(3)

    response_dict = {'status':'0',
                     'timestamp':utils.getLocalTimestamp()
                     }    
    
    # there should only be results. we assume the results are sorted by time
    stop_dict = {'stopID':stopID,}
    route_results = []
    for r in routes:
        if not utils.inthepast(r.arrivalTime):
            route_results.append(dict({'routeID':r.routeID,
                          'vehicleID':'unknown',
                          'minutes':str(utils.computeCountdownMinutes(r.arrivalTime)),
                          'arrivalTime':r.arrivalTime,
                          'destination':r.destination,
                          }))
    
    # add the populated stop details to the response
    stop_dict.update({'route':route_results});
    response_dict.update({'stop':stop_dict})
        
    return response_dict

## end stopRouteRequest()

def routeVehicleRequest(routeID, vehicleID, devStoreKey):
    logging.debug("Route/Vehicle Request started for %s, route %s vehicle %s" % (devStoreKey,routeID,vehicleID))
    
    # encapsulate response in json
    return {'status':'-1',
            'timestamp':getLocalTimestamp(),
            'description':'Vehicle requests calls are not yet supported',
           }

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
