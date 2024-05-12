import pickle
from pathlib import Path

from streamlit_authenticator.utilities.hasher import Hasher

names = ["Black Panther", "Captain America", "Iron Man", "Spider-Man", "Thor"]
usernames = ["blackpanther", "captainamerica", "ironman", "spiderman", "thor"]
passwords = ["black123", "captain123", "iron123", "spider123", "thor123"]

hashed_passwords = Hasher(passwords).generate()

file_path = Path(__file__).parent / "hashed_pw.pkl"
with file_path.open("wb") as file:
    pickle.dump(hashed_passwords, file)