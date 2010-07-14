import wsgiref.handlers
import logging
import re
import os

from google.appengine.api import quota
from google.appengine.api import urlfetch
from google.appengine.api import memcache
from google.appengine.api import datastore_errors
from google.appengine.api.urlfetch import DownloadError
from google.appengine.api.labs import taskqueue
from google.appengine.api.labs.taskqueue import Task
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.ext.webapp import template
from google.appengine.ext.db import GeoPt

from google.appengine.runtime import apiproxy_errors

from BeautifulSoup import BeautifulSoup, Tag

from data_model import RouteListing
from data_model import StopLocation


URLBASE = "http://webwatch.cityofmadison.com/webwatch/ada.aspx?"
CRAWL_URLBASE = "http://webwatch.cityofmadison.com/webwatch/Ada.aspx"

class CrawlerHandler(webapp.RequestHandler):
    def get(self):
        # create a new task with this link
        crawlURL = "http://webwatch.cityofmadison.com/webwatch/Ada.aspx"
        task = Task(url='/crawlingtask', params={'crawl':crawlURL,'routeID':'00'})
        task.add('crawler')
        logging.info("Added new task for %s" % crawlURL)        
        return
    
## end CrawlerHandler()
        
class CrawlingTaskHandler(webapp.RequestHandler):
    def post(self):
        try:
            scrapeURL = self.request.get('crawl')
            direction = self.request.get('direction')
            routeID = self.request.get('routeID')
            logging.debug("task scraping for %s, direction %s, route %s" % (scrapeURL,direction,routeID))
            
            loop = 0
            done = False
            result = None
            start = quota.get_request_cpu_usage()
            while not done and loop < 3:
                try:
                    # fetch the page
                    result = urlfetch.fetch(scrapeURL)
                    done = True;
                except urlfetch.DownloadError:
                    logging.info("Error loading page (%s)... sleeping" % loop)
                    if result:
                        logging.debug("Error status: %s" % result.status_code)
                        logging.debug("Error header: %s" % result.headers)
                        logging.debug("Error content: %s" % result.content)
                        time.sleep(4)
                        loop = loop+1
            end = quota.get_request_cpu_usage()
            #logging.info("scraping took %s cycles" % (end-start))

            # start to interrogate the results
            soup = BeautifulSoup(result.content)
            for slot in soup.html.body.findAll("a","ada"):
                #logging.info("pulling out data from page... %s" % slot)

                if slot.has_key('href'):
                    href = slot['href']
                    title = slot['title']
                    logging.info("FOUND A TITLE ----> %s" % title)
                    # route crawler looks for titles with an ID# string
                    if title.find("[ID#") > 0:
                        # we finally got down to the page we're looking for
                        
                        # pull the stopID from the page content...
                        stopID = title.split("ID#")[1].split("]")[0]
                        
                        # pull the intersection from the page content...
                        intersection = title.split("[")[0].strip()
                        
                        logging.info("found stop %s, %s" % (stopID,intersection))
                        
                        # check for conflicts...
                        q = db.GqlQuery("SELECT * FROM StopLocation WHERE stopID = :1 and direction = :2", stopID,direction.upper())
                        stopQuery = q.fetch(1)
                        if len(stopQuery) == 0:
                            # add the new stop
                            stop = StopLocation()
                            stop.stopID = stopID
                            stop.routeID = routeID
                            stop.intersection = intersection.upper()
                            stop.direction = direction.upper()
                            stop.put()
                            logging.info("added new stop listing MINUS geo location")
                        else:
                            logging.info("already have this stop in the table...")
                        
                        # pull the route and direction data from the URL
                        #routeData = scrapeURL.split('?')[1]
                        #logging.info("found the page! arguments: %s stopID: %s" % (routeData,stopID))
                        #routeArgs = routeData.split('&')
                        #routeID = routeArgs[0].split('=')[1]
                        #directionID = routeArgs[1].split('=')[1]
                        #timeEstimatesURL = CRAWL_URLBASE + href
                    
                        # check for conflicts...
                        #q = db.GqlQuery("SELECT * FROM RouteListing WHERE route = :1 AND direction = :2 AND stopID = :3",
                                        #routeID, directionID, stopID)
                        #routeQuery = q.fetch(1)
                        #if len(routeQuery) == 0:
                          # add the new route to the DB
                          #route = RouteListing()
                          #route.route = routeID
                          #route.direction = directionID
                          #route.stopID = stopID
                          #route.scheduleURL = timeEstimatesURL
                          #route.put()
                          #logging.info("added new route listing entry to the database!")
                        #else:
                          #logging.error("we found a duplicate entry!?! %s", routeQuery[0].scheduleURL)
                    #else: # title.split(",")[0].isdigit():
                    elif href.find("?r=") > -1:
                        # create a new task with this link
                        crawlURL = CRAWL_URLBASE + href
                        if routeID == '00' or len(routeID) > 2:
                            routeID = href.split('r=')[1]
                        task = Task(url='/crawlingtask', params={'crawl':crawlURL,'direction':title,'routeID':routeID})
                        task.add('crawler')
                        logging.info("Added new task for %s, direction %s, route %s" % (title.split(",")[0],title,routeID))                    
                    # label crawler looks for titles with letters for extraction/persistence
                    #elif title.replace('-','').replace(' ','').isalpha():
                    #    routeData = href.split('?')[1]
                    #    logging.info("found the route LABEL page! href: %s" % href)
                    #    routeArgs = routeData.split('&')
                    #    directionID = routeArgs[1].split('=')[1]
                    #    
                    #    l = DestinationListing.get_or_insert(title, id=directionID, label=title)

                                        
        except apiproxy_errors.DeadlineExceededError:
            logging.error("DeadlineExceededError exception!?")
            return
            
        return;
    
