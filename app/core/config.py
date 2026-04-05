import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        raise ValueError("DATABASE_URL is missing from the environment")

settings = Settings()
