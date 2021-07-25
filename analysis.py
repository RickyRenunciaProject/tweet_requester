import json
import pickle
import os.path
from sys import getsizeof
from typing import OrderedDict, Union, List, Tuple
from tweet_rehydrate.cache import JsonlHandler
import pandas as pd
import sqlite3


class TweetMedia:
    def __init__(self, data: dict, source_tweet=None):
        self.data = data
        try:
            self.id = data["id_str"]
        except:
            try:
                self.id = data["id"]
            except:
                raise
        self.source_tweet = source_tweet

    def mtype(self):
        return self.data["type"]

    def url(self):
        return self.data["media_url_https"]

    def __str__(self):
        return self.mtype().upper() + ": " + self.url()


class TweetPhoto(TweetMedia):
    def __init__(self, data: dict, source_tweet=None):
        super().__init__(data, source_tweet=source_tweet)
        assert self.mtype().lower() == "photo", "Not a photo media"

    def thumbnailURL(self):
        if "thumb" in self.data["sizes"].keys():
            return self.url() + ":thumb"
        else:
            return self.url()

    def largeURL(self):
        if "large" in self.data["sizes"].keys():
            return self.url() + ":large"
        else:
            return self.url()

    def mediumURL(self):
        if "medium" in self.data["sizes"].keys():
            return self.url() + ":medium"
        else:
            return self.url()

    def smallURL(self):
        if "small" in self.data["sizes"].keys():
            return self.url() + ":small"
        else:
            return self.url()


class TweetVideo(TweetMedia):
    def __init__(self, data: dict, source_tweet=None):
        super().__init__(data, source_tweet=source_tweet)
        assert self.mtype().lower() == "video", "Not a video media"

    def getVariants(self):
        try:
            return self.data["video_info"]["variants"]
        except:
            return []

    def url(self, bitrate=832000):
        return self.getBestVariant(bitrate)['url']

    def getBestVariant(self, bitrate=832000):
        closest = None
        distance = bitrate
        for v in self.getVariants():
            if "bitrate" in v.keys():
                if int(v["bitrate"]) == bitrate:
                    return v
                elif distance > abs(int(v["bitrate"])-bitrate):
                    distance = abs(int(v["bitrate"])-bitrate)
                    closest = v
            else:
                continue
        if closest is not None:
            # Return Closest
            return closest
        # Return first in list
        return self.getVariants()[0]


