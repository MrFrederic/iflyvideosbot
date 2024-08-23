class Flight:
    def __init__(self, id: int, datetime: int, flight_number: int, length: int, storage) -> None:
        self.id = id
        self.datetime = datetime  # This represents a timestamp object
        self.flight_number = flight_number
        self.length = length  # This represents flight duration in seconds
        self.videos = storage.list_flights_videos(self)

    @classmethod
    def group_by_sessions(cls, flights: list['Flight']) -> list['Session']:
        def is_within_session(session: Session, flight: Flight, buffer: int = 900) -> bool:
            return session.start - buffer <= flight.datetime <= session.end + buffer
        
        sessions: list[Session] = []
        for flight in flights:
            session = next((s for s in sessions if is_within_session(s, flight)), None)
            
            if session:
                session.add_flight(flight)
            else:
                sessions.append(Session(flight))

        return sessions

class Session:
    def __init__(self, flight: Flight) -> None:
        self.start = flight.datetime
        self.end = flight.datetime + flight.length
        self.flights = [flight]

    def add_flight(self, flight: Flight) -> 'Session':
        self.start = min(self.start, flight.datetime)
        self.end = max(self.end, flight.datetime + flight.length)

        self.flights.append(flight)
        self.flights.sort(key=lambda f: f.datetime)
        return self
