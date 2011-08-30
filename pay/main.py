import cgi
import decimal
import logging
import os
import random
import string

from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import login_required
from google.appengine.ext.webapp.util import run_wsgi_app

from pay import paypal
from pay import settings

from data_model import Purchase

# hack to enable urllib to work with Python 2.6
import os
os.environ['foo_proxy'] = 'bar'
import urllib
urllib.getproxies_macosx_sysconf = lambda: {}

class RequestHandler(webapp.RequestHandler):
  def error( self, code ):
    webapp.RequestHandler.error( self, code )
    if code >= 500 and code <= 599:
      path = os.path.join(os.path.dirname(__file__), 'templates/50x.htm')
      self.response.out.write(template.render(path, {}))
    if code == 404:
      path = os.path.join(os.path.dirname(__file__), 'templates/404.htm')
      self.response.out.write(template.render(path, {}))

class Home(RequestHandler):
  def post(self):
    self.get()
  def get(self):
    # @todo get the user from the phone number. if it doesn't exist, create one
    phone = self.request.get('phone')
    purchase = Purchase(purchaser='phone', status='NEW', secret=random_alnum(16) )
    purchase.put()

    pay = paypal.Pay( 
      10.00, 
      "%s/return/%s/%s/%s/" % (self.request.uri, phone, purchase.key(), purchase.secret), 
      "%s/cancel/%s/%s/" % (self.request.uri, phone, purchase.key()), 
      self.request.remote_addr)

    data = {
      'paykey': pay.paykey(),
      'phone':phone,
    }
    path = os.path.join(os.path.dirname(__file__), 'templates/main.htm')
    self.response.out.write(template.render(path, data))


class Buy(RequestHandler):
  @login_required
  def get(self, key):
    data = { 'item': 'fixme' }
    util.add_user( self.request.uri, data )
    if settings.USE_EMBEDDED:
      (ok, pay) = self.start_purchase( item )
      data['endpoint'] = settings.EMBEDDED_ENDPOINT
      data['paykey'] = pay.paykey()
      path = os.path.join(os.path.dirname(__file__), 'buy_embedded.htm')
    else:
      path = os.path.join(os.path.dirname(__file__), 'buy.htm')
    self.response.out.write(template.render(path, data))

  def post(self):
    phone = self.request.get('phone')
    coupon = self.request.get('coupon')
    (ok, pay) = self.start_purchase(phone,coupon)
    if ok:
      self.redirect( pay.next_url() ) # go to paypal
    else:
      data = {
        'item': 'fixme',
        'message': 'An error occurred during the purchase process'
      }
      util.add_user( self.request.uri, data )
      path = os.path.join(os.path.dirname(__file__), 'templates/buy.htm')
      self.response.out.write(template.render(path, data))

  def start_purchase(self, item):
    purchase = Purchase( purchaser=phone, status='NEW', secret=random_alnum(16) )
    purchase.put()
    if settings.USE_IPN:
      ipn_url = "%s/ipn/%s/%s/" % ( self.request.host_url, purchase.key(), purchase.secret )
    else:
      ipn_url = None
    if settings.USE_CHAIN:
      seller_paypal_email = util.paypal_email(item.owner)
    else:
      seller_paypal_email = None
    pay = paypal.Pay( 
      item.price_dollars(), 
      "%spay/buy/%s/%s/" % (self.request.uri, purchase.key(), purchase.secret), 
      "%scancel/%s/" % (self.request.uri, purchase.key()), 
      self.request.remote_addr,
      seller_paypal_email,
      ipn_url,
      shipping=settings.SHIPPING)

    purchase.debug_request = pay.raw_request
    purchase.debug_response = pay.raw_response
    purchase.paykey = pay.paykey()
    purchase.put()
    
    if pay.status() == 'CREATED':
      purchase.status = 'CREATED'
      purchase.put()
      return (True, pay)
    else:
      purchase.status = 'ERROR'
      purchase.put()
      return (False, pay)

class BuyReturn(RequestHandler):

  def get(self, user_key, purchase_key, secret ):
    '''user arrives here after purchase'''
    purchase = Purchase.get( purchase_key )

    # validation
    if purchase == None: # no key
      self.error(404)

    elif purchase.status != 'CREATED' and purchase.status != 'COMPLETED':
      purchase.status_detail = 'Expected status to be CREATED or COMPLETED, not %s - duplicate transaction?' % purchase.status
      purchase.status = 'ERROR'
      purchase.put()
      self.error(501)

    elif secret != purchase.secret:
      purchase.status = 'ERROR'
      purchase.status_detail = 'BuyReturn secret "%s" did not match' % secret
      purchase.put()
      self.error(501)

    else:
      if purchase.status != 'COMPLETED':
        purchase.status = 'RETURNED'
        purchase.put()

      data = {
        'item': user_key, #model.User.get(user_key),
        'message': 'Purchased',
      }

      util.add_user( self.request.uri, data )
      
      path = os.path.join(os.path.dirname(__file__), 'templates/buy.htm')
      self.response.out.write(template.render(path, data))

class BuyCancel(RequestHandler):
  def get(self, item_key, purchase_key):
    logging.debug( "cancelled %s with %s" % ( item_key, purchase_key ) )
    purchase = Purchase.get( purchase_key )
    purchase.status = 'CANCELLED'
    purchase.put()
    data = {
      'item': 'fixme', #model.Item.get(item_key),
      'message': 'Purchase cancelled',
    }
    util.add_user( self.request.uri, data )
    path = os.path.join(os.path.dirname(__file__), 'templates/buy.htm')
    self.response.out.write(template.render(path, data))

class IPN (RequestHandler):

  def post(self, key, secret):
    '''incoming post from paypal'''
    logging.debug( "IPN received for %s" % key )
    ipn = paypal.IPN( self.request )
    if ipn.success():
      # request is paypal's
      purchase = Purchase.get( key )
      if secret != purchase.secret:
        purchase.status = 'ERROR'
        purchase.status_detail = 'IPN secret "%s" did not match' % secret
        purchase.put()
      # confirm amount
      elif purchase.item.price_decimal() != ipn.amount:
        purchase.status = 'ERROR'
        purchase.status_detail = "IPN amounts didn't match. Item price %f. Payment made %f" % ( purchase.item.price_dollars(), ipn.amount )
        purchase.put()
      else:
        purchase.status = 'COMPLETED'
        purchase.put()
    else:
      logging.info( "PayPal IPN verify failed: %s" % ipn.error )
      logging.debug( "Request was: %s" % self.request.body )


class NotFound (RequestHandler):
  def get(self):
    self.error(404)

def random_alnum( count ):
  chars = string.letters + string.digits
  result = ''
  for i in range(count):
    result += random.choice(chars)
  return result

application = webapp.WSGIApplication( [
    ('/pay', Home),
    ('/pay/return/(.*)/([^/]*)/([^/]*)/.*', BuyReturn),
    ('/pay/cancel/(.*)/([^/]*)/.*', BuyCancel),
    ('/pay/buy/', Buy),
    ('/ipn/(.*)/(.*)/', IPN),
    ('/.*', NotFound),
  ],
  debug=True)

def main():
  logging.getLogger().setLevel(logging.DEBUG)
  run_wsgi_app(application)

if __name__ == "__main__":
  main()