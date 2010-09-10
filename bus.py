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

def findBusAtStop(routeID, stopID):
    
      q = db.GqlQuery("SELECT * FROM RouteListing WHERE route = :1 AND stopID = :2",
                      routeID, stopID)
      routeQuery = q.fetch(10)
      if len(routeQuery) > 0:
          if len(routeQuery) > 2:
              logging.error("Snap. There is more than one route in the datastore!?! route %s stop %s" %
                            (routeID, stopID))
          
          scheduleURL = []
          for r in routeQuery:
              scheduleURL.append(r.scheduleURL)
      else:
          logging.error("Huh... we couldn't find this route information %s", )
          smsBody = "Route %s, Stop %s\n" % (routeID, stopID) + "Sorry. We do not have this route information on file." 
          return(smsBody)

      start = quota.get_request_cpu_usage()
      textBody = ""
      validMsg = False
      for s in scheduleURL:
          # extract the direction ID from the URL
          routeData = s.split('?')[1]
          routeArgs = routeData.split('&')
          directionID = routeArgs[1].split('=')[1]
          logging.debug("Requesting schedule... %s " % s)

          directionLabel = getDirectionLabel(directionID)
          loop = 0
          done = False
          result = None
          while not done and loop < 3:
             try:
               # go fetch the webpage for this route/stop!
               result = urlfetch.fetch(s)
               done = True;
             except urlfetch.DownloadError:
               logging.error("Error loading page (%s)... sleeping" % loop)
               if result:
                   logging.error("Error status: %s" % result.status_code)
                   logging.error("Error header: %s" % result.headers)
                   logging.error("Error content: %s" % result.content)
               time.sleep(3)
               loop = loop+1
           
          if result is None or result.status_code != 200:
             logging.error("Exiting early: error fetching URL: " + result.status_code)
             textBody = "Route %s, Stop %s\n" % (routeID, stopID) + "Sorry. The Metro site appears to be down!"
          else:
             soup = BeautifulSoup(result.content)
             textBody += "toward %s" % directionLabel + "\n"

             skip = False
             for slot in soup.html.body.findAll("a","ada"):
                validMsg = True
                logging.debug("pulling out a timeslot from page... %s" % slot)
                # only take the first time entry
                if slot['title'].split(':')[0].isdigit() and not skip:
                  logging.debug("the actual time is %s" % slot['title'])
                  textBody += slot['title'].replace('P.M.','pm').replace('A.M.','am') + "\n"
                  #skip = True
                elif slot['title'].find('Prediction') > -1:
                  time = "(as of " + slot['title'][23:35] + ")\n"
         
      if validMsg is False:
          textBody = "Snap! It looks like route %s isn't running right now..." % routeID
      elif len(textBody) > 140:
          # truncate the message if it's too long for some reason
          logging.error("Text body is too long!?! %s" % textBody)
          textBody = textBody[0:120]
      #else:
      #    textBody += time
               
      fetch_time = quota.get_request_cpu_usage()
      logging.debug("fetching the URL cost %d cycles" % (fetch_time-start))

      logging.info("Returning the message, %s" % textBody)
      return(textBody)
  
  ## end findBusAtStop()

def aggregateBuses(stopID, sid, caller):
    
    if len(stopID) == 3:
        stopID = "0" + stopID
        
    q = db.GqlQuery("SELECT * FROM RouteListing WHERE stopID = :1",stopID)
    routeQuery = q.fetch(100)
    if len(routeQuery) == 0:
        # this should never ever happen
        logging.error("Huh? There are no matching stops for this ID?!? %s" % stopID)
        textBody = "Snap! It looks like stop %s isn't running right now..." % stopID
        # send back the error only if this was an SMS request
        if caller.isdigit() is True:
            task = Task(url='/sendsmstask', params={'phone':caller,
                                                    'sid':sid,
                                                    'text':textBody,})
            task.add('smssender')
    else:
        memcache.add(sid,0)
        for r in routeQuery:
            counter = memcache.incr(sid)
            task = Task(url='/aggregationtask', 
                        params={'sid':sid,
                                'stop':stopID,
                                'route':r.route,
                                'direction':r.direction,
                                'url':r.scheduleURL,
                                'caller':caller
                                })
            task.add('aggregation')
            logging.debug("Added new task for bus aggregation %s route %s counter: %s" % (sid, r.route, counter))

    
    return

## end aggregateBuses()

