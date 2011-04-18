import logging

from datetime import date
from datetime import timedelta
import time

from google.appengine.api import urlfetch
from google.appengine.api import memcache
from google.appengine.api import quota
from google.appengine.api.urlfetch import DownloadError
from google.appengine.api.labs import taskqueue
from google.appengine.api.labs.taskqueue import Task

from google.appengine.ext import db

from google.appengine.runtime import apiproxy_errors
from BeautifulSoup import BeautifulSoup, Tag
from data_model import RouteListing
from data_model import DestinationListing
from data_model import BusStopAggregation

from api.v1 import utils


def aggregateBusesAsynch(sid, stopID, routeID=None):
    if len(stopID) == 3:
        stopID = "0" + stopID
        
    # @todo add memcache support for route listings
    if routeID is None:
        q = db.GqlQuery("SELECT * FROM RouteListing WHERE stopID = :1",stopID)
    else:
        q = db.GqlQuery("SELECT * FROM RouteListing WHERE stopID = :1 AND route = :2",stopID,routeID)
        
    routeQuery = q.fetch(100)
    if len(routeQuery) == 0:
        # this should never ever happen
        logging.error("API: Huh? There are no matching stops for this ID?!? %s" % stopID)
        return None
    else:
        # create a bunch of asynchronous url fetches to get all of the route data
        rpcs = []
        memcache.set(sid,0)
        for r in routeQuery:
            rpc = urlfetch.create_rpc()
            rpc.callback = create_callback(rpc,stopID,r.route,sid,r.direction)
            logging.info("API: initiating asynchronous fetch for %s" % r.scheduleURL)
            counter = memcache.incr(sid)
            urlfetch.make_fetch_call(rpc, r.scheduleURL)
            rpcs.append(rpc)
            
        # all of the schedule URLs have been fetched. now wait for them to finish
        for rpc in rpcs:
            logging.info('waiting on rpc call... %s ' % memcache.get(sid))
            rpc.wait()
        
        # all call should be complete at this point    
        while memcache.get(sid) > 0 :
            logging.info('API: ERROR : uh-oh. in waiting loop... %s' % memcache.get(sid))
            rpc.wait()
            
        return aggregateAsynchResults(sid)
    

## end aggregateBusesAsynch()

#
# once all of the results have been grabbed, piece them together
#
def aggregateAsynchResults(sid):
      logging.info("API: Time to report back on results for %s..." % sid)
      
      q = db.GqlQuery("SELECT * FROM BusStopAggregation WHERE sid = :1 ORDER BY time", sid)
      routes = q.fetch(10)
      if len(routes) == 0:
          #logging.debug("We couldn't find results for transaction %s. Chances are there aren't any matches with the request." % sid)
          textBody = "Doesn't look good... Your bus isn't running right now!"

      return routes
  
## end aggregatAsynchResults()

#
# This function handles the callback of a single fetch request.
# If all requests for this sid are services, aggregate the results
#
def handle_result(rpc,stopID,routeID,sid,directionID):
    routes = None
    result = None
    try:
        # go fetch the webpage for this route/stop!
        result = rpc.get_result()
        done = True;
    except urlfetch.DownloadError:
         logging.error("API: Error loading page. route %s, stop %s" % (routeID,stopID))
         if result:
            logging.error("API: Error status: %s" % result.status_code)
            logging.error("API: Error header: %s" % result.headers)
            logging.error("API: Error content: %s" % result.content)
           
    directionLabel = utils.getDirectionLabel(directionID)       
    arrival = '0'
    textBody = 'unknown'
    valid = False
    if result is None or result.status_code != 200:
           logging.error("API: Exiting early: error fetching URL: " + result.status_code)
           textBody = "error " + routeID + " (missing data)"
    else:
           soup = BeautifulSoup(result.content)
           for slot in soup.html.body.findAll("a","ada"):
              # only take the first time entry
              if slot['title'].split(':')[0].isdigit():
                arrival = slot['title']
                textBody = arrival.replace('P.M.','pm').replace('A.M.','am')
                valid = True
                # add these results to datastore until we're ready to put
                # them all together
                stop = BusStopAggregation()
                stop.stopID = stopID
                stop.routeID = routeID
                stop.sid = sid
                stop.arrivalTime = textBody
                stop.destination = directionLabel
          
                # turn the arrival time into absolute minutes
                logging.debug("chop up arrival time... %s" % arrival)
                hours = int(arrival.split(':')[0])
                if arrival.find('P.M.') > 0 and int(hours) < 12:
                    hours += 12
                minutes = int(arrival.split(':')[1].split()[0])
                arrivalMinutes = (hours * 60) + minutes
                logging.debug("chop up produced %s hours and %s minutes" % (hours,minutes))
                stop.time = arrivalMinutes
          
                stop.text = textBody + " toward %s" % directionLabel
                stop.put()

    # create the task that glues all the messages together when 
    # we've finished the fetch tasks
    counter = memcache.decr(sid)
    logging.info("bus route processed... new counter is %s" % counter)
    if counter == 0:
        # put them all together
        memcache.delete(sid)
        #routes = aggregateAsynchResults(sid)
        
    return routes

## end

# Use a helper function to define the scope of the callback.
def create_callback(rpc,stopID,routeID,sid,directionID):
    return lambda: handle_result(rpc,stopID,routeID,sid,directionID)
