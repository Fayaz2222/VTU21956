# src/utils.py
import shortuuid # Install with: pip install shortuuid
from datetime import datetime, timedelta
import re
import os
import logging
from dotenv import load_dotenv

load_dotenv() # Load environment variables

# Configure logging for utilities
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler(os.getenv('LOG_FILE_PATH', 'app.log'))
file_handler.setFormatter(log_formatter)

utils_logger = logging.getLogger('utils')
utils_logger.setLevel(logging.INFO)
utils_logger.addHandler(file_handler)
utils_logger.propagate = False # Prevent logs from going to root logger/console by default

def generate_short_code(length=7):
    """Generates a unique alphanumeric short code."""
    # shortuuid generates unique, URL-safe IDs by default
    return shortuuid.uuid()[:length]

def is_valid_url(url):
    """Checks if a string is a valid URL."""
    # A more robust regex for URL validation
    regex = re.compile(
        r'^(?:http|ftp)s?://' # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' # domain...
        r'localhost|' # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
        r'(?::\d+)?' # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return re.match(regex, url) is not None

def calculate_expiry(minutes):
    """Calculates the expiry datetime based on given minutes from now (UTC)."""
    return datetime.utcnow() + timedelta(minutes=minutes)

def get_client_ip(request):
    """Extracts client IP address from Flask request."""
    # Prioritize 'X-Forwarded-For' for proxy compatibility
    if 'X-Forwarded-For' in request.headers:
        return request.headers['X-Forwarded-For'].split(',')[0].strip()
    return request.remote_addr # Fallback to direct connection IP

def get_geolocation(ip_address):
    """
    Retrieves coarse-grained geographical location from an IP address.
    This is a mocked implementation for simplicity, as real GeoIP requires external databases.
    """
    if not ip_address:
        utils_logger.warning("No IP address provided for geolocation.")
        return {'country': 'Unknown', 'region': 'Unknown', 'city': 'Unknown'}

    # Using the current location (Kadapa, Andhra Pradesh, India) as the mock location
    return {'country': 'India', 'region': 'Andhra Pradesh', 'city': 'Kadapa'}