class TweetAnalyzer:
    def __init__(self, data: Union[str, dict], localMedia: bool = True):
        self.data = data
        self.onlyLocalMedia = localMedia
        if type(self.data) is str:
            self.data = json.loads(self.data)
        self.extractMeta()

    def extractMeta(self):
        try:
            self.id = self.data["id_str"]
        except:
            try:
                self.id = self.data["id"]
            except:
                raise
        # self.user_id = self.data['user']['id_str']
        try:
            self.user_screen_name = self.data['user']["screen_name"]
        except:
            raise
        # self.user_id = self.data['user']['id_str']
        try:
            self.user_id = self.data['user']["id_str"]
        except:
            try:
                self.user_id = self.data['user']["id"]
            except:
                raise
        self._isRetweet()
        self._isQuote()
        self.retweetCount = self.data.get("retweet_count", 0)
        self.quoteCount = self.data.get("quote_count", 0)
        self.favoriteCount = self.data.get("favorite_count", 0)
        if not self.onlyLocalMedia:
            self._hasMedia()
        self._hasLocalMedia()

    def language(self) -> Union[str, None]:
        # Use default "und" used by Twitter
        lang = self.data.get("lang", "und")
        return lang if lang != "und" and type(lang) is str else None

    def _hasMedia(self):
        self.hasMedia = 'media_url_https' in str(
            self.data) or 'media_url' in str(self.data)
        self.extractMedia()

    def text(self) -> str:
        try:
            return self.data["full_text"]
        except Exception as _:
            return self.data.get("text", "")

    def _hasLocalMedia(self):
        self.hasLocalMedia = 'media_url_https' in str(self.data['entities']) or 'media_url' in str(self.data['entities']) or 'media_url_https' in str(
            self.data.get('extended_entities', {})) or 'media_url' in str(self.data.get('extended_entities', {}))
        # If hasMedia has not been set before
        if not hasattr(self, "hasMedia"):
            self.hasMedia = self.hasLocalMedia
        self.extractMedia(recursive=False)

    def extractMedia(self, recursive: bool = True) -> List[str]:
        media = []
        if 'entities' in self.data.keys():
            if 'media' in self.data['entities']:
                for m in self.data['entities']['media']:
                    if m["type"].lower() == "photo":
                        media.append(TweetPhoto(m, self.id))
                    elif m["type"].lower() == "video":
                        media.append(TweetVideo(m, self.id))
                    else:
                        media.append(TweetMedia(m, self.id))
        if 'extended_entities' in self.data.keys():
            if 'media' in self.data['extended_entities'].keys():
                for m in self.data['extended_entities']['media']:
                    if m["type"].lower() == "photo":
                        media.append(TweetPhoto(m, self.id))
                    elif m["type"].lower() == "video":
                        media.append(TweetVideo(m, self.id))
                    else:
                        media.append(TweetMedia(m, self.id))

        # If recursive process the internal media of retweeted or quoted status
        # Else skip recursion and store in self.localMedia
        if recursive and getattr(self, "retweeted_status", False):
            if self.retweeted_status.hasMedia:
                media = media + self.retweeted_status.media
        if recursive and getattr(self, "quoted_status", False):
            if self.quoted_status.hasMedia:
                media = media + self.quoted_status.media
        if recursive:
            self.media: List[Union[TweetMedia, TweetVideo, TweetPhoto]] = media
        else:
            self.localMedia: List[Union[TweetMedia,
                                        TweetVideo, TweetPhoto]] = media
            if not hasattr(self, "media"):
                self.media = self.localMedia

    def url(self):
        return f"https://twitter.com/any_user/status/{self.id}"

    def urlByIDs(self):
        return f"https://twitter.com/{self.user_id}/status/{self.id}"

    def _urlQuotedTweet(self):
        if self.isQuote:
            for URL in self.data["entities"]["urls"]:
                try:
                    url_str = URL["expanded_url"]
                    if "https://twitter.com/" in url_str:
                        return url_str
                except:
                    continue
        return "Not applicable"

    def _urlOriginalTweet(self):
        if self.isRetweet:
            return f"https://twitter.com/{self.ot_user_id}/status/{self.ot_id}"
        return "Not applicable"

    def _isRetweet(self):
        # As stipulated in Twitter API v1.1
        # Retweets can be distinguished from typical Tweets by the existence of a retweeted_status attribute.
        self.urlOriginalTweet = "Not applicable"
        value = False
        # If a tweet is a retweet it is not the quoting tweet.
        if "retweeted_status" in self.data.keys():
            if self.data["retweeted_status"] is not None:
                self.retweeted_status = TweetAnalyzer(
                    self.data["retweeted_status"], self.onlyLocalMedia)
                self.urlOriginalTweet = self.retweeted_status.urlByIDs()
                value = True
        self.isRetweet = value

    def _isQuote(self):
        value = False
        self.urlQuotedTweet = "Not applicable"
        if not self.isRetweet:
            if "quoted_status" in self.data.keys():
                if self.data["quoted_status"] is not None:
                    self.quoted_status = TweetAnalyzer(
                        self.data["quoted_status"], self.onlyLocalMedia)
                    self.urlQuotedTweet = self.quoted_status.urlByIDs()
                    value = True
        self.isQuote = value

    def user_mentions(self) -> List[dict]:
        entities: dict = self.data.get("entities", {})
        return entities.get("user_mentions", [])
    
    def hashtags(self) -> List[dict]:
        entities: dict = self.data.get("entities", {})
        return entities.get("hashtags", [])

    # # Verify if tweet already in omeka
    # @staticmethod
    # def is_in_omeka(tweet:dict, omeka_api_url:str,itemset:str="test"):
    #     tweet_id = tweet["id_str"]
    #     user_id = tweet["user"]["id_str"]
    #     url_id = f"https://twitter.com/{user_id}/status/{tweet_id}"
    #     response = requests.get(url=omeka_api_url+"items/", params=json.dumps({"property": ['identifier','eq',url_id]}))
    #     if response.status_code == 200:
    #         if int(json.loads(response.text)["hey"])>0:
    #             pass
    #         pass
    #     return False

    # def omekas_store(self, omeka_api_url:str):
    #     json_ld = self.generateJSON_LD(omeka_api_url);
    #     requests.post(omeka_api_url)

    # def generateJSON_LD(self, omeka_api_url:str):
    #     data = {
    #         "@context": "https://schema.org/SocialMediaPosting",
    #         "@id": self.urlByIDs(),
    #     }
    #     if self.isRetweet:
    #         # retweeted_status = TweetAnalyzer(self.data["retweeted_status"])
    #         if not TweetAnalyzer.is_in_omeka(self.data["retweeted_status"], omeka_api_url):
    #             retweeted_status = TweetAnalyzer(self.data["retweeted_status"])
    #             retweeted_status.omekas_store(omeka_api_url)
    #         else:
    #             pass
    #         data["isBasedOn"]= {
    #             "@context": "https://schema.org/SocialMediaPosting",
    #             "@id":[retweeted_status.urlByIDs(),]
    #         }
    #     elif self.isQuote:
    #         # quoted_status = TweetAnalyzer(self.data["quoted_status"])
    #         if not TweetAnalyzer.is_in_omeka(self.data["quoted_status"], omeka_api_url):
    #             retweeted_status.omekas_store(omeka_api_url)
    #         else:
    #             pass
    #         data["isBasedOn"]= {
    #             "@context": "https://schema.org/SocialMediaPosting",
    #             "@id":[retweeted_status.urlByIDs(),]
    #         }
    #     return data, remote_store_url

    def __str__(self):
        output: str = f"ID: {self.id}\nText: {self.text()}\nURL: {self.urlByIDs()}\nRetweet:{str(self.isRetweet)}\nOriginal Tweet URL: {self.urlOriginalTweet}\nQuotes:{str(self.isQuote)}\nQuoted Tweet URL: {self.urlQuotedTweet}\nHas Media={str(self.hasMedia)}\nHas Local Media={str(self.hasLocalMedia)}\nMedia={str([str(m) for m in self.media])}"
        return output

    def __lt__(self, other):
        selfCount = self.retweetCount
        otherCount = other.retweetCount
        if self.isRetweet:
            selfCount = 0
        if other.isRetweet:
            otherCount = 0
        return selfCount < otherCount

    def __le__(self, other):
        selfCount = self.retweetCount
        otherCount = other.retweetCount
        if self.isRetweet:
            selfCount = 0
        if other.isRetweet:
            otherCount = 0
        return selfCount <= otherCount

    def __gt__(self, other):
        return not self.__le__(other)

    def __ge__(self, other):
        return not self.__lt__(other)

    def __eq__(self, other):
        selfCount = self.retweetCount
        otherCount = other.retweetCount
        if self.isRetweet:
            selfCount = 0
        if other.isRetweet:
            otherCount = 0
        return selfCount == otherCount


