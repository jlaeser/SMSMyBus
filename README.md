SMSMyBus
========
This project is a civic hacking project that makes the Madison Metro bus system more accessible, 
easier to use, and make the entire riding experience more enjoyable.

http://www.smsmybus.com

The app is currently deployed on Google App Engine.

SMSMyBus Applications
---------------------
The original goal of this project was to provide access to real-time arrival estimates via a 
variety of mobile interfaces:

* SMS
* XMPP (Google Chat)
* Email
* Phone. 

These interfaces were built with brute force screen scraping of the Metro website.

Over time, the project evolved into an abstraction over those interfaces and general purpose web 
services were created for accessing schedule, route and location data.

SMSMyBus API
------------
This application provides access to a free, easy to use, JSON-based web service interface for 
Madison Metro service. Once you've received a developer token, you have access to the following
services:

* Real-time arrival estimates for every route at every stop in the city.
* A list of all stops in a specified route
* The geo-location of any stop in the city
* Search for stops near a specified geo-location
* A list of all routes in the system

http://www.smsmybus.com/api

### API Resources

There is a second repository that contains some example uses of the API

http://github.com/gtracy/smsmybus-dev

There is a Google Group used for developer discussion

http://groups.google.com/group/smsmybus-dev

Running Your Own Instance
-------------------------

You can deploy your own instance of SMSMyBus for testing or for
running your own version of the API, either on the Google infrastructure
or locally using the Python SDK dev_appserver. Before deploying,
copy config.py-sample to config.py and customize the settings to
your own email address, Twillio API keys, etc. If you are deploying
locally, not using the SMS features, and will not export statistics
to Google Docs, you may not need to change anything.

Deploy/run the application, and visit
http://baseurl/debug/create/newkey 

You will likely need to log in at that time. If running locally,
be sure to click on 'Sign in as administrator' to create the key.

That will create your first developer key, 'fixme'. You can go to 
the Datastore Viewer ( http://localhost:8080/_ah/admin/datastore ) 
and edit your new key.

Finally, you need to load route data. SMSMyBus crawls the Madison
Metro website to load route and stop data. It starts by inserting
a seed URL into an App Engine Task Queue. A background job pulls
that URL from the queue, fetches and parses the page, and recursively
discovers links to routes and stops, inserting those links back
into the queue. To start the crawl, visit:

http://localhost:8080/routelist/configure/ 

You should now be able to use the API as documented to fetch realtime
bus data, substituting your URL for smsmybus.com 

http://www.smsmybus.com/api
