import wsgiref.handlers
import logging
import re

from google.appengine.api import quota
from google.appengine.api import urlfetch
from google.appengine.api import memcache
from google.appengine.api.urlfetch import DownloadError
from google.appengine.api.labs import taskqueue
from google.appengine.api.labs.taskqueue import Task
from google.appengine.ext import webapp
from google.appengine.ext import db

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
        task = Task(url='/crawlingtask', params={'crawl':crawlURL,})
        task.add('crawler')
        logging.info("Added new task for %s" % crawlURL)        
        return
    
## end CrawlerHandler()
        
class CrawlingTaskHandler(webapp.RequestHandler):
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
                        # we finally got down to the page we're looking for
                        
                        # pull the stopID from the page content...
                        stopID = title.split("ID#")[1].split("]")[0]
                        
                        # pull the intersection from the page content...
                        intersection = title.split("[")[0].strip()
                        
                        logging.info("found stop %s, %s" % (stopID,intersection))
                        
                        # check for conflicts...
                        q = db.GqlQuery("SELECT * FROM StopLocation WHERE stopID = :1", stopID)
                        stopQuery = q.fetch(1)
                        if len(stopQuery) == 0:
                            # add the new stop
                            stop = StopLocation()
                            stop.stopID = stopID
                            stop.intersection = intersection
                            stop.put()
                            logging.info("adde new stop listing MINUS geo location")
                        
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
                    else: # title.split(",")[0].isdigit():
                        # create a new task with this link
                        crawlURL = CRAWL_URLBASE + href
                        task = Task(url='/crawlingtask', params={'crawl':crawlURL,})
                        task.add('crawler')
                        logging.info("Added new task for %s" % title.split(",")[0])                    # label crawler looks for titles with letters for extraction/persistence
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

            if result.content[0] == '5':
                # parser for the geo stop data...
                stops = result.content.split('<br>')
                for s in stops:
                    #logging.info("Parsing... %s" % s)
                    if s[0] == '|':
                        data = re.search('\|\d+;.*?(4.*?)\|(.*?)\|(.*?)\[ID#(\d+)\]\|(.*?)\|',s)
                        if data is not None:
                            latitude = data.group(1)
                            longitude = data.group(2)
                            intersection = data.group(3)
                            stopID = data.group(4)
                            direction = data.group(5)
                            #logging.info("LAT: %s" % latitude)
                            #logging.info("LONG: %s" % longitude)
                            #logging.info("Intersection: %s" % intersection)
                            #logging.info("Stop ID: %s" % stopID)
                            #ogging.info("direction: %s" % direction)
                            q = db.GqlQuery("SELECT * FROM StopLocation WHERE stopID = :1", stopID)
                            stop = q.get()
                            if stop is None:
                                logging.error("We DON'T already have this stop in the store!?!")
                            else:
                                stop.location = (latitude+","+longitude)
                                stop.update_location()
                                stop.direction = direction
                                stop.put()
                                #logging.info("GEO DATA ADDED for %s" % intersection)
                                
                                # update the route table to include a reference to the new geo data
                                #q = db.GqlQuery("SELECT * FROM RouteListing WHERE stopID = :1", stopID)
                                #route = q.get()
                                #if route is None:
                                #    logging.error("IMPOSSIBLE... no stop on record?!? %s", stopID)
                                #else:
                                #    route.stopLocation = stop
                                #    route.put()
                                
                        else:
                            logging.debug("Nothing found?!")
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
                    else: 
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
        qstring = "select __key__ from " + table
        logging.info("query string is... %s" % qstring)
        q = db.GqlQuery(qstring)
        results = q.fetch(500)
        while results:
            db.delete(results)
            results = fetch(500, len(results))

## end
    
## end ScrapeRouteStopHandler
def main():
  logging.getLogger().setLevel(logging.INFO)
  application = webapp.WSGIApplication([('/configure', CrawlerHandler),
                                        ('/configuregeo', CrawlGeoHandler),
                                        ('/crawlingtask', CrawlingTaskHandler),
                                        ('/crawlinggeotask', CrawlingGeoTaskHandler),
                                        ('/droptable/(.*)', DropTableHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()

