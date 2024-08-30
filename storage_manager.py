import os
import sqlite3
from datetime import datetime, timedelta
from videos import Video
from flights import Flight
from typing import Optional
from users import User_Management, User

class Storage:
    db_file = "data.db"

    def __init__(self) -> None:
        try:
            if not os.path.exists(Storage.db_file):
                # Create database file and tables if they do not exist
                with sqlite3.connect(Storage.db_file) as conn:
                    cursor = conn.cursor()
                    create_tables_query = """
                    CREATE TABLE IF NOT EXISTS flights (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        datetime INTEGER NOT NULL UNIQUE,
                        flight_number INTEGER NOT NULL,
                        length INTEGER NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER NOT NULL UNIQUE PRIMARY KEY AUTOINCREMENT,
                        username TEXT,
                        menu_message INTEGER,
                        chat_state TEXT,
                        type TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS user_flight (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        user INTEGER NOT NULL,
                        flight INTEGER NOT NULL,
                        FOREIGN KEY (user) REFERENCES users(id),
                        FOREIGN KEY (flight) REFERENCES flights(id)
                    );

                    CREATE TABLE IF NOT EXISTS videos (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        telegram_id INTEGER NOT NULL UNIQUE,
                        filename TEXT NOT NULL,
                        flight INTEGER,
                        uploaded_date INTEGER,
                        uploaded_by INTEGER,
                        file_size INTEGER,
                        file_length INTEGER,
                        parsed_flyer TEXT,
                        parsed_date TEXT,
                        parsed_flight TEXT,
                        parsed_camera TEXT,
                        FOREIGN KEY (flight) REFERENCES flights(id),
                        FOREIGN KEY (uploaded_by) REFERENCES users(id)
                    );
                    """
                    cursor.executescript(create_tables_query)
                    conn.commit()

            self.db_conn = sqlite3.connect(Storage.db_file)
            self.db_cursor = self.db_conn.cursor()
        except Exception as e:
            print(f"Error initializing database: {e}")

    def close(self) -> None:
        if self.db_conn:
            self.db_conn.close()



    def flight(self, id: int) -> Optional[Flight]:
        query = "SELECT id, datetime, flight_number, length FROM flights WHERE id = ?"
        self.db_cursor.execute(query, (id,))
        result = self.db_cursor.fetchone()
        return Flight(*result, self) if result else None

    def find_flight(self, timestamp: int) -> Optional[Flight]:
        query = "SELECT id FROM flights WHERE datetime = ?"
        self.db_cursor.execute(query, (timestamp,))
        result = self.db_cursor.fetchone()
        if result:
            return self.flight(result[0])
        return None

    def add_flight(self, timestamp: int, flight_number: int, length: int) -> Flight:
        self.db_cursor.execute('''
            INSERT INTO flights (datetime, flight_number, length)
            VALUES (?, ?, ?)
        ''', (timestamp, flight_number, length))
        self.db_conn.commit()
        id = self.db_cursor.lastrowid
        return self.flight(id)
    
    def list_users_flights(self, user, date: int=None) -> list[Flight]: #date should be a timestamp (in UTC)
        self.db_cursor.execute("SELECT flight FROM user_flight WHERE user = ?", (user.id,))
        flight_ids = self.db_cursor.fetchall()
        flights = [self.flight(flight_id[0]) for flight_id in flight_ids]

        # Apply date filter if provided
        if date is not None:
            provided_date = datetime.fromtimestamp(date)
            start_of_day = datetime(provided_date.year, provided_date.month, provided_date.day)
            end_of_day = start_of_day + timedelta(days=1) - timedelta(seconds=1)
            flights = [flight for flight in flights if start_of_day.timestamp() <= flight.datetime <= end_of_day.timestamp()]

        return flights
    
    def list_flights_users(self, flight: Flight) -> list[User]:
        self.db_cursor.execute("SELECT user FROM user_flight WHERE flight = ?", (flight.id,))
        users_ids = self.db_cursor.fetchall()
        u_m = User_Management(self)
        users = [u_m.get(users_id[0]) for users_id in users_ids]

        return users


    def video(self, id: int) -> Optional[Video]:
        query = "SELECT id, telegram_id, filename, flight, uploaded_date, uploaded_by, file_size, file_length, parsed_flyer, parsed_date, parsed_flight, parsed_camera FROM videos WHERE id = ?"
        self.db_cursor.execute(query, (id,))
        result = self.db_cursor.fetchone()
        return Video(*result) if result else None

    def add_video(self, telegram_id: int, filename: str, file_size: int, file_length: int, uploaded_by: int) -> Video:
        try:
            parsed_flyer, parsed_camera, parsed_flight, parsed_date = Video.parse_filename(filename)
            uploaded_date = int(datetime.now().timestamp())
            flight_timestamp = int(datetime.strptime(parsed_date, '%Y_%m_%d_%H_%M_%S').timestamp())
            flight = self.find_flight(flight_timestamp)
            if not flight:
                flight = self.add_flight(flight_timestamp, parsed_flight, file_length)

            self.db_cursor.execute("""
                INSERT INTO videos (telegram_id, filename, flight, uploaded_date, uploaded_by, file_size, file_length, parsed_flyer, parsed_date, parsed_flight, parsed_camera)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (telegram_id, filename, flight.id, uploaded_date, uploaded_by, file_size, file_length, parsed_flyer, 
                parsed_date, parsed_flight, parsed_camera))
            
            self.db_conn.commit()
            print("Video added successfully.")
            id = self.db_cursor.lastrowid
            return self.video(id)
        except Exception as e:
            print(f"Error adding video: {e}")
            self.db_conn.rollback()

    #TODO - Optional filters
    def list_flights_videos(self, flight: Flight, camera=None) -> list[Video]:
        self.db_cursor.execute("SELECT id FROM videos WHERE flight = ?", (flight.id,))
        video_ids = self.db_cursor.fetchall()
        videos = [self.video(video_id[0]) for video_id in video_ids]
        return videos