from storage_manager import Storage
from flights import Flight

class User_Management:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def get(self, id: int) -> 'User':
        query = "SELECT id, username, menu_message, chat_state, type FROM users WHERE id = ?"
        self.storage.db_cursor.execute(query, (id,))
        result = self.storage.db_cursor.fetchone()
        return User(*result, self) if result else None

    def add(self, username: str, menu_message: int, chat_state: str, type: str) -> 'User':
        try:
            self.storage.db_cursor.execute('''
                INSERT INTO users (username, menu_message, chat_state, type)
                VALUES (?, ?, ?, ?)
            ''', (username, menu_message, chat_state, type))
            self.storage.db_conn.commit()
            id = self.storage.db_cursor.lastrowid
            return self.get(id)
        except Exception as e:
            self.storage.db_conn.rollback()
            print(f"Error: {e}")
            return None

class User:
    def __init__(self, id: int, username: str, menu_message: int, chat_state: str, type: str, u_m: User_Management) -> None:
        self.id = id
        self.username = username
        self.menu_message = menu_message
        self.chat_state = chat_state
        self.type = type
        self._u_m = u_m
        self._storage = u_m.storage

    def update_username(self, username) -> 'User':
        query = "UPDATE users SET username = ? WHERE id = ?;"
        self._storage.db_cursor.execute(query, (username, self.id,))
        self.username = username
        return self._u_m.get(self.id)
    
    def update_menu_message(self, menu_message) -> 'User':
        query = "UPDATE users SET menu_message = ? WHERE id = ?;"
        self._storage.db_cursor.execute(query, (menu_message, self.id,))
        self.menu_message = menu_message
        return self._u_m.get(self.id)
    
    def update_chat_state(self, chat_state) -> 'User':
        query = "UPDATE users SET chat_state = ? WHERE id = ?;"
        self._storage.db_cursor.execute(query, (chat_state, self.id,))
        self.chat_state = chat_state
        return self._u_m.get(self.id)

    def add_flight(self, flight: Flight):
        try:
            self._storage.db_cursor.execute('''
                INSERT INTO user_flight (user, flight)
                VALUES (?, ?)
            ''', (self.id, flight.id,))
            self._storage.db_conn.commit()
            id = self._storage.db_cursor.lastrowid
            return True
        except Exception as e:
            self._storage.db_conn.rollback()
            print(f"Error: {e}")
            return None