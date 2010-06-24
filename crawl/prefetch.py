import wsgiref.handlers
import logging
import re
import time
from datetime import timedelta
from datetime import datetime

from google.appengine.api import quota
from google.appengine.api import urlfetch
from google.appengine.api import memcache
from google.appengine.api.urlfetch import DownloadError
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.ext.db import GeoPt

from google.appengine.runtime import apiproxy_errors

from data_model import LiveRouteStatus
from data_model import LiveVehicleStatus
from geo.geomodel import GeoModel

ROUTE_URLBASE = "http://webwatch.cityofmadison.com/webwatch/UpdateWebMap.aspx?u="

class CrawlerHandler(webapp.RequestHandler):
    def get(self, routeID=""):
        # don't run these jobs during "off" hours
        ltime = time.localtime()
        ltime_hour = ltime.tm_hour - 5
        ltime_hour += 24 if ltime_hour < 0 else 0
        if ltime_hour > 1 and ltime_hour < 6:
            self.response.out.write('offline')
            return

        try:
            scrapeURL = ROUTE_URLBASE + routeID
            
            loop = 0
            done = False
            result = None
            start = quota.get_request_cpu_usage()
            while not done and loop < 2:
                try:
                    # fetch the page
                    result = urlfetch.fetch(scrapeURL)
                    done = True;
                except urlfetch.DownloadError:
                    logging.error("Error loading page (%s)... sleeping" % loop)
                    if result:
                        logging.error("Error status: %s" % result.status_code)
                        logging.error("Error header: %s" % result.headers)
                        logging.error("Error content: %s" % result.content)
                        time.sleep(4)
                        loop = loop+1
            end = quota.get_request_cpu_usage()
            logging.info("scraping took %s cycles" % (end-start))
            if not done:
                logging.error("prefecth failed... couldn't fetch the URL %s" % scrapeURL)
                return

            # get the local time and convert it to madison time
            ltime = time.localtime()
            ltime_hour = ltime.tm_hour - 5
            ltime_hour += 24 if ltime_hour < 0 else 0
            ltime_min = ltime_hour * 60 + ltime.tm_min
            logging.debug("local time... %s (%s:%s) day minutes %s" % (ltime,ltime_hour,ltime.tm_min,ltime_min))

            # parser for the stop data...
            stops = result.content.split('<br>')

            # the very first line in the content should always start
            # with the date, timestamp, and route endpoint.
            logging.info("Parsed FIRST LINE... %s" % stops[0])

            # grab the timestamp out of the first line
            data = re.search('(\d+/\d+/\d+)\s+(\d+:\d+:\d+)\s+(\d+)*',stops[0])
            if data is not None:
                date = data.group(1)
                timestamp = data.group(2)                
            logging.info("date... %s time... %s" % (date,timestamp))

            routeToken = '-7'
            lat = '40'
            lon = '-80'
            intersection = ' '
            stopID = '0'
            arrivalEstimate = ' '
            destination = ' '
            vehicleStats = []

            
            # hackish... the stop data gets collapsed together if there is no bus
            # arriving at individual stops. try to detect this and adjust when necessary
            if stops[0].find('||') > -1:
                logging.info("hack! lines are crunched together...")
                firstLine = stops[0].split('||')[-1]
            else:
                firstLine = stops[0]
            
            data = re.search('(\d+\.\d+)\|(-\d+\.\d+)\|(.*?)\|(.*?)\|(\d+:\d+\s+\w+)\sTO\s(.*?)',firstLine)
            if data is not None:
                #routeToken = data.group(1)
                lat = data.group(1)
                lon = data.group(2)
                intersection = data.group(3)
                destination = data.group(4)
                arrival = data.group(5)
                routeQualifier = data.group(6)
            
            for s in stops:
                #logging.info("Parsing... %s" % s)
                if s == stops[0]:
                    #logging.info("skipping the first line...")
                    continue
                
                # hackish... the stop data gets collapsed together if there is no bus
                # arriving at individual stops. try to detect this and adjust when necessary
                if s.find('||') > -1:
                    logging.info("hack! lines are crunched together...\n%s" % s)
                    realLine = s.split('||')[-1]
                    logging.info("the real line... %s" % realLine)
                else:
                    realLine = s.rstrip()

                data = re.search('(\d+);(\d+\.\d+)\|(-\d+\.\d+)\|(.*?)\|(.*?)\|(\d+:\d+\s\w+)\s(.*)',realLine)
                if data is not None:
                    #logging.info("Parsed NEW STOP... %s" % realLine)
                    routeToken = data.group(1)
                    lat = data.group(2)
                    lon = data.group(3)
                    
                    # hack... the stop ID isn't always encoded. check to see if we need to pull it out
                    intersection = data.group(4)
                    stopID = '0'
                    if intersection.find("ID#") > -1:
                        stopDetails = re.search('(.*?)\[ID#(\d+)\]',intersection)
                        intersection = stopDetails.group(1)
                        stopID = stopDetails.group(2)
                    elif stopID == '0':
                        stopID = findStopID(intersection,destination)
                        stopID = '0' if stopID is None else stopID
                        logging.debug("extracted stop ID %s using intersection %s, direction %s" % (stopID,intersection,destination))
                        
                    destination = data.group(5)
                    arrivalEstimate = data.group(6)
                    routeQualifier = data.group(7)
                    #logging.info("%s + %s + %s + %s + %s + %s + %s + %s" % (routeToken,lat,lon,intersection,stopID,destination,arrivalEstimate,destination))
                    status = LiveRouteStatus()
                    status.routeToken = routeToken
                    status.routeID = routeID
                    status.stopID = stopID
                    status.arrivalTime = arrivalEstimate
                    status.intersection = intersection
                    status.destination = destination
                    status.routeQualifier = routeQualifier
                    status.stopLocation = getLocation(lat,lon,stopID)
                    status.time = getAbsoluteTime(arrivalEstimate)

                    # commit to datastore
                    status.put()
                    
                elif re.search('^\d+:\d+',realLine) is not None:
                    #logging.debug("we're assuming this is a timestamp line for stopID %s" % stopID)
                    data = re.search('(\d+:\d+\s\w+)\s+TO\s+(.*)',realLine)
                    if data is not None:
                        #logging.info("%s + %s" % (data.group(1),data.group(2)))
                        status = LiveRouteStatus()
                        status.routeToken = routeToken
                        status.routeID = routeID
                        status.stopID = stopID
                        status.arrivalTime = data.group(1)
                        status.time = getAbsoluteTime(data.group(1))
                        status.intersection = intersection
                        status.destination = destination
                        status.routeQualifier = data.group(2)
                        status.stopLocation = getLocation(lat,lon,stopID)
                        status.put()
                        
                elif realLine.endswith(';') is False:
                    #logging.debug("we're parsing details for a specific vehicle %s" % realLine)
                    vehicleStats.append(realLine)
                else:
                    logging.error("bogus route entry line. we have no idea what to do with it! %s" % realLine)
                      
            # parse the vehicle detail data we collected...
            lat = '0'
            lon = '0'
            destination = '-1'
            vehicleID = '-1'
            #logging.debug("start to analyze vehicle data (length: %s)" % len(vehicleStats))
            for v in vehicleStats:
                # these lines are very POORLY formed. the first entry has junk on the front
                # and the lat/lon data one line will reference a vehicle defined on the next line
                data = re.search('\d+;\*(\d+\.\d+)\|(-\d+\.\d+)\|\d+\|\<b\>(.*?)\<',v)
                if data is not None:
                    #logging.debug("found first vehicle line... %s" % v)
                    lat = data.group(1)
                    lon = data.group(2)
                    destination = data.group(3)
                elif v.find("Vehicle") > -1:
                    #logging.debug("found a vehicle identifier... %s" % v)
                    data = re.search('Vehicle.*?:\s(\d+)',v)
                    if data is not None:
                        vehicleID = data.group(1).lstrip().rstrip()
                    else:
                        vehicleID = '-1'
                        #logging.error("unable to identify a vehicle number!?")
                elif v.find("Timepoint") > -1:
                    #logging.debug("found a timepoint... %s" % v)
                    if v.find("*") > -1:
                        # this is the last entry so the regular expression is a bit different
                        data = re.search('Timepoint\:\s+(.*?);\*',v)
                        if data is not None:
                            # if we're already tracking this vehicle, replace it.
                            # otherwise, create a new one.
                            q = db.GqlQuery("SELECT * FROM LiveVehicleStatus WHERE routeID = :1 and vehicleID = :2",routeID,vehicleID)
                            vehicle = q.get()
                            if vehicle is None:
                                #logging.debug("NEW BUS!")
                                vehicle = LiveVehicleStatus()
                            vehicle.routeID = routeID
                            vehicle.vehicleID = vehicleID
                            vehicle.location = GeoPt(lat,lon)
                            vehicle.destination = destination
                            vehicle.nextTimepoint = data.group(1)
                            #logging.info("adding new vehicle (1)... %s at %s" % (vehicleID,vehicle.location))
                            vehicle.put()
                        else:
                            logging.error("VEHICLE SCAN: invalid timepoint entry!!")
                    else:
                        data = re.search('Timepoint\:\s+(.*?);(\d+\.\d+)\|(-\d+\.\d+)\|\d+\|\<b\>(.*?)\<',v)
                        if data is not None:
                            # if we're already tracking this vehicle, replace it.
                            # otherwise, create a new one.
                            q = db.GqlQuery("SELECT * FROM LiveVehicleStatus WHERE routeID = :1 and vehicleID = :2",routeID,vehicleID)
                            vehicle = q.get()
                            if vehicle is None:
                                #logging.debug("NEW BUS!")
                                vehicle = LiveVehicleStatus()
                            vehicle.routeID = routeID
                            vehicle.vehicleID = vehicleID
                            vehicle.location = GeoPt(lat,lon)
                            vehicle.destination = destination
                            vehicle.nextTimepoint = data.group(1)
                            #logging.info("adding new vehicle (2)... %s at %s" % (vehicleID,vehicle.location))
                            vehicle.put()

                            # now reset lat/lon for the next loop iteration
                            lat = data.group(2)
                            lon = data.group(3)
                            destination = data.group(4)
                        else:
                            logging.error("VEHICLE SCAN: invalid timepoint entry!!")

        
        except apiproxy_errors.DeadlineExceededError:
            logging.error("DeadlineExceededError exception!?")
            return
        
        return
    
