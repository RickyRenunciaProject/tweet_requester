import json, logging
from time import sleep
import requests
from .cache import Cache, Request
from typing import Union, Tuple, List


# Source https://developer.twitter.com/en/docs/twitter-api/tweets/lookup/api-reference/get-tweets-id
TWEET_BY_ID_URL = "https://api.twitter.com/2/tweets/"


class BearerAuth(requests.auth.AuthBase):
    """ ReadOnly Bearer Token authentication. 
    It only requires the bearer token to work.
    """

    def __init__(self, token: str):
        self.token = token

    def __call__(self, r: Request):
        r.headers["authorization"] = "Bearer " + self.token
        return r


class TSess():
    BASE_URL_11 = "https://api.twitter.com/1.1/statuses/lookup.json"

    def __init__(
        self,
        bearer_token: str,
        expansions: List[str] = [
            "attachments.media_keys",
            "author_id",
            "entities.mentions.username",
            "referenced_tweets.id",
            "referenced_tweets.id.author_id",
        ],
        media_fields: List[str] = [
            "type",
            "duration_ms",
            "preview_image_url",
            "public_metrics",

        ],
        place_fields: List[str] = [
            "country",
            "country_code",
            "full_name",
            "geo",
            "id",
            "name",
            "place_type",
            "contained_within",
        ],
        user_fields: List[str] = [
            "username",
            "name",
            "id",
            "created_at",
            "description",
            "pinned_tweet_id",
        ],
        tweet_fields: List[str] = [
            "lang",
            "author_id",
            "id",
            "public_metrics",
            "possibly_sensitive",
            "conversation_id",
            "in_reply_to_user_id",
            "referenced_tweets",
            "source",
            "text",
            "geo",
        ],
        cache_dir: str = "./.tweet_bearer_cache/",
        error_log=".tweet_error.json",
        compression_level: int = 3,
        sleep_time=1.0,
        hash_split=False,
    ):
        self.auth = BearerAuth(bearer_token)
        self.cache = Cache(cache_dir=cache_dir, soft_reload=False,
                           compression_level=compression_level, hash_split=hash_split)
        self.ERROR_LOG = error_log
        self.SLEEP_TIME = sleep_time
        try:
            handler = open(self.ERROR_LOG, 'r')
            self.ERROR_DICT: dict = json.load(handler)
            handler.close()
        except:
            self.ERROR_DICT = {}

        self.PARAMS = {
            'expansions': ','.join(expansions),
            'media.fields': ','.join(media_fields),
            'tweet.fields': ','.join(tweet_fields),
            'place.fields': ','.join(place_fields),
            'user.fields': ','.join(user_fields),
        }
        self.failed_ids = []

    def load_tweet_batch(
        self, ids: List[str],
        base_url="https://api.twitter.com/2/tweets"
    ) -> Union[str, None]:
        # https://api.twitter.com/2/tweets?ids=1228393702244134912,1227640996038684673,1199786642791452673&tweet.fields=created_at&expansions=author_id&user.fields=created_at
        params = self.PARAMS.copy()
        params.update({"ids": ','.join(ids)})
        # URI = self.generate_URI(base_url, params)
        if self.cache.check(base_url, params=params):
            return self.cache.get(base_url, params=params)
        else:
            response = requests.get(base_url, params=params, auth=self.auth)
            if response.status_code == 200:
                self.cache.store(base_url, response.text, params=params)
                sleep(self.SLEEP_TIME)
                return response.text
        return None

    @staticmethod
    def generate_URI(base_url: str, params: dict, v2: bool = True):
        params = params.copy()
        params = Request.order_dict(params)
        uri = base_url
        if len(params.keys()) > 0:
            uri += "?"
            for key in params.keys():
                if hasattr(params[key], '__iter__') and type(params[key]) is not str:
                    uri += key + "=" + ','.join(params[key]) + "&"
                else:
                    uri += key + "=" + params[key] + "&"
        return uri[:-1]

    @staticmethod
    def generate_URI_11(tweet_id: str, params: dict = {}):
        new_params = {
            "id": tweet_id,
            "include_entities": True,
            "tweet_mode": "extended",  # Testing to include Extended Entities
            "trim_user": False,
        }
        params.update(new_params)
        return TSess.BASE_URL_11, params

    @staticmethod
    def generate_batch_URI_11(tweet_ids: List[str], params: dict = {}):
        tweet_ids_str = ",".join(tweet_ids)
        new_params = {
            "id": tweet_ids_str,
            "include_entities": True,
            "tweet_mode": "extended",  # Testing to include Extended Entities
            "trim_user": False,
        }
        params.update(new_params)
        return TSess.BASE_URL_11, params

    def load_request(
        self, base_url: str, params: dict,
        is_tweet: bool = True, is_v2: bool = True
    ) -> Tuple[str, int]:
        if self.cache.check(base_url, params=params):
            logging.debug("Value in Cache")
        elif id in self.ERROR_DICT.keys():
            logging.debug("Previous Error Found!")
            return json.dumps(self.ERROR_DICT[id][2]), self.ERROR_DICT[id][1]
        else:
            logging.debug("Need to request value")
            sleep(self.SLEEP_TIME)
            response = requests.get(base_url, params=params, auth=self.auth)
            response.status_code
            if response.status_code == 200:
                data = response.text
                sleep(0.0005)
                r: List[dict] = json.loads(data)
                if is_tweet and is_v2:
                    if type(r) is list:
                        assert len(r) > 0, "List is empty! Response was empty list."
                        r = r[0]
                sleep(0.0005)
                if "errors" in r.keys() and "data" not in r.keys() and is_tweet:
                    error: str = r["errors"][0]["title"]
                    logging.debug(f"{id} - Twitter Error Returned: {error}")
                    hash = self.cache.uri_hash(base_url, params=params)
                    error_code = 440
                    self.ERROR_DICT.update({id: (hash, error_code, r)})
                    with open(self.ERROR_LOG, "w") as handler:
                        json.dump(self.ERROR_DICT, handler, indent=2)
                    return data, error_code  # Using code 440 for any Twitter API error code found
                else:
                    self.cache.store(uri=base_url, value=data,
                                     params=params, method="GET")
            else:
                hash = self.cache.uri_hash(base_url, params=params)
                error_code = response.status_code
                self.ERROR_DICT.update({id: (hash, error_code, response.text)})
                with open(self.ERROR_LOG, "w") as handler:
                    json.dump(self.ERROR_DICT, handler, indent=2)
                logging.debug(f"Could not load tweet: {response.reason}")
                return response.text, response.status_code
        return self.cache.get(base_url, params=params), 200

    def load_tweet_11(self, id: str, v2: bool = True) -> Tuple[str, int]:
        if type(id) is int:
            id = str(id)
        elif type(id) is str:
            assert id.isnumeric(
            ), f"id {type(id)} provided is not a valid string representation of an integer."
        else:
            raise Exception(
                f"Invalid id type: {type(id)}. Only <class int> and <class str> are acceptable.")
        if v2:
            base_url, params = TSess.generate_URI_11(id, params=self.PARAMS)
        else:
            base_url, params = TSess.generate_URI_11(id, params={})

        return self.load_request(base_url=base_url, params=params)

    def load_tweet_batch_11(self, ids: List[str], v2: bool = True) -> Tuple[str, int]:
        for id in ids:
            try:
                assert id.isnumeric(
                ), f"id {type(id)} provided is not a valid string representation of an integer."
            except:
                raise Exception(
                    f"Invalid id type: {type(id)}. Only numeric <class str> are acceptable.")
        if v2:
            params = self.PARAMS
        else:
            params = {}
        base_url, params = TSess.generate_batch_URI_11(ids, params=params)

        return self.load_request(base_url=base_url, params=params)

    def load_tweet(self, id: str, base_url=TWEET_BY_ID_URL) -> Tuple[str, int]:
        if type(id) is int:
            id = str(id)
        elif type(id) is str:
            assert id.isnumeric(
            ), f"id {type(id)} provided is not a valid string representation of an integer."
        else:
            raise Exception(
                f"Invalid id type: {type(id)}. Only <class int> and <class str> are acceptable.")
        url = base_url + id
        headers = {}
        logging.debug(f"Requesting tweet {id} with uri: '{url}'")
        return self.load_request(base_url=url, params=self.PARAMS)
