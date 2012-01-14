import os
import wsgiref.handlers
import logging

from django.utils import simplejson
from geo.geomodel import geotypes

from google.appengine.api import memcache

from google.appengine.ext import webapp
from google.appengine.ext import db

from google.appengine.ext.webapp.util import run_wsgi_app

from api.v1 import utils

class StaticAPIs(db.Model):
    method = db.StringProperty()
    json   = db.TextProperty()
    date   = db.DateTimeProperty(auto_now_add=True)
#

class MainHandler(webapp.RequestHandler):
    
    def get(self):
      
      # validate the request parameters
      devStoreKey = 'nomar'#validateRequest(self.request,utils.GETROUTES)
      if devStoreKey is None:
          logging.debug("unable to validate the request parameters")
          self.response.headers['Content-Type'] = 'application/javascript'
          self.response.out.write(simplejson.dumps(utils.buildErrorResponse('-1','Illegal request parameters')))
          return
      
      logging.debug('getroutes request...  ')
      
      if utils.afterHours() is True:
          # don't run these jobs during "off" hours
	      json_response = utils.buildErrorResponse('-1','The Metro service is not currently running')
      else:
          json_response = memcache.get(utils.GETROUTES)
          if json_response is None:
              api = db.GqlQuery('select * from StaticAPIs where method = :1', utils.GETROUTES).get()
              if api is not None:
                  logging.debug('---> datastore hit');
                  json_response = api.json
              else:
                  json_response = getRoutes()
                  static = StaticAPIs()
                  static.method = utils.GETROUTES
                  static.json = json_response
                  static.put()
                  
              # drop it into the memcache again
              memcache.add(utils.GETROUTES, json_response)
              logging.debug('---> storing in memcache');
          else:
              logging.debug('---> memcache hit');
              
          utils.recordDeveloperRequest(devStoreKey,utils.GETROUTES,self.request.query_string,self.request.remote_addr);

      #logging.debug('API: json response %s' % json_response);    
      # encapsulate response in json
      callback = self.request.get('callback')
      if callback is not '':
          self.response.headers['Content-Type'] = 'application/javascript'
          self.response.headers['Access-Control-Allow-Origin'] = '*'
          self.response.headers['Access-Control-Allow-Methods'] = 'GET'
          response = callback + '(' + simplejson.dumps(json_response) + ');'
      else:
          self.response.headers['Content-Type'] = 'application/json'
          response = json_response
      
      self.response.out.write(response)

    def post(self):
        self.response.headers['Content-Type'] = 'application/javascript'
        self.response.out.write(simplejson.dumps(utils.buildErrorResponse('-1','The API does not support POST requests')))
        return

## end MainHandler


def getRoutes():
    
    q = db.GqlQuery('select * from RouteListing order by route')
    routes = q.fetch(2000)
    if routes is None:
        response_dict = {'status':'0',
                         'info':'No routes found'
                        }
        return response_dict
        
    response_dict = {'status':'0',
                    }    
    ## stopped here trying to create a map of unique routes and endpoints
    ##
    hits = {}
    for r in routes:
        # are we tracking this route/direction pair?
        key = r.route + ':' + r.direction
        hits[key] = hits.get(key,0) + 1

    routeMap = {}        
    for k,v in hits.iteritems():
        key = k.split(':')
        routeID = key[0]
        direction = key[1]
        directionLabel = utils.getDirectionLabel(direction)
        
        logging.debug('adding direction %s to route %s' % (directionLabel,routeID))
        if routeID in routeMap:
            routeMap[routeID].append(directionLabel)
        else:
            routeMap[routeID] = list()
            routeMap[routeID].append(directionLabel)
        
    route_results = []
    for k,v in routeMap.iteritems():
        route_results.append(dict({'routeID':k,'directions':routeMap[k]}))
    
    # add the populated route details to the response
    response_dict.update({'routes':route_results})
        
    return simplejson.dumps(response_dict)

## end getRoutes()

def validateRequest(request,type):
    
    # validate the key
    devStoreKey = utils.validateDevKey(request.get('key'))
    if devStoreKey is None:
        utils.recordDeveloperRequest(None,utils.GETSTOPS,request.query_string,request.remote_addr,'illegal developer key specified');
        return None
    
    return devStoreKey

## end validateRequest()

application = webapp.WSGIApplication([('/api/v1/getroutes', MainHandler),
                                      ],
                                     debug=True)

def main():
  logging.getLogger().setLevel(logging.DEBUG)
  run_wsgi_app(application)
  #wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
