import logging
from google.appengine.api import mail

class Dummy():
    return

def sendEmailResponse(email, textBody):
    
    header = "Thanks for your request! Here are your results...\n\n"             
    footer = "\n\nThank you for using SMSMyBus!\nhttp://www.smsmybus.com"
      
    logging.debug("Sending outbound email to %s with message %s" % (email,textBody))
    
    # setup the response email
    message = mail.EmailMessage()
    message.sender = 'request@smsmybus.com'
    message.bcc = 'gtracy@gmail.com'
    message.to = email
    message.subject = 'Your Metro schedule estimates'
    message.body = header + textBody + footer
    message.send()

## end sendEmailResponse()

