# settings for app

PAYPAL_ENDPOINT = 'https://svcs.sandbox.paypal.com/AdaptivePayments/' # sandbox
#PAYPAL_ENDPOINT = 'https://svcs.paypal.com/AdaptivePayments/' # production

PAYPAL_PAYMENT_HOST = 'https://www.sandbox.paypal.com/au/cgi-bin/webscr' # sandbox
#PAYPAL_PAYMENT_HOST = 'https://www.paypal.com/webscr' # production

PAYPAL_USERID = 'gtracy_1305234860_biz_api1.gmail.com'
PAYPAL_PASSWORD = '1305234887'
PAYPAL_SIGNATURE = 'AkT6FJDw.KbViLJU2i4bL4Nj-EErA10Br4EMPY65MaPf71ygHtflhjRi'
PAYPAL_APPLICATION_ID = 'APP-80W284485P519543T' # sandbox only
PAYPAL_EMAIL = 'gtracy_1305234860_biz@gmail.com'

#PAYPAL_USERID = 'greg.tracy_api1.softgrove.com'
#PAYPAL_PASSWORD = 'S55ZRMRAFRTG7SZ5'
#PAYPAL_SIGNATURE = 'A8oP5BrqlRppZRisG5JJJbzs5V4bAcBPk0rxqJFVZSJKoMbKslAss-3l'
#PAYPAL_APPLICATION_ID = 'APP-80W284485P519543T' # sandbox only
#PAYPAL_EMAIL = 'greg.tracy@softgrove.com'

PAYPAL_COMMISSION = 0.2 # 20%

USE_CHAIN = False
USE_IPN = False
USE_EMBEDDED = False
SHIPPING = False # not yet working properly; PayPal bug

# EMBEDDED_ENDPOINT = 'https://paypal.com/webapps/adaptivepayment/flow/pay'
EMBEDDED_ENDPOINT = 'https://www.sandbox.paypal.com/webapps/adaptivepayment/flow/pay'