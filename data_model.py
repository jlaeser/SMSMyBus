from google.appengine.ext import db


class PhoneLog(db.Model):
  phone = db.StringProperty()
  date = db.DateTimeProperty(auto_now_add=True)
  body = db.StringProperty(multiline=True)
  smsID = db.StringProperty()
  outboundSMS = db.StringProperty(multiline=True)
## end phoneLog

class RouteListing(db.Model):
    route = db.StringProperty()
    direction = db.StringProperty()
    stopID = db.StringProperty()
    scheduleURL = db.StringProperty()
## end RouteListing

class DestinationListing(db.Model):
    id = db.StringProperty()
    label = db.StringProperty()
## end DestinationListing

class BusStopAggregation(db.Model):
    dateAdded = db.DateTimeProperty(auto_now_add=True)
    routeID = db.StringProperty()
    stopID = db.StringProperty()
    time = db.IntegerProperty()
    text = db.StringProperty(multiline=True)
    sid = db.StringProperty()
## end BusStopAggregation
    
