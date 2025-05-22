from app.app import app
from app.db import init_db
import webbrowser

if __name__ == "__main__":
    # Ensure the SQLite file & schema exist
    init_db()

    # Pop open the browser
    webbrowser.open("http://127.0.0.1:8888")

    # Run Flask (no debug so it won't spawn a second process)
    app.run(port=8888, debug=False)
