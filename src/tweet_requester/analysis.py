import json
from typing import Union, List


class TweetMedia:
    def __init__(self, data: dict, source_tweet=None):
        self.data = data
        try:
            self.id: str = data["id_str"]
        except:
            try:
                self.id: str = data["id"]
            except:
                raise
        self.source_tweet: Union[str, None] = source_tweet

    def mtype(self) -> str:
        return self.data["type"]

    def url(self) -> str:
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
        """This class facilitates accessing values from a tweet data dictionary.

        Args:
            data (Union[str, dict]): Tweet Data in dictionary or JSON format.
            localMedia (bool, optional): Include media from reference tweets as local. Defaults to True.
        """
        self.data = data
        self.onlyLocalMedia = localMedia
        if type(self.data) is str:
            self.data = json.loads(self.data)
        self.extractMeta()

    def extractMeta(self):
        """Upon receiving the data dictionary extracts multiple facts from it.
        """
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
        self.retweetCount: int = int(self.data.get("retweet_count", 0))
        self.quoteCount: int = int(self.data.get("quote_count", 0))
        self.favoriteCount: int = int(self.data.get("favorite_count", 0))
        if not self.onlyLocalMedia:
            self._hasMedia()
        self._hasLocalMedia()

    def isBasedOn(self) -> str:
        """Returns the Tweet ID of the tweet it references.
        For retweets returns the retweeted tweet even if 
        another tweet is quoted inside the original.

        Returns:
            str: Tweet ID of original tweet
        """
        isBasedOn = ""
        if self.isRetweet:
            isBasedOn = self.retweeted_status.id
        elif self.isQuote:
            isBasedOn = self.quoted_status.id
        return isBasedOn

    def language(self) -> Union[str, None]:
        """Extracts language suggested by Twitter.
        A value of "und" is Twitter default value for undetermined language.

        Returns:
            Union[str, None]: [description]
        """
        # Use default "und" used by Twitter
        lang = self.data.get("lang", "und")
        return lang if lang != "und" and type(lang) is str else None

    def _hasMedia(self):
        """Part of initialization. Sets the value for self.hasMedia and
        calls self.extractMedia() method.
        """
        self.hasMedia = 'media_url_https' in str(
            self.data) or 'media_url' in str(self.data)
        self.extractMedia()

    def text(self) -> str:
        """Extracts the text of the tweet. Returns short version of full version missing.

        Returns:
            str: Text of the tweet (short version if long not available)
        """
        try:
            return self.data["full_text"]
        except Exception as _:
            return self.data.get("text", "")

    def _hasLocalMedia(self):
        """Part of initialization. Sets the value for self.hasLocalMedia,
        sets self.hasMedia if not previously set and calls self.extractMedia() method.
        """
        self.hasLocalMedia = 'media_url_https' in str(self.data['entities']) or 'media_url' in str(self.data['entities']) or 'media_url_https' in str(
            self.data.get('extended_entities', {})) or 'media_url' in str(self.data.get('extended_entities', {}))
        # If hasMedia has not been set before
        if not hasattr(self, "hasMedia"):
            self.hasMedia = self.hasLocalMedia
        self.extractMedia(recursive=False)

    def extractMedia(self, recursive: bool = True):
        """Recursively or locally appends `TweetMedia`, `TweetPhoto` and `TweetVideo`
        objects into a list stored at `self.media`.

        Args:
            recursive (bool, optional): boolean that determines if media lookup should 
                dive into the quoted and retweeted tweet statuses. Defaults to True.
        """
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

    def url(self) -> str:
        """Creates a URL to the tweet using only the tweet id.

        Returns:
            str: URL using template f"https://twitter.com/any_user/status/{self.id}"
        """
        return f"https://twitter.com/any_user/status/{self.id}"

    def urlByIDs(self) -> str:
        """Creates a URL to the tweet using both the tweet id and user id.

        Returns:
            str: URL using template f"https://twitter.com/{self.user_id}/status/{self.id}"
        """
        return f"https://twitter.com/{self.user_id}/status/{self.id}"

    def _urlQuotedTweet(self) -> str:
        """Helper method for self._isQuote method.
        TODO: Update it to use the same templates as the urlByIDs method.
        Returns:
            str: URL of Quoted Tweet or "Not applicable"
        """
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
        """Helper method for self._isRetweet method.
        TODO: Update it to use the same templates as the urlByIDs method.
        Returns:
            str: URL of Quoted Tweet or "Not applicable"
        """
        if self.isRetweet:
            return f"https://twitter.com/{self.ot_user_id}/status/{self.ot_id}"
        return "Not applicable"

    def _isRetweet(self):
        """Part of initialization, Sets the `isRetweet` and urlOriginalTweet
        attributes.
        TODO: Use `None` for failure.
        """
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
        """Part of initialization, Sets the `iQuote` and urlQuotedTweet
        attributes.
        TODO: Use `None` for failure.
        """
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
        """Extracts user mentions from the data dictionary.

        Returns:
            List[dict]: User mentions in their original format.
        """
        entities: dict = self.data.get("entities", {})
        return entities.get("user_mentions", [])

    def hashtags(self) -> List[dict]:
        """Extracts hashtags from the data dictionary.

        Returns:
            List[dict]: Hashtags in their original format.
        """
        entities: dict = self.data.get("entities", {})
        return entities.get("hashtags", [])

    def __str__(self) -> str:
        """Method to allow a print out of the tweet.

        Returns:
            str: Print out of the tweet with sum metadata.
        """
        output: str = f"ID: {self.id}\nText: {self.text()}\nURL: {self.urlByIDs()}\nRetweet:{str(self.isRetweet)}\nOriginal Tweet URL: {self.urlOriginalTweet}\nQuotes:{str(self.isQuote)}\nQuoted Tweet URL: {self.urlQuotedTweet}\nHas Media={str(self.hasMedia)}\nHas Local Media={str(self.hasLocalMedia)}\nMedia={str([str(m) for m in self.media])}"
        return output

    @staticmethod
    def compare_by_favorite_count(set: bool = True):
        TweetAnalyzer._favorite_quoteCount = set

    @staticmethod
    def compare_by_retweet_count(set: bool = True):
        TweetAnalyzer._favorite_quoteCount = not set

    def _effective_size(self) -> int:
        """Helper function for comparisons.
        The class attribute `TweetAnalyzer._favorite_quoteCount` 
        controls if retweetCount or favoriteCount is used.

        Returns:
            int: 0, retweetCount or quoteCount.
        """
        if self.isRetweet:
            return 0
        if getattr(TweetAnalyzer, "_favorite_quoteCount", False):
            return self.favoriteCount
        else:
            return self.retweetCount

    def __lt__(self, other: "TweetAnalyzer") -> bool:
        return self._effective_size() < other._effective_size()

    def __le__(self, other: "TweetAnalyzer") -> bool:
        return self._effective_size() == other._effective_size() or self < other

    def __gt__(self, other: "TweetAnalyzer") -> bool:
        return not self.__le__(other)

    def __ge__(self, other: "TweetAnalyzer"):
        return not self.__lt__(other)

    def __eq__(self, other: "TweetAnalyzer"):
        return self._effective_size() == other._effective_size()
