from enum import Enum
from typing import Iterator, Literal, TypedDict
from pymongo import MongoClient
from pymongo.database import Database


class Location(TypedDict):
    lat: float
    lon: float
    name: str

class State(TypedDict, total=False):
    type: Literal['idle', 'get', 'getDetailed', 'add', 'rename']
    location: Location # NotRequired[Location] doesn't work...


class Backend():
    db: Database

    def __init__(self) -> None:
        self.db = MongoClient('mongo', 27017).weatherDB
        self.db.locations.create_index(
            [('chat', 1), ('location.lat', 1), ('location.lon', 1)], unique=True)

    def addLocation(self, chat_id: str, location: Location) -> bool:
        if self.db.locations.count({
            'chat': chat_id,
            'location.lat': location['lat'],
            'location.lon': location['lon']
        }, limit=1) > 0:
          return False
        self.db.locations.insert_one({'chat': chat_id, 'location': location})
        return True

    def getLocations(self, chat_id: str) -> Iterator[Location]:
        cursor = self.db.locations.find({'chat': chat_id})
        for elem in cursor:
            yield elem['location']

    def renameLocation(self, chat_id: str, location: Location, newName: str):
        self.db.locations.find_one_and_update({
            'chat': chat_id,
            'location.lat': location['lat'],
            'location.lon': location['lon']
        }, {'$set': {'location.name': newName}})

    def setState(self, chat_id: str, state: State):
        self.db.states.replace_one({'chat': chat_id}, {
            'chat': chat_id,
            'state': state
        }, upsert=True)

    def getState(self, chat_id: str) -> State:
        result = self.db.states.find_one({'chat': chat_id})
        if result == None:
            return {'type': 'idle'}
        return result['state']