class TweetJLAnalyzer:
    # First-In-First-Out list to keep track of least recently used tweet in cache.
    cache_list = []
    id_to_line = {}  # One to one Mapping of line_number:int to tweet_id:str
    line_to_id = {}
    jl_cache = {}  # cache of latest CACHE_SIZE accessed tweets from the jsonl
    CACHE_SIZE = 800
    MIN_RETWEET_COUNT = 99
    # keys:int = retweet_count, value:list = list of jsonl line numbers with that retweet_count
    retweet_cache = {}
    quote_cache = {}  # keys:int = quote_count, values:list = list of jsonl line numbers with that retweet_count
    retweetOf = {}  # keys:str = the url to a retweeted tweet, value:int = number of times found in dataset
    quoteOf = {}  # keys:str = the url to a quoted tweet, value:int = number of times quoted in dataset

    def __init__(self, filename: str, rtc_cache_file: str = "", reset=False, local_media=False, cache_size=None):
        if cache_size is not None and type(cache_size) is int:
            self.CACHE_SIZE = cache_size
        self.filename = filename
        self.only_local_media = local_media
        # if rtc_cache_file == "":
        #     rtc_cache_file = os.path.join(os.path.dirname(filename), "rtc_cache_" + os.path.basename(filename)+".pkl") # pickle file
        # self.sortByRetweet(rtc_cache_file=rtc_cache_file)
        self.orderedListGeneration(reset=reset)

    def get_most_retweeted(self, n=10, has_media=False, has_local_media=False) -> List[Tuple[int, str, int]]:
        rt_counts = list(self.retweet_cache.keys())
        rt_counts.sort(reverse=True)
        found = 0
        idx = 0
        all_found = []
        response = []
        while found < n:
            tmp_list = self.retweet_cache[rt_counts[idx]]
            if has_local_media:
                for key in tmp_list:
                    id_str = self.line_to_id[key]
                    if type(key) is int:
                        tweet = self.fetch_by_position(key)
                    else:
                        tweet: TweetAnalyzer = self.fetch_by_id(id_str)
                    if type(tweet) is TweetAnalyzer:
                        if tweet.hasLocalMedia:
                            if id_str not in all_found:
                                all_found.append(id_str)
                                response.append((rt_counts[idx], id_str, key))
                                found += 1
            elif has_media:
                for key in tmp_list:
                    id_str = self.line_to_id[key]
                    if type(key) is int:
                        tweet = self.fetch_by_position(key)
                    else:
                        tweet: TweetAnalyzer = self.fetch_by_id(id_str)
                    if type(tweet) is TweetAnalyzer:
                        if tweet.hasMedia:
                            if id_str not in all_found:
                                all_found.append(id_str)
                                response.append((rt_counts[idx], id_str, key))
                                found += 1
            else:
                for key in tmp_list:
                    id_str = self.line_to_id[key]
                    if id_str not in all_found:
                        all_found.append(id_str)
                        response.append((rt_counts[idx], id_str, key))
                        found += 1
            idx += 1
        return response

    def get_most_retweeted_media(self, n=10) -> List[Tuple[int, str, int]]:
        rt_counts = list(self.retweet_cache.keys())
        rt_counts.sort(reverse=True)
        found = 0
        idx = 0
        all_found_media = []
        response = []
        while found < n:
            tmp_list = self.retweet_cache[rt_counts[idx]]
            for key in tmp_list:
                id_str = self.line_to_id[key]
                if type(key) is int:
                    tweet = self.fetch_by_position(key)
                else:
                    tweet: TweetAnalyzer = self.fetch_by_id(id_str)
                if type(tweet) is TweetAnalyzer:
                    if tweet.hasMedia:
                        new_m = False
                        for m in tweet.media:
                            if m.id not in all_found_media:
                                all_found_media.append(m.id)
                                response.append((rt_counts[idx], m.id, m))
                                new_m = True
                        if new_m:
                            found += 1
            idx += 1
        return response

    def fetch_by_id(self, tweet_id: Union[str, int]) -> Union[TweetAnalyzer, None]:
        assert type(tweet_id) is int or type(
            tweet_id) is str, "Invalid tweet_id data type"
        if type(tweet_id) is not str:
            tweet_id = str(tweet_id)
        if tweet_id in self.id_to_line.keys():
            key = self.id_to_line[tweet_id][-1]
            tweet = self.fetch_by_position(int(key))
            if type(key) is int:
                return tweet
            else:
                if tweet.id == tweet_id:
                    return tweet
                else:
                    return self.fetch_by_id_helper(tweet_id, tweet)
        return None

    def fetch_by_id_helper(self, tweet_id: str, tweet: TweetAnalyzer) -> TweetAnalyzer:
        if tweet.isRetweet:
            if tweet.retweeted_status.id == tweet_id:
                return tweet.retweeted_status
            else:
                output = self.fetch_by_id_helper(
                    tweet_id, tweet.retweeted_status)
                if output is not None:
                    return output
        if tweet.isQuote:
            if tweet.quoted_status.id == tweet_id:
                return tweet.quoted_status
            else:
                output = self.fetch_by_id_helper(
                    tweet_id, tweet.retweeted_status)
                if output is not None:
                    return output
        return None

    def fetch_by_position(self, lineNumber: int) -> TweetAnalyzer:
        """
        Lines are 1 indexed
        """
        if lineNumber in self.jl_cache.keys():
            # Send to back of the line of FIFO
            self.cache_list.remove(lineNumber)
            self.cache_list.append(lineNumber)
            return self.jl_cache[lineNumber]

        with open(self.filename, 'r') as handler:
            try:
                for _ in range(lineNumber-1):
                    next(handler)
                tweet = TweetAnalyzer(
                    handler.readline().strip(), self.only_local_media)
                self.update_caches(lineNumber, tweet)
                return tweet
            except Exception as e:
                print("Error:", e)
                print("Coult not fetch that line from Jsonl.")
                return None

    def update_caches(self, key, tweet, use_quotes=False):
        """
        Ricky Renuncia data from 2019 does not have quote count as this feature was introduce in 2020 by Twitter.
        By default this caches will not be updated
        """
        self.jl_cache.update({key: tweet})
        if tweet.id not in self.id_to_line.keys():
            self.id_to_line.update({tweet.id: [key, ]})
        else:
            if key not in self.id_to_line[tweet.id]:
                self.id_to_line[tweet.id].append(key)
        self.line_to_id.update({key: tweet.id})

        if tweet.retweetCount in self.retweet_cache.keys():
            if key not in self.retweet_cache[tweet.retweetCount]:
                self.retweet_cache[tweet.retweetCount].append(key)
        else:
            self.retweet_cache[tweet.retweetCount] = [key, ]
        self.cache_list.append(key)
        if len(self.cache_list) > self.CACHE_SIZE:
            oldkey = self.cache_list[0]
            self.cache_list = self.cache_list[1:]
            self.jl_cache.pop(oldkey, None)
        if use_quotes:
            if tweet.quoteCount in self.retweet_cache.keys():
                if key not in self.retweet_cache[tweet.quoteCount]:
                    self.retweet_cache[tweet.quoteCount].append(key)
            else:
                self.retweet_cache[tweet.quoteCount] = [key, ]

    @staticmethod
    def retrieveDict(tweet: TweetAnalyzer, key: int) -> dict:
        return {
            'id': tweet.data['id'],
            'id_str': tweet.data['id_str'],
            'user': {
                'id': tweet.data['user']['id'],
                'id_str': tweet.data['user']['id_str'],
            },
            'jsonl_key': key,
        }

    def orderedListGeneration(self, reset: bool):
        metadata_file = os.path.join(os.path.dirname(
            self.filename), ".multiple_sorts_" + os.path.basename(self.filename)+".pkl")
        print(metadata_file)
        if os.path.isfile(metadata_file) and not reset:
            print("Loading Backup")
            meta = pickle.load(open(metadata_file, 'rb'))
            self.retweetOf = meta["retweeted_urls"]
            self.quoteOf = meta["quoted_urls"]
            self.retweet_cache = meta["retweet_counts"]
            self.line_to_id = meta["line_to_id"]
            self.id_to_line = meta["id_to_line"]
        else:
            print("Creating Lists")
            key = 0
            print(self.filename)
            with open(self.filename, 'r') as handler:

                while True:
                    key += 1
                    if key % 200000 == 0:
                        print("Finished:", key)
                    try:
                        tweet = TweetAnalyzer(
                            handler.readline().strip(), localMedia=self.only_local_media)
                    except Exception as e:
                        print(e)
                        print("Could not create tweet")
                        print(f"Last line processed = {key-1}")
                        self.LAST_CONTENT_LINE = key-1
                        break
                    self.ordered_helper(tweet, key)

            pickle.dump({"retweeted_urls": self.retweetOf, "quoted_urls": self.quoteOf, "retweet_counts": self.retweet_cache,
                        "id_to_line": self.id_to_line, "line_to_id": self.line_to_id}, open(metadata_file, "wb"))
        # print(str(self.retweetOf)[:200])
        # print(str(self.quoteOf)[:200])
        # print(str(self.retweet_cache)[:200])

    def ordered_helper(self, tweet, key: Union[int, float]):
        if tweet.id not in self.id_to_line.keys():
            self.id_to_line.update({tweet.id: [key, ]})
        else:
            if key not in self.id_to_line[tweet.id]:
                self.id_to_line[tweet.id].append(key)
        if type(key) is int or type(key) is float:
            self.line_to_id.update({key: tweet.id})
        if tweet.isRetweet:
            if tweet.retweeted_status.id not in self.retweetOf.keys():
                self.retweetOf[tweet.retweeted_status.id] = 1
            else:
                self.retweetOf[tweet.retweeted_status.id] += 1
            self.ordered_helper(tweet.retweeted_status, key+0.01)

        if tweet.isQuote:
            if tweet.quoted_status.id not in self.quoteOf.keys():
                self.quoteOf[tweet.quoted_status.id] = 1
            else:
                self.quoteOf[tweet.quoted_status.id] += 1
            self.ordered_helper(tweet.quoted_status, key+0.0001)
        # retrieve_dict = TweetJLAnalyzer.retrieveDict(tweet, key)
        # Define a minimal retweetCount for including in retweet_cache
        if tweet.retweetCount > self.MIN_RETWEET_COUNT and not tweet.isRetweet:
            if tweet.retweetCount in self.retweet_cache.keys():
                self.retweet_cache[tweet.retweetCount].append(key)
            else:
                self.retweet_cache[tweet.retweetCount] = [key, ]

    def head(self, n: int = 5, skip: int = 0, sep="\n\n"):
        assert n > 0, "Value of n is not valid, positive integer required."
        assert skip >= 0, "Value of skip is not valid, non-negative integer required."
        output: str = ""
        with open(self.filename, 'r') as handler:
            for _ in range(skip):
                try:
                    rline = handler.readline()
                except:
                    break
            for _ in range(n):
                try:
                    rline = handler.readline().strip()
                    line = TweetAnalyzer(rline, self.only_local_media)
                    output += str(line) + sep
                    # output += rline +"\n\n"
                except Exception as e:
                    print(type(e))
                    print(e.args)
                    print(e)
                    break
        return output

    def headRetweeted(self, n: int = 5, skip: int = 0):
        assert n > 0, "Value of n is not valid, positive integer required."
        assert skip >= 0, "Value of skip is not valid, non-negative integer required."
        output: str = ""
        with open(self.filename, 'r') as handler:
            for _ in range(skip):
                try:
                    rline = handler.readline()
                except:
                    break
            count = 0
            while n > count:
                try:
                    if count >= n:
                        break
                    rline = handler.readline().strip()
                    line = TweetAnalyzer(rline, self.only_local_media)
                    if line.isRetweet:
                        output += str(line) + "\n\n"
                        # output += rline +"\n\n"
                        count += 1
                except Exception as e:
                    print(type(e))
                    print(e.args)
                    print(e)
                    break
        return output
