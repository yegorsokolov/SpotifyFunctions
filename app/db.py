import os, sys, sqlite3
from flask import g

# Determine where to put the DB file:
if getattr(sys, 'frozen', False):
    # running as a bundled .exe
    basedir = os.path.dirname(sys.executable)
else:
    # running normally
    basedir = os.path.abspath(os.path.dirname(__file__))

DB_PATH = os.path.join(basedir, 'Shrinker_App.db')

def get_db():
    """Return a sqlite3 connection stored on flask.g."""
    db = getattr(g, '_sqlite_db', None)
    if db is None:
        db = g._sqlite_db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    """If the DB file doesn’t exist, create it and all tables."""
    if not os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.executescript("""
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS Users (
          Id             INTEGER PRIMARY KEY AUTOINCREMENT,
          SpotifyUserId  TEXT    UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS Playlists (
          Id                  INTEGER PRIMARY KEY AUTOINCREMENT,
          SpotifyPlaylistId   TEXT    UNIQUE NOT NULL,
          Name                TEXT    NOT NULL,
          OwnerId             INTEGER NOT NULL REFERENCES Users(Id)
        );
        CREATE TABLE IF NOT EXISTS Tracks (
          Id               INTEGER PRIMARY KEY AUTOINCREMENT,
          PlaylistId       INTEGER NOT NULL REFERENCES Playlists(Id),
          SpotifyTrackId   TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS DeletedPlaylists (
          SpotifyPlaylistId  TEXT PRIMARY KEY,
          Name               TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ShrunkPlaylists (
          Id                    INTEGER PRIMARY KEY AUTOINCREMENT,
          OriginalPlaylistId    INTEGER NOT NULL REFERENCES Playlists(Id),
          NewSpotifyPlaylistId  TEXT    NOT NULL
        );
        """)
        conn.commit()
        conn.close()
