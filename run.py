"""Development entry point:  python run.py"""
import os

from interviewiq import create_app

app = create_app()

if __name__ == "__main__":
    # debug is opt-in: the Werkzeug debugger must never be exposed on a shared network
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
