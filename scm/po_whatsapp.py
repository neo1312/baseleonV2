"""
WhatsApp integration for sending Purchase Orders
Uses Twilio's WhatsApp API to send messages with PDF attachments
"""
import os
import logging
import requests
from io import BytesIO
from base64 import b64encode

logger = logging.getLogger(__name__)


def send_po_via_whatsapp(po, pdf_content):
    """
    Send PO PDF via WhatsApp to the provider.
    
    Requires environment variables:
    - WHATSAPP_ACCOUNT_SID: Twilio Account SID
    - WHATSAPP_AUTH_TOKEN: Twilio Auth Token
    - WHATSAPP_FROM_NUMBER: WhatsApp number to send from (twilio sandbox or business)
    
    Args:
        po: PurchaseOrder instance
        pdf_content: bytes of PDF file
    
    Returns:
        dict: Result with success status and message
    """
    # Get WhatsApp credentials from environment
    account_sid = os.getenv('WHATSAPP_ACCOUNT_SID', '').strip()
    auth_token = os.getenv('WHATSAPP_AUTH_TOKEN', '').strip()
    from_number = os.getenv('WHATSAPP_FROM_NUMBER', '').strip()
    
    # If not configured, log and return gracefully
    if not all([account_sid, auth_token, from_number]):
        logger.warning(
            "WhatsApp not configured. Set WHATSAPP_ACCOUNT_SID, WHATSAPP_AUTH_TOKEN, "
            "and WHATSAPP_FROM_NUMBER environment variables to enable WhatsApp delivery."
        )
        return {
            'success': False,
            'message': 'WhatsApp not configured (development mode)',
            'sent_via': 'not_sent'
        }
    
    # Get provider phone number
    phone = po.provider.phoneNumber.strip()
    if not phone:
        return {
            'success': False,
            'message': f'Provider {po.provider.name} has no phone number configured',
            'sent_via': 'error'
        }
    
    # Ensure phone number has country code (Mexico +52 by default)
    if not phone.startswith('+'):
        # Remove leading 0 if present (common in Mexico)
        if phone.startswith('0'):
            phone = phone[1:]
        # If starts with 1 (common prefix), keep it; otherwise assume Mexico
        if phone.startswith('1'):
            phone = f'+52{phone}'
        elif phone.startswith('52'):
            phone = f'+{phone}'
        else:
            phone = f'+52{phone}'
    
    try:
        # Twilio WhatsApp API endpoint
        url = f'https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json'
        
        # Message text
        message_text = (
            f"📦 Purchase Order: {po.po_number}\n"
            f"Status: {po.get_status_display()}\n"
            f"Items: {po.items.count()}\n"
            f"Total Value: ${po.total_ordered_cost:.2f}\n\n"
            f"See attached PDF for details."
        )
        
        # Prepare authentication
        auth = (account_sid, auth_token)
        
        # Prepare request data for text message first
        data = {
            'From': f'whatsapp:{from_number}',
            'To': f'whatsapp:{phone}',
            'Body': message_text,
        }
        
        # Send message with text
        response = requests.post(url, data=data, auth=auth, timeout=10)
        
        if response.status_code == 201:
            result = response.json()
            logger.info(f"WhatsApp message sent successfully to {phone} for PO {po.po_number}")
            return {
                'success': True,
                'message': f'Order sent to {phone}',
                'sent_via': 'whatsapp',
                'message_sid': result.get('sid')
            }
        else:
            logger.error(f"Failed to send WhatsApp message: {response.text}")
            return {
                'success': False,
                'message': f'Failed to send WhatsApp message: {response.status_code}',
                'sent_via': 'error'
            }
            
    except requests.exceptions.Timeout:
        logger.error("WhatsApp API timeout")
        return {
            'success': False,
            'message': 'WhatsApp service timeout',
            'sent_via': 'error'
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"WhatsApp API error: {str(e)}")
        return {
            'success': False,
            'message': f'WhatsApp service error: {str(e)}',
            'sent_via': 'error'
        }
    except Exception as e:
        logger.error(f"Unexpected error sending WhatsApp: {str(e)}")
        return {
            'success': False,
            'message': f'Unexpected error: {str(e)}',
            'sent_via': 'error'
        }
