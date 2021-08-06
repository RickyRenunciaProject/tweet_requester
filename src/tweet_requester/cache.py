import os, logging
import os.path
import datetime
import zlib
from enum import Enum
from hashlib import md5, sha1
from datetime import datetime
from sys import getsizeof


def get_size(obj: object, seen=None):
    """Recursively finds size of objects"""
    size = getsizeof(obj)
    if seen is None:
        seen = set()
    obj_id = id(obj)
    if obj_id in seen:
        return 0
    # Important mark as seen *before* entering recursion to gracefully handle
    # self-referential objects
    seen.add(obj_id)
    if isinstance(obj, dict):
        size += sum([get_size(v, seen) for v in obj.values()])
        size += sum([get_size(k, seen) for k in obj.keys()])
    elif hasattr(obj, '__dict__'):
        size += get_size(obj.__dict__, seen)
    elif hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes, bytearray)):
        size += sum([get_size(i, seen) for i in obj])
    return size

    def request(self, key: K) -> V:
        pass

    def _get(self, key: K) -> V:
        value = self.request(key)
        store = Retrievable(value)
        self.CACHE.update({key: store})
        return value


class HashType(Enum):
    md5 = 1
    sha1 = 2


class Request():
    def __init__(
        self, uri: str, method: str = "GET",
        params: dict = {}, headers: dict = {}
    ):
        if type(uri) is not str:
            try:
                uri = str(uri)
            except:
                raise
        assert type(uri) is str, "uri most be a string!"
        assert type(method) is str, "method must be a string!"
        assert type(headers) is dict, "headers must be a dictionary!"
        self.URI = uri
        self.method = method.upper()
        self.params = self.order_dict(params)
        self.headers = self.order_dict(headers)

    @staticmethod
    def order_dict(dictionary: dict):
        keys = list(dictionary.keys())
        keys.sort()
        new_headers = {}
        for key in keys:
            new_headers.update({key: dictionary[key]})
        return new_headers