def aggregatAsynchResults(sid, phone):
    
      stopID = '-1'
      textBody = ''
      logging.debug("Time to report back to %s on results for %s..." % (phone,sid))
      
      # if this request is via email or is the prefetcher, grab multiple results
      num_records = 4
      if phone.find('@') > -1 or phone.find('prefetch') > -1:
          num_records = 10
          
      q = db.GqlQuery("SELECT * FROM BusStopAggregation WHERE sid = :1 ORDER BY time", sid)
      routeQuery = q.fetch(num_records)
      if len(routeQuery) > 0:
          stopID = routeQuery[0].stopID
          textBody = "Stop %s\n" % routeQuery[0].stopID
          for r in routeQuery:
              textBody += "Route %s " % r.routeID + " %s" % r.text + "\n"
      else:
          logging.error("We couldn't find this SMS transaction information %s. Chances are there aren't any matches with the request." % sid)
          textBody = "Doesn't look good... Your bus isn't running right now!"
        
      if phone.find('@') > -1 and phone.find('/') > -1:
          # assuming that this is an XMPP request - not SMS
          sendXmppResponse(phone, textBody)
      elif phone.find('@') > -1:
          # assuming that this is an email request - not SMS
          sendEmailResponse(phone, textBody)          
      elif phone.find('prefetch') > -1:
          # assuming that this is a prefetch request - not SMS
          rest.postResults(sid, phone, textBody)
          return # don't log this event
      elif phone.isdigit() is False:
          # assuming that this is a twitter request - not SMS
          twitter.sendTwitterResponse(phone, textBody, stopID, routeID=-1)
      elif phone.find('%') > -1:
          # special web request for testing
          return
      else:
          # it's an SMS request!
          logging.info("Initiating return SMS for ID %s from %s" % (sid,phone))
          account = twilio.Account(ACCOUNT_SID, ACCOUNT_TOKEN)
          sms = {
                 'From' : CALLER_ID,
                 'To' : phone,
                 'Body' : textBody,
                }
          try:
              account.request('/%s/Accounts/%s/SMS/Messages' % (API_VERSION, ACCOUNT_SID),
                              'POST', sms)
          except Exception, e:
              logging.error("Twilio REST error: %s" % e)
                        
      # create an event to log the event
      task = Task(url='/loggingtask', params={'phone':phone,
                                              'inboundBody':stopID,
                                              'sid':sid,
                                              'outboundBody':textBody,})
      task.add('phonelogger')

      return
  
## end aggregatAsynchResults()

def handle_result(rpc,stopID,routeID,sid,directionID):
    result = None
    try:
        # go fetch the webpage for this route/stop!
        result = rpc.get_result()
        done = True;
    except urlfetch.DownloadError:
         logging.error("Error loading page (%s)... sleeping" % loop)
         if result:
            logging.error("Error status: %s" % result.status_code)
            logging.error("Error header: %s" % result.headers)
            logging.error("Error content: %s" % result.content)
           
    directionLabel = getDirectionLabel(directionID)       
    arrival = '0'
    textBody = 'unknown'
    valid = False
    if result is None or result.status_code != 200:
           logging.error("Exiting early: error fetching URL: " + result.status_code)
           textBody = routeID + " (missing data)"
    else:
           soup = BeautifulSoup(result.content)
           for slot in soup.html.body.findAll("a","ada"):
              logging.debug("pulling out a timeslot from page... %s" % slot)
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
    logging.debug("bus route processed... new counter is %s" % counter)
    if counter == 0:
        # put them all together
        memcache.delete(sid)
        aggregateAsynchResults(sid,caller)

# Use a helper function to define the scope of the callback.
def create_callback(rpc,stopID,routeID,sid,directionID):
    return lambda: handle_result(rpc,stopID,routeID,sid,directionID)

def aggregateBusesAsynch(stopID, sid, caller):
    if len(stopID) == 3:
        stopID = "0" + stopID
        
    q = db.GqlQuery("SELECT * FROM RouteListing WHERE stopID = :1",stopID)
    routeQuery = q.fetch(100)
    if len(routeQuery) == 0:
        # this should never ever happen
        logging.error("Huh? There are no matching stops for this ID?!? %s" % stopID)
        textBody = "Snap! It looks like stop %s isn't running right now..." % stopID
        # send back the error only if this was an SMS request
        if caller.isdigit() is True:
            task = Task(url='/sendsmstask', params={'phone':caller,
                                                    'sid':sid,
                                                    'text':textBody,})
            task.add('smssender')
    else:
        rpcs = []
        memcache.add(sid,0)
        for r in routeQuery:
            counter = memcache.incr(sid)
            rpc = urlfetch.create_rpc()
            #rpc.callback = create_callback(rpc,stopID,r.route,sid,r.direction)
            logging.info("initiating asynchronous fetch from %s" % r.scheduleURL)
            urlfetch.make_fetch_call(rpc, r.scheduleURL)
            rpcs.append(rpc)
            
        # all of the schedule URLs have been fetched. now wait for them to finish
        for rpc in rpcs:
            #rpc.wait()
            handle_result(rpc,stopID,routeID,sid,directionID)
    
    return
## end aggregateBusesAsynch()


def getDirectionLabel(directionID):
    directionLabel = memcache.get("directionID")
    if directionLabel is None:
        q = db.GqlQuery("SELECT * FROM DestinationListing WHERE id = :1", directionID)
        directionQuery = q.fetch(1)
        if len(directionQuery) > 0:
            logging.debug("Found destination ID mapping... %s :: %s" % (directionQuery[0].id,directionQuery[0].label))
            directionLabel = directionQuery[0].label
            memcache.add(directionID, directionLabel)
        else:
            logging.error("ERROR: We don't have a record of this direction ID!?! Impossible! %s" % directionID)
            directionLabel = "unknown"
            
    return directionLabel

## end getDirectionLabel()
