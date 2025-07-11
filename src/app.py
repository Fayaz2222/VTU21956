# src/app.py
import os
import logging
import re
from datetime import datetime
from flask import Flask, request, jsonify, redirect, g
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import local modules
from src.database import init_db, get_db_connection
from src.utils import generate_short_code, is_valid_url, calculate_expiry, get_client_ip, get_geolocation

app = Flask(__name__)

# --- Logging Configuration for Flask App ---
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')

# File handler
file_handler = logging.FileHandler(os.getenv('LOG_FILE_PATH', 'app.log'))
file_handler.setFormatter(log_formatter)

# Console handler (useful for development)
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

# Get the Flask app's logger and add handlers
app.logger.setLevel(logging.INFO) # Set overall logging level for the app
app.logger.addHandler(file_handler)
app.logger.addHandler(console_handler) # Add console handler

# --- Database Connection Management ---
@app.before_request
def before_request():
    """Establishes a database connection before each request."""
    g.db = get_db_connection()

@app.teardown_request
def teardown_request(exception):
    """Closes the database connection after each request."""
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()

# Initialize the database when the app starts
with app.app_context():
    init_db()

# --- API Endpoints ---

@app.route('/shorturls', methods=['POST'])
def create_short_url():
    """
    Creates a new shortened URL.
    Expects JSON body with 'url', optional 'validity' (minutes), and optional 'shortcode'.
    """
    data = request.get_json()
    original_url = data.get('url')
    validity_minutes = data.get('validity')
    custom_shortcode = data.get('shortcode')

    # 1. Input Validation
    if not original_url or not is_valid_url(original_url):
        app.logger.error(f"Validation Error: Invalid or missing URL in request: {original_url}")
        return jsonify({"error": "Invalid or missing URL"}), 400

    # 2. Determine expiry date
    expiry_minutes = validity_minutes if isinstance(validity_minutes, int) and validity_minutes > 0 else 30
    expires_at = calculate_expiry(expiry_minutes)

    cursor = g.db.cursor()
    final_shortcode = None

    if custom_shortcode:
        # 3. Handle custom shortcode
        # Basic alphanumeric and hyphen/underscore check, length between 4 and 20 for example
        if not re.match(r'^[a-zA-Z0-9_-]{4,20}$', custom_shortcode):
            app.logger.error(f"Validation Error: Invalid custom shortcode format: {custom_shortcode}")
            return jsonify({"error": "Invalid custom shortcode format. Must be alphanumeric (4-20 chars) and can include _ or -"}), 400

        # Check for uniqueness
        cursor.execute("SELECT id FROM urls WHERE short_code = ?", (custom_shortcode,))
        if cursor.fetchone():
            app.logger.warning(f"Conflict: Custom shortcode '{custom_shortcode}' already in use.")
            return jsonify({"error": "Custom shortcode already in use. Please choose another or omit to auto-generate."}), 409
        final_shortcode = custom_shortcode
    else:
        # 4. Auto-generate unique shortcode
        while True:
            generated_code = generate_short_code()
            cursor.execute("SELECT id FROM urls WHERE short_code = ?", (generated_code,))
            if not cursor.fetchone():
                final_shortcode = generated_code
                break

    # 5. Store in database
    try:
        created_at = datetime.utcnow()
        cursor.execute(
            "INSERT INTO urls (original_url, short_code, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (original_url, final_shortcode, created_at.isoformat(), expires_at.isoformat())
        )
        g.db.commit()
        app.logger.info(f"Short URL created successfully: '{final_shortcode}' for '{original_url}'")

        short_link = f"{os.getenv('BASE_URL')}/{final_shortcode}"
        return jsonify({
            "shortLink": short_link,
            "expiry": expires_at.isoformat() + "Z" # Append Z for UTC as per ISO 8601
        }), 201
    except sqlite3.Error as e:
        app.logger.error(f"Database Error: Failed to create short URL for '{original_url}': {e}", exc_info=True)
        return jsonify({"error": "Internal server error occurred while creating short URL"}), 500

