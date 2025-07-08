from dotenv import load_dotenv, find_dotenv
# this finds and loads your .env file
load_dotenv(find_dotenv())

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)