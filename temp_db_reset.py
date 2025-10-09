import logging
from dotenv import load_dotenv

# Load environment variables from .env file before importing other modules
load_dotenv()

from app import models
from app.database import engine, Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_database():
    logger.info("Connecting to the database to reset the schema.")
    try:
        logger.info("Dropping all existing tables...")
        Base.metadata.drop_all(bind=engine)
        logger.info("Tables dropped successfully.")

        logger.info("Creating all tables based on the current models...")
        Base.metadata.create_all(bind=engine)
        logger.info("Tables created successfully.")

        logger.info("Database schema has been successfully reset.")
    except Exception as e:
        logger.error(f"An error occurred during database reset: {e}")
        raise

if __name__ == "__main__":
    reset_database()