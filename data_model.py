from google.appengine.ext import db
from geo.geomodel import GeoModel

class Purchase(db.Model):
  '''a completed transaction'''
  purchaser = db.StringProperty()
  created = db.DateTimeProperty(auto_now_add=True)
  status = db.StringProperty( choices=( 'NEW', 'CREATED', 'ERROR', 'CANCELLED', 'RETURNED', 'COMPLETED' ) )
  status_detail = db.StringProperty()
  secret = db.StringProperty() # to verify return_url
  debug_request = db.TextProperty()
  debug_response = db.TextProperty()
  paykey = db.StringProperty()

class SMSUser(db.Model):
  phone         = db.StringProperty()
  purchase      = db.ReferenceProperty(Purchase)
  creation_date = db.DateTimeProperty(auto_now_add=True)
## end SMSUser

class PhoneLog(db.Model):
  phone       = db.StringProperty()
  date        = db.DateTimeProperty(auto_now_add=True)
  body        = db.StringProperty(multiline=True)
  smsID       = db.StringProperty()
  outboundSMS = db.StringProperty(multiline=True)
## end phoneLog

# note that a stop extends GeoModel   
class StopLocation(GeoModel):
    stopID       = db.StringProperty()
    routeID      = db.StringProperty()
    intersection = db.StringProperty()
    direction    = db.StringProperty()
## end StopLocation    


class RouteListing(db.Model):
    route        = db.StringProperty()
    direction    = db.StringProperty()
    stopID       = db.StringProperty()
    scheduleURL  = db.StringProperty()
    stopLocation = db.ReferenceProperty(StopLocation,collection_name="stops")    
## end RouteListing

class DestinationListing(db.Model):
    id    = db.StringProperty()
    label = db.StringProperty()
## end DestinationListing

class BusStopAggregation(db.Model):
    dateAdded   = db.DateTimeProperty(auto_now_add=True)
    routeID     = db.StringProperty()
    stopID      = db.StringProperty()
    destination = db.StringProperty()
    arrivalTime = db.StringProperty()
    time        = db.IntegerProperty()
    text        = db.StringProperty(multiline=True)
    sid         = db.StringProperty()
## end BusStopAggregation

class LiveRouteStatus(db.Model):
    dateAdded    = db.DateTimeProperty(auto_now_add=True)
    routeToken   = db.StringProperty()
    routeID      = db.StringProperty()
    stopID       = db.StringProperty()
    arrivalTime  = db.StringProperty()
    time         = db.IntegerProperty()
    intersection = db.StringProperty()
    destination  = db.StringProperty()
    routeQualifier = db.StringProperty()
    stopLocation = db.ReferenceProperty(StopLocation,collection_name="liveroutes")
## end LiveRouteStatus

class LiveVehicleStatus(db.Model):
    dateAdded    = db.DateTimeProperty(auto_now_add=True)
    routeID      = db.StringProperty()
    vehicleID    = db.StringProperty()
    location     = db.GeoPtProperty()
    destination  = db.StringProperty()
    nextTimepoint= db.StringProperty()
## end LiveVehicleStatus

class DeveloperKeys(db.Model):
    dateAdded      = db.DateTimeProperty(auto_now_add=True)
    developerName  = db.StringProperty()
    developerKey   = db.StringProperty()
    developerEmail = db.EmailProperty()
    requestCounter = db.IntegerProperty()
    errorCounter   = db.IntegerProperty()
## end DeveloperKeys

class DeveloperRequest(db.Model):
    developer     = db.ReferenceProperty()
    date          = db.DateTimeProperty(auto_now_add=True)
    type          = db.StringProperty()
    error         = db.StringProperty()
    requestTerms  = db.StringProperty()
    remoteAddr    = db.StringProperty()
## end DeveloperRequest

class ParseErrors(db.Model):
    dateAdded = db.DateTimeProperty(auto_now_add=True)
    intersection = db.StringProperty()
    location = db.GeoPtProperty()
    direction = db.StringProperty()
    routeID = db.StringProperty()
    stopID = db.StringProperty()
    metaStringOne = db.TextProperty()
    metaStringTwo = db.TextProperty()
    reviewed = db.BooleanProperty()
## end ParseErrors
    