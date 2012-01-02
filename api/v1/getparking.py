import os
import wsgiref.handlers
import logging
import time

from google.appengine.ext import webapp
from google.appengine.api import urlfetch
from google.appengine.ext.webapp.util import run_wsgi_app

from BeautifulSoup import BeautifulSoup, Tag

from django.utils import simplejson

from api.v1 import utils


class MainHandler(webapp.RequestHandler):
    # POST not support by the API
    def post(self):
        self.response.headers['Content-Type'] = 'application/javascript'
        self.response.out.write(simplejson.dumps(utils.buildErrorResponse('-1','The API does not support POST requests')))
        return
    
    def get(self):
      
        loop = 0
        done = False
        result = None
        while not done and loop < 3:
            try:
              result = urlfetch.fetch('http://www.cityofmadison.com/parkingUtility/garagesLots/availability/')
              done = True;
            except urlfetch.DownloadError:
              logging.error("Error loading page (%s)... sleeping" % loop)
              if result:
                logging.debug("Error status: %s" % result.status_code)
                logging.debug("Error header: %s" % result.headers)
                logging.debug("Error content: %s" % result.content)
              time.sleep(6)
              loop = loop+1
           
        if result is None or result.status_code != 200:
            logging.error("Exiting early: error fetching URL: " + result.status_code)
            return 
     
        soup = BeautifulSoup(result.content)
        json_response = []
        getLots(soup, json_response, "dataRow rowShade");
        getLots(soup, json_response, "dataRow");
        for lot in json_response:
            logging.debug('lot... %s' % lot)
            logging.debug('... name %s' % lot['name'])
            if lot['name'] == 'Brayton Lot':
                lot['address'] = '1 South Butler St.'
                lot['total_spots'] = '243'
                #lot['url'] = 'http://www.cityofmadison.com/parkingUtility/garagesLots/facilities/brayton.cfm'
            elif lot['name'] == 'Capitol Square North Garage':
                lot['address'] = '218 East Mifflin St.'
                lot['total_spots'] = '613'
                #lot['url'] = 'http://www.cityofmadison.com/parkingUtility/garagesLots/facilities/capSquareNorth.cfm'
            elif lot['name'] == 'Government East Garage':
                lot['address'] = '215 S. Pinckney St.'
                lot['total_spots'] = '516'
                #lot['url'] = 'http://www.cityofmadison.com/parkingUtility/garagesLots/facilities/govtEast.cfm'
            elif lot['name'] == 'Overture Center Garage':
                lot['address'] = '318 W. Mifflin St.'
                lot['total_spots'] = '620'
                #lot['url'] = 'http://www.cityofmadison.com/parkingUtility/garagesLots/facilities/overture.cfm'
            elif lot['name'] == 'State Street Campus Garage':
                lot['address'] = ['430 N. Frances St.','415 N. Lake St.']
                lot['total_spots'] = '1066'
                #lot['url'] = 'http://www.cityofmadison.com/parkingUtility/garagesLots/facilities/stateStCampus.cfm'
            elif lot['name'] == 'State Street Capitol Garage':
                lot['address'] = '214 N. Carroll St.'
                lot['total_spots'] = '855'
                #lot['url'] = 'http://www.cityofmadison.com/parkingUtility/garagesLots/facilities/stateStCapitol.cfm'
					
        # encapsulate response in json or jsonp
        logging.debug('API: json response %s' % json_response)

        callback = self.request.get('callback')
        if callback is not '':
            self.response.headers['Content-Type'] = 'application/javascript'
            self.response.headers['Access-Control-Allow-Origin'] = '*'
            self.response.headers['Access-Control-Allow-Methods'] = 'GET'
            response = callback + '(' + simplejson.dumps(json_response) + ');'
        else:
            self.response.headers['Content-Type'] = 'application/json'
            response = simplejson.dumps(json_response)
      
        self.response.out.write(response)

## end RequestHandler

def getLots(soup, response, class_name):
    results = []
    for lot in soup.html.body.findAll("div",{"class":class_name}):
        #logging.debug('lot... %s' % lot);
        #logging.debug('lot.div.a ... %s' % lot.div.a.string)
        for detail in lot:
            if detail.string is not None and detail.string.isdigit():
                #logging.debug('DIGIT %s' % detail.string)
                lot_spots = detail.string

        lot_details = {
            'name' : lot.div.a.string,
            'open_spots' : lot_spots
        }
        response.append(lot_details)

## end

application = webapp.WSGIApplication([('/api/v1/getparking', MainHandler),
                                      ],
                                     debug=True)

def main():
  logging.getLogger().setLevel(logging.DEBUG)
  run_wsgi_app(application)
  #wsgiref.handlers.CGIHandler().run(application)

if __name__ == '__main__':
  main()
