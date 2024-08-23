from flights import Flight
from typing import Tuple, Optional

class Video:
    def __init__(self, id: int, telegram_id: int, filename: str, flight: int, uploaded_date: int, 
                 uploaded_by: int, file_size: int, file_length: int, parsed_flyer: str, 
                 parsed_date: str, parsed_flight: str, parsed_camera: str) -> None:
        self.id = id
        self.telegram_id = telegram_id
        self.filename = filename
        self.flight = flight
        self.uploaded_date = uploaded_date
        self.uploaded_by = uploaded_by
        self.file_size = file_size
        self.file_length = file_length
        self.parsed_flyer = parsed_flyer
        self.parsed_date = parsed_date
        self.parsed_flight = parsed_flight
        self.parsed_camera = parsed_camera

    @classmethod
    def parse_filename(cls, filename: str) -> Optional[Tuple[str, str, str, str]]:
        """
        Parse the filename to extract flyer, camera name, flight number, and datetime.
        """
        try:
            parts = filename.replace('-', '_').split('.')[0].split('_')
            if len(parts) < 10:
                raise ValueError(f"Filename does not contain enough parts to parse.")

            flyer = str(parts[1])
            camera = str(parts[2])
            flight = str(parts[3])
            datetime = str('_'.join(parts[4:10]))

            return flyer, camera, flight, datetime
        except Exception as e:
            print(f"Error parsing filename: {e}")
            return None