## end CrawlingTask()


class CrawlGeoHandler(webapp.RequestHandler):
    def get(self):
        crawlURL = "http://webwatch.cityofmadison.com/webwatch/Ada.aspx"
        task = Task(url='/crawlinggeotask', params={'crawl':crawlURL,})
        task.add('crawler')
        logging.info("Added new task for %s" % crawlURL)        
        return
    
        
class CrawlingGeoTaskHandler(webapp.RequestHandler):
    def post(self):
        try:
            scrapeURL = self.request.get('crawl')
            logging.debug("task scraping for %s" % scrapeURL)
            
            loop = 0
            done = False
            result = None
            start = quota.get_request_cpu_usage()
            while not done and loop < 3:
                try:
                    # fetch the page
                    result = urlfetch.fetch(scrapeURL)
                    done = True;
                except urlfetch.DownloadError:
                    logging.info("Error loading page (%s)... sleeping" % loop)
                    if result:
                        logging.debug("Error status: %s" % result.status_code)
                        logging.debug("Error header: %s" % result.headers)
                        logging.debug("Error content: %s" % result.content)
                        time.sleep(4)
                        loop = loop+1
            end = quota.get_request_cpu_usage()
            logging.info("scraping took %s cycles" % (end-start))

            if result.content[0] == '7':
                # parser for the geo stop data...
                stops = result.content.split('<br>')
                for s in stops:
                    #logging.info("Parsing... %s" % s)
                    if s[0] == '|':
                        # |18;43.0656205|-89.4237496|ALLEN & COMMONWEALTH [ID#2969]|CapSq|3:20 PM TO CAP SQR
                        data = re.search('\|\d+;.*?(4.*?)\|(.*?)\|(.*?)\[ID#(\d+)\]\|(.*?)\|',s)
                        if data is None:
                            # |32;43.0527923|-89.43559|Monroe & Glenway|Allied-Chalet|2:40 PM TO ALLD DR:MOHAWK
                            data = re.search('\|\d+;.*?(4.*?)\|(.*?)\|(.*?)\|(.*?)\|',s)
                            if data is not None:
                                latitude = data.group(1).strip()
                                longitude = data.group(2).strip()
                                intersection = data.group(3).strip()
                                direction = data.group(4).strip()
                        else:
                            latitude = data.group(1).strip()
                            longitude = data.group(2).strip()
                            intersection = data.group(3).strip()
                            stopID = data.group(4).strip()
                            direction = data.group(5).strip()
                                                            
                        if data is not None:
                            logging.debug("creating task to store this stop in the datastore...")
                            # create a task event to process the data and check/store in the datastore
                            task = Task(url='/storethestop', params={'intersection':intersection,
                                                                     'latitude':latitude,
                                                                     'longitude':longitude,
                                                                     'direction':direction,
                                                                     'crawlLine':s,
                                                                    })
                            task.add('stopstorage')
                            
 
                return
            
            # start to interrogate the results
            soup = BeautifulSoup(result.content)
            for slot in soup.html.body.findAll("a","ada"):
                logging.info("pulling out data from page... %s" % slot)

                if slot.has_key('href'):
                    href = slot['href']
                    title = slot['title']
                    logging.info("FOUND A TITLE ----> %s" % title)
                    # route crawler looks for titles with an ID# string
                    if title.find("[ID#") > 0:
                        # this should never happen
                        logging("FATAL ERROR")
                    elif href.find("?r=") > -1:
                        crawlURL = "http://webwatch.cityofmadison.com/webwatch/UpdateWebMap.aspx?u="+href.split("=")[1]
                        task = Task(url='/crawlinggeotask', params={'crawl':crawlURL,})
                        task.add('crawler')
                        logging.info("Added new task for %s" % crawlURL)

        except apiproxy_errors.DeadlineExceededError:
            logging.error("DeadlineExceededError exception!?")
            return
            
        return;
    
