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