## end CrawlerHandler()
        
class CrawlerCheckHandler(webapp.RequestHandler):
    
    def get(self,routeID=""):
        return
        
## end CrawlerCheckHandler

class CrawlerCleanerHandler(webapp.RequestHandler):
    def get(self,table=""):
        hourAgo = timedelta(hours=1)
        logging.info("hour ago... %s",hourAgo)
        timestamp = datetime.now() - hourAgo
        logging.info("current time... %s",datetime.now())
        logging.info("timestamp for query... %s",timestamp)
        qstring = "select __key__ from " + table + " where dateAdded < :1"
        logging.info("crawler cleaning :: query string is... %s" % qstring)
        q = db.GqlQuery(qstring,timestamp)
        results = q.fetch(500)
        while results:
            db.delete(results)
            results = q.fetch(500, len(results))
## end CrawlerCleanerHandler

def findStopID(intersection,direction):
    
    intersection = intersection.upper()
    cacheKey = intersection+":"+direction
    stopID = memcache.get(cacheKey)
    if stopID is None:
        stop = db.GqlQuery("SELECT * FROM StopLocation WHERE intersection = :1 and direction = :2", intersection, direction).get()
        if stop is not None:
            stopID = stop.stopID
            logging.debug("adding stop %s to memcache" % stopID)
            memcache.add(cacheKey,stopID)
        else:
            logging.error("impossible! we couldn't find this intersection, %s, in the datastore" % intersection)
    
    return stopID