## end

class DropTableHandler(webapp.RequestHandler):
    def get(self, table=""):
        qstring = "select * from " + table
        logging.info("query string is... %s" % qstring)
        q = db.GqlQuery(qstring)
        results = q.fetch(500)
        while results:
            if table == 'RouteListing':
                for r in results:
                    try:
                        sLocation = r.stopLocation
                    except datastore_errors.Error,e:
                        if e.args[0] == "ReferenceProperty failed to be resolved":
                            sLocation = None
                        else:
                            raise
                    if sLocation is not None:
                        r.stopLocation = None
                        r.put()
            else:
                db.delete(results)
    
            results = q.fetch(500, len(results))

## end
    
class StopStorageHandler(webapp.RequestHandler):
    def post(self):
        intersection = self.request.get('intersection')
        latitude = self.request.get('latitude')
        longitude = self.request.get('longitude')
        direction = self.request.get('direction')
        logging.info("storing intersection %s at lat/lon %s,%s toward %s" % (intersection,latitude,longitude,direction))
        
        if len(intersection) > 400:
            intersection = intersection.ljust(400)
            
        q = db.GqlQuery("SELECT * FROM StopLocation WHERE intersection = :1 AND direction = :2", intersection.upper(),direction.upper())
        stop = q.get()
        if stop is None:
            logging.debug("We DON'T already have this stop in the store!?! %s to %s" % (intersection.upper(),direction.upper()))
            # create a task event to process the error
            task = Task(url='/crawl/errortask', params={'intersection':intersection,
                                                        'location':(latitude+","+longitude),
                                                        'direction':direction,
                                                        'metaStringOne':self.request.get('crawlLine'),
                                                        'metaStringTwo':'from geotask crawler'
                                                      })
            task.add('crawlerrors')
        else:
            stop.location = GeoPt(latitude,longitude)
            stop.update_location()
            #stop.direction = direction
            stop.put()
            logging.info("GEO DATA ADDED for %s" % intersection)
                                
            # update the route table to include a reference to the new geo data
            q = db.GqlQuery("SELECT * FROM RouteListing WHERE stopID = :1", stop.stopID)
            route = q.get()
            if route is None:
                logging.error("IMPOSSIBLE... no stop on record?!? %s", stop.stopID)
            else:
                logging.debug("updating RouteListing with this stop... %s" % stop.key())
                route.stopLocation = stop
                route.put()

        return
    
## end
    
class RouteListHandler(webapp.RequestHandler):
    def get(self,routeID=""):
      logging.info("fetching all stop locations for route %s" % routeID)
      q = db.GqlQuery("SELECT * FROM RouteListing WHERE route = :1", routeID)
      if q is not None:
          results = []
          
          # Perform the query to get 500 results.
          stops = q.fetch(500)
          logging.info("running through stop location list....")
          for s in stops:
              logging.debug("fetch route list details for stop %s" % s.stopID)
              try:
                  sLocation = s.stopLocation
              except datastore_errors.Error,e:
                  if e.args[0] == "ReferenceProperty failed to be resolved":
                      sLocation = None
                  else:
                      raise
                  
              results.append({'stopID':s.stopID,
                              'location':sLocation if sLocation is not None else 'unknown',
                              'intersection':sLocation.intersection if sLocation is not None else 'unknown',
                              'direction':sLocation.direction if sLocation is not None else 'unknown',
                              'routeID':routeID,
                              })
              
              
      # add the counter to the template values
      template_values = {'stops':results}
        
      # create a page that provides a form for sending an SMS message
      path = os.path.join(os.path.dirname(__file__), 'stop.html')
      self.response.out.write(template.render(path,template_values))

    
## end

## end ScrapeRouteStopHandler
def main():
  logging.getLogger().setLevel(logging.DEBUG)
  application = webapp.WSGIApplication([('/configure', CrawlerHandler),
                                        ('/configuregeo', CrawlGeoHandler),
                                        ('/crawlingtask', CrawlingTaskHandler),
                                        ('/crawlinggeotask', CrawlingGeoTaskHandler),
                                        ('/storethestop', StopStorageHandler),
                                        ('/routelist/(.*)', RouteListHandler),
                                        ('/droptable/(.*)', DropTableHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()

