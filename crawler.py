import logging

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
                logging.info("pulling out a timeslot from page... %s" % slot)

                if slot.has_key('href'):
                    href = slot['href']
                    title = slot['title']
                    logging.info("FOUND A TITLE ----> %s" % title)
                    # route crawler looks for titles with an ID# string
                    if title.find("[ID#") > 0:
                        # we finally got down to the page we're looking for
                        
                        # pull the stopID from the page content...
                        stopID = title.split("ID#")[1].split("]")[0]
                        
                        # pull the route and direction data from the URL
                        routeData = scrapeURL.split('?')[1]
                        logging.info("found the page! arguments: %s stopID: %s" % (routeData,stopID))
                        routeArgs = routeData.split('&')
                        routeID = routeArgs[0].split('=')[1]
                        directionID = routeArgs[1].split('=')[1]
                        timeEstimatesURL = CRAWL_URLBASE + href
                    
                        # check for conflicts...
                        q = db.GqlQuery("SELECT * FROM RouteListing WHERE route = :1 AND direction = :2 AND stopID = :3",
                                        routeID, directionID, stopID)
                        routeQuery = q.fetch(1)
                        if len(routeQuery) == 0:
                          # add the new route to the DB
                          route = RouteListing()
                          route.route = routeID
                          route.direction = directionID
                          route.stopID = stopID
                          route.scheduleURL = timeEstimatesURL
                          route.put()
                          logging.info("added new route listing entry to the database!")
                        else:
                          logging.error("we found a duplicate entry!?! %s", routeQuery[0].scheduleURL)
                    # route crawler creates new tasks for every non-matching page
                    # else: 
                    # label crawler only creates new tasks for the first level of the hierarchy 
                    else: # title.split(",")[0].isdigit():
                        # create a new task with this link
                        crawlURL = CRAWL_URLBASE + href
                        task = Task(url='/crawlingtask', params={'crawl':crawlURL,})
                        task.add('crawler')
                        logging.info("Added new task for %s" % title.split(",")[0])
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

