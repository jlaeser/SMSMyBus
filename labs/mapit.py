import os
import wsgiref.handlers
import logging
from operator import itemgetter

from google.appengine.api import memcache
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.ext.webapp import template

from google.appengine.runtime import apiproxy_errors
from data_model import PhoneLog
from data_model import StopLocation


class MapHandler(webapp.RequestHandler):
    def get(self):
      # do some analysis on the request history...
      reqs = dict()
      cursor = None
      # Start a query for all Person entities.
      q = PhoneLog.all()
      while q is not None:
          # If the app stored a cursor during a previous request, use it.
          if cursor:
              q.with_cursor(cursor)

          # Perform the query to get 500 results.
          log_events = q.fetch(500)
          cursor = q.cursor()

          logQuery = q.fetch(500)
          if len(logQuery) > 0:
            for e in logQuery:
                    
                # add up all of the unique stop IDs
                requestString = e.body.split()
                if len(requestString) >= 2:
                    stopID = requestString[1]
                elif len(requestString) > 0:
                    stopID = requestString[0]
                    
                if len(requestString) > 0 and stopID.isdigit() and len(stopID) == 4:
                    if stopID in reqs:
                        reqs[stopID] += 1
                    else:
                        reqs[stopID] = 1
          else:
              logging.debug('nothing left!')
              break

      # review the results for popular stops
      stops_stats = []
      for key,value in reqs.items():
          stops_stats.append({'stopID':key,
                              'count':value,
                              })

      # do we have the stop locations?
      stopLocations = memcache.get_multi(reqs.keys())
      if stopLocations is None:
          logging.error("unable to find stop locations!?")
          msg = "no data"
      else:
          msg = "your data"
          
      locations = []
      for key,value in stopLocations.items():
          locations.append({'stopID':key,
                            'location':value,
                            })
          
      template_values = {'stops':stops_stats,
                         'locations':locations,
                         'message':msg,
                         }
        
      # create a page that provides a form for sending an SMS message
      path = os.path.join(os.path.dirname(__file__), 'mapit.html')
      self.response.out.write(template.render(path,template_values))
    
## end MapHandler()

class CollectorHandler(webapp.RequestHandler):
    def get(self):
      # do some analysis on the request history...
      reqs = dict()
      cursor = None
      # Start a query for all Person entities.
      q = PhoneLog.all()
      while q is not None:
          # If the app stored a cursor during a previous request, use it.
          if cursor:
              q.with_cursor(cursor)

          # Perform the query to get 500 results.
          logQuery = q.fetch(500)
          cursor = q.cursor()
          if len(logQuery) > 0:
            logging.debug('read in another chunk of phone logs...')
            for e in logQuery:
                    
                # add up all of the unique stop IDs
                requestString = e.body.split()
                if len(requestString) >= 2:
                    stopID = requestString[1]
                elif len(requestString) > 0:
                    stopID = requestString[0]
                    
                if len(requestString) > 0 and stopID.isdigit() and len(stopID) == 4:
                    if stopID in reqs:
                        reqs[stopID] += 1
                    else:
                        reqs[stopID] = 1
          else:
              logging.debug('done reading phone logs...')
              break

      # find that lat/longs for all the stops
      validStops = reqs.keys()      
      stopLocs = memcache.get_multi(validStops)
      if stopLocs or stopLocs is None:
        logging.error("logging stop locations!")
        locations = dict()
        cursor = None
        # Start a query for all Person entities.
        q = StopLocation.all()
        while q is not None:
          # If the app stored a cursor during a previous request, use it.
          if cursor:
              q.with_cursor(cursor)

          # Perform the query to get 500 results.
          locationQuery = q.fetch(500)
          cursor = q.cursor()
          if len(locationQuery) > 0:
            logging.debug('just read in another chunk of stop locations...')
            for l in locationQuery:
                location = l.location
                if location is not None and l.stopID in validStops:
                    logging.debug('adding location %s for stopID %s' % (location,l.stopID))
                    stopLocs.append({l.stopID:location})
      
        memcache.set_multi(stopLocs)

      return
    
## end CollectorHandler

def main():
  logging.getLogger().setLevel(logging.DEBUG)
  application = webapp.WSGIApplication([('/labs/map', MapHandler),
                                        ('/labs/maptask', CollectorHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
