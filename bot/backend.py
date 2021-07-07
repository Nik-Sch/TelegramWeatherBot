from dataclasses import asdict, dataclass
from typing import Dict, Iterator, List, Literal, Optional, TypedDict
from pymongo import MongoClient
from pymongo.database import Database
from requests_cache import CachedSession
from requests_cache.backends import MongoCache
import os

@dataclass
class Location:
    lat: float
    lon: float
    name: str
    default: bool = False

    @staticmethod
    def fromDict(d: Dict):
        return Location(d['lat'], d['lon'], d['name'], d.get('default', False))
    
    def toDict(self):
        return asdict(self)


StateType = Literal['idle', 'get', 'getTenDays', 'getRadar', 'add', 'rename', 'remove', 'set_default']

@dataclass
class State:
    type: StateType
    location: Optional[Location] = None
    addLocations: Optional[List[Location]] = None

    @staticmethod
    def fromDict(d: Dict) -> 'State':
        locationDict = d.get('location', None)
        addLocationDict = d.get('addLocations', None)
        location = Location.fromDict(locationDict) if locationDict is not None else None
        addLocations = [Location.fromDict(l) for l in addLocationDict] if addLocationDict is not None else None
        return State(d['type'], location, addLocations)
    
    def toDict(self):
        locDict = self.location.toDict() if self.location is not None else None
        locListDict = [l.toDict() for l in self.addLocations] if self.addLocations is not None else None
        return {
            'type': self.type,
            'location': locDict,
            'addLocations': locListDict
        }

def getRequestsCache():
    return CachedSession(cache_name='/cache/http_cache.sqlite')

class Backend():
    mongoClient = MongoClient('mongo', 27017, connect=False)
    requestsSession = getRequestsCache()

    db: Database

    def __init__(self) -> None:
        self.db = self.mongoClient.weatherDB
        self.db.locations.create_index(
            [('chat', 1), ('location.lat', 1), ('location.lon', 1)], unique=True)

    def addLocation(self, chat_id: str, location: Location) -> bool:
        if self.db.locations.count({
            'chat': chat_id,
            'location.lat': location.lat,
            'location.lon': location.lon,
        }, limit=1) > 0:
          return False
        self.db.locations.insert_one({'chat': chat_id, 'location': location.toDict()})
        return True

    def removeLocation(self, chat_id: str, location: Location):
        self.db.locations.delete_one({
            'chat': chat_id,
            'location.lat': location.lat,
            'location.lon': location.lon
        })

    def getLocations(self, chat_id: str) -> Iterator[Location]:
        cursor = self.db.locations.find({'chat': chat_id})
        for elem in cursor:
            yield Location.fromDict(elem['location'])

    def getDefaultLocation(self, chat_id: str) -> Optional[Location]:
        for location in self.getLocations(chat_id):
            if location.default:
                return location
        return None

    def setDefaultLocation(self, chat_id: str, location: Location):
        self.db.locations.update_many({
            'chat': chat_id,
            'location.default': True
        }, {'$set': {'location.default': False}})
        self.db.locations.update_one({
            'chat': chat_id,
            'location.lat': location.lat,
            'location.lon': location.lon
        }, {'$set': {'location.default': True}})

    def renameLocation(self, chat_id: str, location: Location, newName: str):
        self.db.locations.find_one_and_update({
            'chat': chat_id,
            'location.lat': location.lat,
            'location.lon': location.lon
        }, {'$set': {'location.name': newName}})

    def setState(self, chat_id: str, state: State):
        self.db.states.replace_one({'chat': chat_id}, {
            'chat': chat_id,
            'state': state.toDict()
        }, upsert=True)

    def getState(self, chat_id: str) -> State:
        result = self.db.states.find_one({'chat': chat_id})
        if result == None:
            return State('idle')
        return State.fromDict(result['state'])
