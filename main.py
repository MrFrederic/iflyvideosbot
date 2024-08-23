from storage_manager import Storage

storage = Storage()

#video = storage.add_video("tgid", "iFlyMinsk_DaniilAnopreenko_Door_3_2024-08-16_19-56-23.mp4", 1024, 120, 69)
video = storage.video(1)
storage.close()