## end findStopID

def getLocation(lat,lon,stopID):
    
    # we're taking lat/long and stopID as arguments, but in fact
    # only using stopID for the datastore and memcache queries.
    # however, since the metro's feed doesn't include the stopID
    # in some cases, for some unknown reason, i'll use the a 
    # concatenated string of lat/long
    
    #logging.debug("fetching stop location for stop %s : %s,%s" % (stopID, lat,lon))
    
    if stopID == '0':
        geoString = lat+","+lon
    else:
        geoString = stopID
        
    geoKey = memcache.get(geoString)
    if geoKey is None:
        if stopID != '0':
            geoKey = db.GqlQuery("SELECT __key__ FROM StopLocation where stopID = :1",
                                 stopID).get()
        else:
            geoKey = db.GqlQuery("SELECT __key__ FROM StopLocation where location = :1",
                                 geoString).get()
            
        if geoKey is not None:
            #logging.debug("adding %s key to memcache" % geoKey)
            memcache.add(geoString,geoKey)
        else:
            logging.error("Unable to getLocation for this stop %s,%s" % (lat,lon))
            
    return geoKey
## end getLocation()
    
def getAbsoluteTime(timestamp):
    
    arrivalMinutes = 999999
    
    # turn the arrival time into absolute minutes
    #logging.debug("chop up arrival time... %s" % timestamp)
    hours = int(timestamp.split(':')[0])
    if timestamp.find('PM') > 0 and int(hours) < 12:
        hours += 12
        minutes = int(timestamp.split(':')[1].split()[0])
        arrivalMinutes = (hours * 60) + minutes
        #logging.debug("chop up produced %s hours and %s minutes - %s" % (hours,minutes,arrivalMinutes))
    else:
        logging.error("invalid timestamp parsing!?! %s" % timestamp)
        
    return arrivalMinutes
## end getAbsoluteTime()


def main():
  logging.getLogger().setLevel(logging.DEBUG)
  application = webapp.WSGIApplication([('/crawl/prefetch/(.*)', CrawlerHandler),
                                        ('/crawl/clean/(.*)', CrawlerCleanerHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()