@app.route('/shorturls/<shortcode>', methods=['GET'])
def get_short_url_stats(shortcode):
    """
    Retrieves statistics for a given short URL.
    """
    cursor = g.db.cursor()
    cursor.execute("SELECT id, original_url, created_at, expires_at FROM urls WHERE short_code = ?", (shortcode,))
    url_entry = cursor.fetchone()

    if not url_entry:
        app.logger.warning(f"Not Found: Statistics requested for non-existent shortcode: {shortcode}")
        return jsonify({"error": "Short URL not found."}), 404

    url_id = url_entry['id']
    cursor.execute("SELECT timestamp, referrer, ip_address, country, region, city FROM clicks WHERE url_id = ?", (url_id,))
    clicks = cursor.fetchall()

    click_details = []
    for click in clicks:
        click_details.append({
            "timestamp": click['timestamp'] + "Z", # Append Z for UTC
            "referrer": click['referrer'],
            "ipAddress": click['ip_address'],
            "location": {
                "country": click['country'],
                "region": click['region'],
                "city": click['city']
            }
        })

    app.logger.info(f"Statistics retrieved for shortcode: {shortcode}")
    return jsonify({
        "originalUrl": url_entry['original_url'],
        "creationDate": url_entry['created_at'] + "Z",
        "expiryDate": url_entry['expires_at'] + "Z",
        "totalClicks": len(clicks),
        "clickDetails": click_details
    }), 200

@app.route('/<shortcode>', methods=['GET'])
def redirect_short_url(shortcode):
    """
    Redirects the user to the original URL and records the click.
    """
    cursor = g.db.cursor()
    cursor.execute("SELECT id, original_url, expires_at FROM urls WHERE short_code = ?", (shortcode,))
    url_entry = cursor.fetchone()

    if not url_entry:
        app.logger.warning(f"Not Found: Attempted redirection for non-existent shortcode: {shortcode}")
        return jsonify({"error": "Short URL not found."}), 404

    expires_at_dt = datetime.fromisoformat(url_entry['expires_at'])
    if expires_at_dt < datetime.utcnow():
        app.logger.warning(f"Gone: Attempted redirection for expired shortcode: {shortcode}")
        return jsonify({"error": "Short URL has expired."}), 410

    # Record click
    url_id = url_entry['id']
    client_ip = get_client_ip(request)
    geolocation_data = get_geolocation(client_ip)
    referrer = request.referrer if request.referrer else 'Direct'
    timestamp = datetime.utcnow().isoformat()

    try:
        cursor.execute(
            "INSERT INTO clicks (url_id, timestamp, referrer, ip_address, country, region, city) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (url_id, timestamp, referrer, client_ip, geolocation_data['country'], geolocation_data['region'], geolocation_data['city'])
        )
        g.db.commit()
        app.logger.info(f"Redirecting shortcode '{shortcode}' to '{url_entry['original_url']}'. Click recorded.")
    except sqlite3.Error as e:
        app.logger.error(f"Database Error: Failed to record click for '{shortcode}': {e}", exc_info=True)
        # Continue with redirection even if click logging fails

    return redirect(url_entry['original_url'])

# --- Custom Error Handlers ---
@app.errorhandler(404)
def not_found_error(error):
    """Handles 404 Not Found errors."""
    app.logger.warning(f"404 Not Found: Requested path: {request.path}")
    return jsonify({"error": "Not Found"}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handles 500 Internal Server Errors."""
    # Log the full traceback for unhandled exceptions
    app.logger.critical(f"500 Internal Server Error: Requested path: {request.path}", exc_info=True)
    return jsonify({"error": "Internal Server Error"}), 500

if __name__ == '__main__':
    # Run the Flask app
    # Set debug=False for production environments
    app.run(debug=False, port=int(os.getenv('PORT', 5000)))