class Cache():
    TWO_YEARS_IN_DAYS = 780.50

    def __init__(
            self, cache_dir="./.tweet_cache/", hash_function=HashType.md5,
            soft_reload=False, refresh_rate=TWO_YEARS_IN_DAYS,
            compression_level: int = 3, hash_split=True, split_size=2, alt_hash=None
    ):
        assert type(hash_function) is HashType or (
            hash_function is None and alt_hash is not None), f"hash_function must be of type '{type(HashType.md5)}''"
        self.HASH_SPLIT = hash_split
        self.hash: HashType = hash_function
        self.SOFT_RELOAD: bool = soft_reload
        self.REFRESH_RATE: float = refresh_rate * 24 * \
            60 * 60  # Change from years to seconds
        self.ALT_HASH = alt_hash
        self.SPLIT_SIZE = split_size
        try:
            assert 0 <= compression_level <= 9, f"Compression level {compression_level} invalid! Defaulting to CmpLvl=3."
        except:
            compression_level = 0
        finally:
            self.COMPRESS_LEVEL = compression_level
        if not os.path.isdir(cache_dir):
            assert not os.path.isfile(
                cache_dir), f"'{cache_dir}' is a file not a directory!"
            os.makedirs(cache_dir)
        self.CACHE_DIR = cache_dir

    def uri_hash(self, uri: str, method: str = "GET", params: dict = {}, headers: dict = {}) -> str:
        tweet_request = Request(uri, method, params, headers)
        return self.request_hash(tweet_request)

    def request_hash(self, tweet_request: Request) -> str:
        def hash(x): return x
        if self.hash is HashType.md5:
            hash = md5
        elif self.hash is HashType.sha1:
            hash = sha1
        elif self.hash is None:
            return self.ALT_HASH(tweet_request)

        # if self.hash is HashType.md5:
        #     if header_hash is None:
        #         header_hash = "{" + md5(str(tweet_request.headers).encode('utf-8')).hexdigest() + "+"
        #     pre_hash_str = (tweet_request.method+"_"+tweet_request.URI + str(tweet_request.headers))
        #     return md5(pre_hash_str.encode('utf-8')).hexdigest()
        # elif self.hash is HashType.sha1:
        #     pre_hash_str = (tweet_request.method+"_"+tweet_request.URI + str(tweet_request.headers))
        #     return sha1(pre_hash_str.encode('utf-8')).hexdigest()

        # Hash header to avoid displaying public information
        if tweet_request.headers == {}:
            header_hash = "{}"
        else:
            header_hash = "{" + \
                hash(str(tweet_request.headers).encode(
                    'utf-8')).hexdigest() + "}"
        pre_hash_str = tweet_request.method + "_" + \
            tweet_request.URI + str(tweet_request.params) + header_hash
        return hash(pre_hash_str.encode('utf-8')).hexdigest()

    def request_stamp(self, tweet_request: Request) -> float:
        """
        Returns the milisecond presicion of the last time a record was cached.
        The integer part of the float is equivalent to seconds.

        Args:
            request (Request): request that includes URI and method

        Returns:
            float: Timestamp of the cache file.
        """
        if self.present(tweet_request=tweet_request):
            file_name = self.request_filename(tweet_request=tweet_request)
            return os.path.getmtime(file_name)
        return 0

    def needs_update(self, tweet_request: Request, refresh_rate: float = None) -> bool:
        """
        Determines if a value needs to be updated based on a refresh_rate 
        float number given in days based on the cach timestamp.

        Args:
            request (Request): Request object that references the resource.
            refresh_rate (float, optional): 
                Custom refresh_rate. Defaults to None to use self.REFRESH_RATE.

        Returns:
            bool: True if the resource need updating.
        """
        if self.SOFT_RELOAD:
            if refresh_rate is None:
                refresh_rate = self.REFRESH_RATE
            filename = self.request_filename(tweet_request=tweet_request)
            if os.path.isfile(filename):
                stamp = os.path.getmtime(filename=filename)
                now = datetime.now().timestamp()
                if now - stamp > refresh_rate:
                    return True
            else:
                return True
        return False

    def uri_filename(self, uri: str, method: str = "GET", params: dict = {}, headers: dict = {}):
        tweet_request = Cache.request_from_uri(uri, method, params, headers)
        return self.request_filename(tweet_request=tweet_request)

    def request_filename(self, tweet_request: Request) -> str:
        if not self.HASH_SPLIT:
            return os.path.join(self.CACHE_DIR, self.request_hash(tweet_request))
        else:
            hash_str = self.request_hash(tweet_request=tweet_request)
            n = self.SPLIT_SIZE
            relative_path = os.path.join(
                self.CACHE_DIR, *[hash_str[i:i+n] for i in range(0, len(hash_str), n)])
            os.makedirs(os.path.dirname(relative_path), exist_ok=True)
            return relative_path

    @staticmethod
    def request_from_uri(uri: str, method: str = "GET", params: dict = {}, headers: dict = {}) -> Request:
        tweet_request = Request(uri, method, params, headers)
        return tweet_request

    def present(self, tweet_request: Request) -> bool:
        file_name = self.request_filename(tweet_request=tweet_request)
        return os.path.isfile(file_name)

    def check(self, uri: str, method: str = "GET", params: dict = {}, headers: dict = {}):
        tweet_request = Cache.request_from_uri(uri, method, params, headers)
        return self.available(tweet_request)

    def available(self, tweet_request: Request):
        try:
            assert type(
                tweet_request) is Request, f"Invalid type {type(tweet_request)} as `request` argument for `available` method, need a Request object."
        except:
            if type(tweet_request) is str:
                tweet_request = Request(tweet_request)
            else:
                raise
        return self.present(tweet_request) and not self.needs_update(tweet_request)

    def get(self, uri: str, method: str = "GET", params: dict = {}, headers: dict = {}) -> str:
        tweet_request = Request(uri, method, params, headers)
        if self.available(tweet_request):
            with open(self.request_filename(tweet_request), 'rb') as cache:
                data = cache.read()
            dc_data = zlib.decompress(data)
            return dc_data.decode("utf-8")
        else:
            return "Unavailable"

    def store_bytes(self, uri: str, value: bytes, method: str = "GET", params: dict = {}, headers: dict = {}):
        tweet_request = Request(uri, method, params, headers)
        data = zlib.compress(value, level=self.COMPRESS_LEVEL)
        with open(self.request_filename(tweet_request), "wb") as cache:
            cache.write(data)
        logging.debug(f"Stored at: {self.request_filename(tweet_request)}")

    def store(self, uri: str,  value: str, method: str = "GET", params: dict = {}, headers: dict = {}):
        logging.debug("Storing...")
        self.store_bytes(uri, value.encode("utf-8"), method, params, headers)




