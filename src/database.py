# src/database.py
import sqlite3
import logging
import os
from dotenv import load_dotenv

load_dotenv() # Load environment variables

# Configure logging for database operations
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler(os.getenv('LOG_FILE_PATH', 'app.log'))
file_handler.setFormatter(log_formatter)

db_logger = logging.getLogger('database')
db_logger.setLevel(logging.INFO)
db_logger.addHandler(file_handler)
db_logger.propagate = False # Prevent logs from going to root logger/console by default

DATABASE_PATH = os.getenv('DATABASE_PATH', './url_shortener.db')

def init_db():
    """Initializes the SQLite database, creating tables if they don't exist."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Create urls table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_url TEXT NOT NULL,
            short_code TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    ''')

    # Create clicks table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_id INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            referrer TEXT,
            ip_address TEXT,
            country TEXT,
            region TEXT,
            city TEXT,
            FOREIGN KEY (url_id) REFERENCES urls (id)
        )
    ''')
    conn.commit()
    conn.close()
    db_logger.info("Database initialized successfully.")

def get_db_connection():
    """Returns a new SQLite database connection."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row # This allows accessing columns by name
    return conn

if __name__ == '__main__':
    # This block runs only when database.py is executed directly
    init_db()