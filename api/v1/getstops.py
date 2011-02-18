import os
import wsgiref.handlers
import logging
import time
import re

from django.utils import simplejson

from google.appengine.api import users
from google.appengine.api.urlfetch import DownloadError
from google.appengine.api.labs import taskqueue
from google.appengine.api.labs.taskqueue import Task
from google.appengine.ext import webapp
from google.appengine.ext import db

from google.appengine.runtime import apiproxy_errors
import bus
from api.v1 import utils

class MainHandler(webapp.RequestHandler):
    
    def get(self):
      
      # validate the request parameters
      devStoreKey = validateRequest(self.request)
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
      elif routeID is not '' and destination is not '':
          response = routeRequest(routeID, destination)
      elif stopID is not '':
          response = stopLocationRequest(stopID)
      else:
          logging.debug("API: invalid request")
          response = utils.buildXMLErrorResponse('-1','Invalid Request parameters. Did you forget to include a routeID?')

      # encapsulate response in json
      logging.debug('API: json response %s' % response);
      self.response.headers['Content-Type'] = 'application/javascript'
      self.response.out.write(simplejson.dumps(response))
    
    def post(self):
        self.response.headers['Content-Type'] = 'application/javascript'
        self.response.out.write(simplejson.dumps(utils.buildErrorResponse('-1','The API does not support POST requests')))
        return

## end MainHandler

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
    route_dict.update({'stops':stop_results});
    response_dict.update({'stop':route_dict})
        
    return response_dict

## end routeRequest()

def stopLocationRequest(stopID):
    
    stop = db.GqlQuery('select * from StopLocation where stopID = :1', stopID).get()
    if stop is None:
        response_dict = {'status':'0',
                         'info':('Stop %s not found', stopID)
                        }
        return response_dict
        
    return {'status':'0',
            'stopID':stopID,
            'intersection':stop.intersection,
            'latitude':'0.0',#stop.location,
            'longitude':'0.0',#stop.location,
           }    
    
## end stopLocationRequest()

def validateRequest(request):
    
    # validate the key
    devStoreKey = utils.validateDevKey(request.get('key'))
    if devStoreKey is None:
        return None
    stopID = request.get('stopID')
    routeID = request.get('routeID')
    destination = request.get('destination')
    
    # a stopID or routeID is required
    if routeID is None and stopID is None:
        return None
    elif destination is not None and routeID is None:
        return None
            
    logging.debug("successfully validated command parameters")
    return devStoreKey

## end validateRequest()



def main():
  logging.getLogger().setLevel(logging.DEBUG)
  application = webapp.WSGIApplication([('/api/v1/getstops', MainHandler),
                                        ('/api/v1/getstoplocation', MainHandler),
                                        ('/api/v1/getvehicles', NotSupportedHandler),
                                        ('/api/v1/getnearbystops', NotSupportedHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
