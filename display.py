from os import environ
from sqlite3.dbapi2 import Cursor
from typing import Tuple, List, Union
from datetime import datetime
from google.cloud.translate_v3.types.translation_service import TranslateTextResponse
from proto.fields import RepeatedField
from tweet_rehydrate.analysis import TweetAnalyzer, json
from tweet_rehydrate.session import TSess
import ipywidgets as widgets
from IPython.core.display import display, HTML, clear_output, Javascript
import sqlite3
from os.path import isfile
from shutil import move
from time import time
from enum import Enum
from queue import Queue
from google.cloud import translate
from google.oauth2 import service_account
import logging

"""
This module objective is to generate an interactive store for
interacting with twitter records inside a jupyter notebook.
"""


def prepare_google_credentials(credentials_file="")\
        -> Union[service_account.Credentials, None]:
    # If not specified try to get credentials file from environment.
    try:
        if not credentials_file:
            credentials_file = environ.get(
                "GOOGLE_APPLICATION_CREDENTIALS", "")
        assert credentials_file
        google_credentials = service_account.Credentials.\
            from_service_account_file(credentials_file)
        return google_credentials
    except Exception as _:
        return None


PHOTO_MEDIA_TYPES = ["photo", "animated_gif"]
VIDEO_MEDIA_TYPES = ["video"]
AUDIO_MEDIA_TYPES = ["audio"]
ALL_MEDIA_TYPES = PHOTO_MEDIA_TYPES + VIDEO_MEDIA_TYPES + AUDIO_MEDIA_TYPES


class PROCESSING_STAGES(Enum):
    UNPROCESSED = 0
    REVIEWING = 1
    FINALIZED = 2
    REJECTED = 3
    UNAVAILABLE_EMBEDING = 4
    RETWEET = 5
    PREPROCESSED = 6


class TweetInteractiveClassifier(TweetAnalyzer):
    def __init__(self, tweet_id, session: TSess):
        self._session = session
        data, code = session.load_tweet_11(tweet_id)
        data = json.loads(data)[0]
        assert code == 200, "Could not get response!"
        super().__init__(data=data, localMedia=False)
        # Loading when required ( display or _repr_html_ )
        self.oEmbededCached = ""

    def load_oEmbed(self):
        self.oEmbededCached = self.oEmbeded()

    def oEmbeded(self) -> str:
        base_url = "https://publish.twitter.com/oembed"
        params = {"url": f"https://twitter.com/Interior/status/{self.id}"}
        response, code = self._session.load_request(
            base_url=base_url, params=params, is_tweet=False)
        data: dict = json.loads(response)
        if type(data) is dict:
            return data.get("html", "<h1>Failed to get embeding.</h1>")
        return "<h1>Failed to get embeding.</h1>"

    def display(self):
        if not self.oEmbededCached:
            self.load_oEmbed()
        assert type(self.oEmbededCached) is str, "Data is not string."
        display(HTML(self.oEmbededCached))

    def _repr_html_(self):
        if not self.oEmbededCached:
            self.load_oEmbed()
        return self.oEmbededCached


class JsonLInteractiveClassifier:
    _delay = 5.0
    _MAX_RETRIES = 30

    def __init__(
        self, tweet_ids_file: str, session: TSess,
        pre_initialized=False, sqlite_db: str = "", **kwargs
    ):
        self.google_credentials: service_account.Credentials = \
            kwargs.get("google_credentials", None)
        self.target_language_code = kwargs.get("target_language_code", "en")
        if self.google_credentials:
            self.translate_client = translate.TranslationServiceClient(
                credentials=self.google_credentials,
            )
        else:
            self.translate_client = None
        self.tweet_session = session
        self._last_submit = time()
        self.db = None
        self.current_tweet = None
        self.current_tweet_id = None
        self._next_tweet_id = Queue()
        if not pre_initialized:
            self.initialize(tweet_ids_file)
        else:
            self.original_filename = None
            self.sqlite_filename = sqlite_db
            assert sqlite_db != '', "Specify a filename to load the database."
            assert isfile(sqlite_db), "The given sqlite filename was \
                not found. Verify the name or path."
            self.connect()

        # Prepare Widgets
        self.description = widgets.Textarea
        self.button_reject = widgets.Button(description="Reject")
        self.button_reject.on_click(self.reject_current)
        self.button_skip = widgets.Button(description="Skip")
        self.button_skip.on_click(self.skip_current)
        self.embeding = widgets.HTML()
        self.javascript = Javascript(
            url="https://platform.twitter.com/widgets.js")
        if kwargs.get("start_inmediately", False):
            self.StartEvaluations()
    
    def get_database_version(self):
        self.connect()
        cur = self.cursor()

        cur.execute('''
            SELECT version 
            FROM db_update 
            ORDER BY timestamp DESC
            LIMIT 1''')
        
        rows = cur.fetchall()
        cur.close()
        self.close()
        for row in rows:
            return float(row[0])
        return 0

    def update_database_v01_v02(self, dateCreated: float, git_commit: str = ""):
        if self.get_database_version() >= 0.2:
            logging.warning(f"Database version is {self.get_database_version()} >= 0.2. Skipping update.")
            return
        self.connect()
        cur = self.cursor()

        cur.execute('''CREATE TABLE tweet_user_detail (
            tweet_id TEXT,
            description TEXT,
            is_meme INTEGER,
            has_slang INTEGER,
            PRIMARY KEY("tweet_id"));''')
        cur.execute("""CREATE INDEX tweet_user_detail_has_slang
            ON tweet_user_detail(has_slang);
        """)
        cur.execute("""CREATE INDEX tweet_user_detail_is_meme
            ON tweet_user_detail(is_meme);
        """)
        self.commit()

        cur.execute('''CREATE TABLE tweet_auto_detail (
            tweet_id TEXT,
            isBasedOn TEXT,
            identifier TEXT,
            url TEXT,
            dateCreated FLOAT,
            datePublished FLOAT,
            user_id TEXT,
            has_media INTEGER,
            language TEXT,
            retweetCount INTEGER,
            quoteCount INTEGER,
            text TEXT,
            PRIMARY KEY("tweet_id"));''')
        cur.execute("""CREATE INDEX tweet_auto_detail_has_media
            ON tweet_auto_detail(has_media);
        """)
        cur.execute("""CREATE INDEX tweet_auto_detail_quoteCount
            ON tweet_auto_detail(quoteCount);
        """)
        cur.execute("""CREATE INDEX tweet_auto_detail_retweetCount
            ON tweet_auto_detail(retweetCount);
        """)
        self.commit()

        cur.execute('''CREATE TABLE tweet_user (
            user_id TEXT,
            user_url TEXT,
            screen_name TEXT,
            PRIMARY KEY("user_id"));''')
        self.commit()

        cur.execute('''CREATE TABLE tweet_match_media(
            tweet_id TEXT,
            media_id TEXT,
            PRIMARY KEY("tweet_id", "media_id"));''')
        self.commit()

        cur.execute('''CREATE TABLE tweet_media (
            media_id TEXT,
            media_url TEXT,
            type TEXT,
            PRIMARY KEY("media_id", "media_url"));''')
        self.commit()

        cur.execute('''
        CREATE TABLE db_update (
            version REAL,
            git_commit TEXT,
            timestamp REAL,
            PRIMARY KEY("version"));''')

        cur.execute(
            """
            INSERT INTO db_update
            (
                "version",
                "git_commit",
                "timestamp"
            ) VALUES (?, ?, ?);""",
            (0.2, git_commit, datetime.now().timestamp())
        )
        self.commit()

        cur.execute("""
            SELECT 
                tweet_id,
                description,
                is_meme,
                has_slang
            FROM tweet_detail;""")
        rows: List[Tuple[str, str, str, str]] = cur.fetchall()
        cur.close()

        for user_detail in rows:
            tweet_id = user_detail[0]
            tweet = TweetInteractiveClassifier(
                tweet_id, session=self.tweet_session)
            self.save_user_details(user_detail)

            self.save_auto_details(tweet, dateCreated=dateCreated)

            self.finalize_tweet(tweet_id=tweet.id)

    def initialize(self, tweet_ids_file: str):
        self.initialize_v2(tweet_ids_file)

    def initialize_v2(self, tweet_ids_file: str):
        """Prepares a new SQLite database for usage.
        """
        self.original_filename = tweet_ids_file
        self.sqlite_filename = "." + tweet_ids_file + ".db"
        if isfile(self.sqlite_filename):
            try:
                self.connect()
                return
            except:
                # Backup Old DB File
                move(self.sqlite_filename, self.sqlite_filename+"."+str(time()))
        # Connect and initialize tables
        self.connect()

        cur = self.db.cursor()

        cur.execute(
            'CREATE TABLE tweet (tweet_id TEXT, state INTEGER, PRIMARY KEY("tweet_id") );'
        )
        cur.execute("""CREATE INDEX tweet_state ON tweet (state);""")

        cur.execute('''CREATE TABLE tweet_user_detail (
            tweet_id TEXT,
            description TEXT,
            is_meme INTEGER,
            has_slang INTEGER,
            PRIMARY KEY("tweet_id"));''')
        cur.execute("""CREATE INDEX tweet_user_detail_has_slang
            ON tweet_user_detail(has_slang);
        """)
        cur.execute("""CREATE INDEX tweet_user_detail_is_meme
            ON tweet_user_detail(is_meme);
        """)
        self.commit()

        cur.execute('''CREATE TABLE tweet_auto_detail (
            tweet_id TEXT,
            isBasedOn TEXT,
            identifier TEXT,
            url TEXT,
            dateCreated FLOAT,
            datePublished FLOAT,
            user_id TEXT,
            has_media INTEGER,
            language TEXT,
            retweetCount INTEGER,
            quoteCount INTEGER,
            text TEXT,
            PRIMARY KEY("tweet_id"));''')
        cur.execute("""CREATE INDEX tweet_auto_detail_has_media
            ON tweet_auto_detail(has_media);
        """)
        self.commit()

        cur.execute('''CREATE TABLE tweet_user (
            user_id TEXT,
            user_url TEXT,
            screen_name TEXT,
            PRIMARY KEY("user_id"));''')
        self.commit()

        cur.execute('''CREATE TABLE tweet_match_media(
            tweet_id TEXT,
            media_id TEXT,
            PRIMARY KEY("tweet_id", "media_id"));''')
        self.commit()

        cur.execute('''CREATE TABLE tweet_media (
            media_id TEXT,
            media_url TEXT,
            type TEXT,
            PRIMARY KEY("media_id", "media_url"));''')
        self.commit()

        # Traduction Cache in DB
        cur.execute('''CREATE TABLE tweet_traduction (
            tweet_id TEXT,
            target_language_code TEXT,
            traduction TEXT,
            PRIMARY KEY( "target_language_code", "tweet_id"  ));''')
        self.commit()

    def initialize_v1(self, tweet_ids_file: str):
        """Prepares a new SQLite database for usage.
        """
        self.original_filename = tweet_ids_file
        self.sqlite_filename = "." + tweet_ids_file + ".db"
        if isfile(self.sqlite_filename):
            try:
                self.connect()
                return
            except:
                # Backup Old DB File
                move(self.sqlite_filename, self.sqlite_filename+"."+str(time()))
        # Connect and initialize tables
        self.connect()

        cur = self.cursor()

        cur.execute(
            'CREATE TABLE tweet (tweet_id TEXT, state INTEGER, PRIMARY KEY("tweet_id") );'
        )
        cur.execute("""CREATE INDEX tweet_state ON tweet (state);""")
        # Replaced Unique Index with PRIMARY KEY at creation
        # cur.execute(
        #     """CREATE UNIQUE INDEX tweet_id_index ON tweet (tweet_id);""")
        self.db.commit()

        with open(self.original_filename, "r") as source:
            n = 0
            commits = 0
            commit_loop = 5000
            records = []
            for k in source:
                k = str(k).strip()
                if k != "":
                    records.append((k, 0))
                    n += 1
                    if n % commit_loop == 0:
                        commits += 1
                        cur.executemany(
                            f"INSERT INTO tweet VALUES (?, ?);", records)
                        self.db.commit()
                        records = []
                        if commits >= 100:
                            break

                else:
                    break
            if len(records) > 0:
                cur.execute(f"INSERT INTO tweet VALUES (?, ?);", records)
                self.commit()
                records = []

        cur.execute('''CREATE TABLE tweet_detail (
            tweet_id TEXT,
            has_media INTEGER,
            description TEXT,
            is_meme INTEGER,
            language TEXT,
            has_slang INTEGER,
            PRIMARY KEY("tweet_id"));''')
        cur.execute("""CREATE INDEX tweet_detail_has_media
            ON tweet_detail(has_media);
        """)
        self.commit()

        # Traduction Cache in DB
        cur.execute('''CREATE TABLE tweet_traduction (
            tweet_id TEXT,
            target_language_code TEXT,
            traduction TEXT,
            PRIMARY KEY( "target_language_code", "tweet_id"  ));''')
        self.commit()

        cur.close()

    def connect(self):
        self.close()
        self.db = sqlite3.connect(self.sqlite_filename)

    def close(self):
        if self.db is not None:
            try:
                self.db.close()
            except Exception as error:
                # If not None it should be connected
                # Still ignore and try to connect
                logging.warning(error)
                logging.warning("Could not close connection, keep going.")
            self.db = None

    def cursor(self, *args, **kwargs):
        assert self.db is not None, "Not connected to sqlite DB!"
        return self.db.cursor(*args, **kwargs)

    def commit(self, *args, **kwargs):
        assert self.db is not None, "Not connected to sqlite DB!"
        return self.db.commit(*args, **kwargs)

    def display(self):
        pass

    def add_to_queue(self, tweet_id: str, cur: Cursor):
        """add_to_queue method is only called from check_retweet method
        Adds tweet_id to tweet table if missing. Skips from queue if already
        processed.
        """
        cur.execute(
            """SELECT state FROM tweet WHERE tweet_id = ?;""", (tweet_id,))
        rows = cur.fetchall()
        if len(rows) > 0:
            # If state is UNPROCESSED add to queue
            state = rows[0][0]
            if state == 0:
                self._next_tweet_id.put(tweet_id)
            else:
                logging.debug(f"Already Processed: {tweet_id}")
        else:
            # If not in table add to table and queue
            cur.execute(
                "INSERT OR REPLACE INTO tweet(tweet_id, state) VALUES(?, ?);",
                (tweet_id, PROCESSING_STAGES.UNPROCESSED.value))
            self.commit()
            self._next_tweet_id.put(tweet_id)

    def check_retweet(self):
        """Checks if tweet has original content."""
        load_next = False
        self.connect()
        cur = self.cursor()
        if self.current_tweet.isQuote:
            assert not self.current_tweet.isRetweet, \
                "Cannot be both quote and retweet!"
        if self.current_tweet.isQuote:
            self.add_to_queue(self.current_tweet.quoted_status.id, cur)
        if self.current_tweet.isRetweet:
            load_next = True
            self.add_to_queue(self.current_tweet.retweeted_status.id, cur)
            cur.execute("""
                UPDATE tweet 
                SET state = ? 
                WHERE tweet_id = ?;""",
                        (
                            PROCESSING_STAGES.RETWEET.value,
                            self.current_tweet_id,
                        )
                        )
            self.commit()
        cur.close()
        self.close()
        if load_next:
            logging.debug("Skipping Retweet!")
            self.load_next_tweet()

    def StartEvaluations(
        self,
        stages: List[PROCESSING_STAGES] = [
            PROCESSING_STAGES.PREPROCESSED
        ]
    ):
        """
        Wrapper around display_another method that has a goodbye message.

        param:
            self
        return:
            None
        """
        self.display_another(stages=stages)
        clear_output()
        display(HTML('<h1 class="alert alert-success">Thank you!</h1><h2 class="alert alert-info">Exited from evaluation</h2>'))

    def load_next_tweet(
        self,
        stages: List[PROCESSING_STAGES] = [
            PROCESSING_STAGES.UNPROCESSED,
            PROCESSING_STAGES.PREPROCESSED
        ]
    ) -> Union[TweetInteractiveClassifier, None]:
        """
        Performs multiple actions to get the next useful tweet.

        param:
            self
        return:
            self.current_tweet (TweetInteractiveClassifier | None)
        """
        # If queue is empty add more values.
        if self._next_tweet_id.empty():
            self.load_random_tweets(stages=stages)
            if self._next_tweet_id.empty():
                # Return no current tweet as no more can be found.
                self.current_tweet_id = None
                self.current_tweet = None
                logging.info("No more tweets to process.")
                return None

        # Get next tweet_id from Queue and clear current_tweet object
        self.current_tweet_id: str = self._next_tweet_id.get()
        self.current_tweet = None

        # Get tweet state from DB
        self.connect()
        cur = self.cursor()
        cur.execute(
            """SELECT state FROM tweet WHERE tweet_id = ?;""", (self.current_tweet_id,))
        rows: List[Tuple[int]] = cur.fetchall()

        cur.close()
        self.close()

        # Tweet should always be added to the table before the queue
        try:
            state_value = rows[0][0]
        except:
            logging.warning(
                f"Tweet{self.current_tweet_id} not in table!!! Trying to add.")
            try:
                self.add_to_queue(self.current_tweet_id)
                state_value = PROCESSING_STAGES.UNPROCESSED.value
            except Exception as err:
                logging.error(err)
                raise

        if PROCESSING_STAGES(state_value) in stages :
            # Update or insert with state Reviewing.
            self.connect()
            cur = self.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO tweet(tweet_id, state) VALUES(?, ?);",
                (self.current_tweet_id, PROCESSING_STAGES.REVIEWING.value))
            self.commit()
            cur.close()
            self.close()
            try:
                self.current_tweet = TweetInteractiveClassifier(
                    self.current_tweet_id, session=self.tweet_session)
            except:
                self.skip_failed()
                self.current_tweet = None
                self.load_next_tweet()
            self.check_retweet()
        else:
            # Try again
            logging.info(f"Tweet state: {state_value}. Loading Next Tweet.")
            self.load_next_tweet()

        return self.current_tweet

    def load_random_tweets(
        self, n: int = 5,
        stages: List[PROCESSING_STAGES] = [
            PROCESSING_STAGES.UNPROCESSED,
            PROCESSING_STAGES.PREPROCESSED
        ]
    ):
        self.connect()
        cur = self.cursor()
        slots = ""
        inputs = []
        for stage in stages:
            slots += "?, "
            inputs.append(stage.value)
        slots = slots[:-2]
        inputs.append(n)
        inputs = tuple(inputs)
        cur.execute(
            f"""SELECT tweet_id FROM tweet WHERE state in ({slots}) ORDER BY RANDOM() LIMIT ?;""",
            inputs)
        rows: List[Tuple[str]] = cur.fetchall()
        for (tweet_id,) in rows:
            self._next_tweet_id.put(tweet_id)

    def load_random_tweet(self):
        self.connect()
        cur = self.cursor()
        cur.execute(
            """SELECT tweet_id FROM tweet WHERE state = 0 ORDER BY RANDOM() LIMIT 1;""")
        rows: List[Tuple[str]] = cur.fetchall()
        try:
            assert len(rows) > 0, "No tweets found"
            self.current_tweet_id = rows[0][0]
            cur.execute(f"""
            UPDATE tweet 
            SET state = 1 
            WHERE tweet_id = ?;""", (self.current_tweet_id,))
            self.commit()
            self.close()
        except:
            self.current_tweet_id = None
            logging.debug(f"Set self.current_tweet_id='{self.current_tweet_id}'")
        if self.current_tweet_id is not None:
            try:
                self.current_tweet = TweetInteractiveClassifier(
                    self.current_tweet_id, session=self.tweet_session)
            except:
                self.skip_failed()
                self.load_next_tweet()
        else:
            self.current_tweet = None

    @staticmethod
    def get_details(tweet: TweetInteractiveClassifier) -> Tuple:
        description = input("Enter a short description:\n")
        # has_media = tweet.hasMedia
        has_local_media = tweet.hasLocalMedia
        has_slang = "?"
        while has_slang[0] not in "ynYN":
            has_slang = input("Does the message include slang?\n(Y/N)")
            if type(has_slang) is not str:
                has_slang = "?"
                continue
        if has_slang[0] in "yY":
            has_slang = True
        else:
            has_slang = False

        is_meme = "?"
        if has_local_media:
            while is_meme[0] not in "ynYN":
                is_meme = input("Is the image a meme?\n(Y/N)")
                if type(is_meme) is not str:
                    is_meme = "?"
            if is_meme[0] in "yY":
                is_meme = True
            else:
                is_meme = False
        else:
            is_meme = False
        language = tweet.language()

        return tweet.id, has_local_media, description, is_meme, language, has_slang

    @staticmethod
    def get_user_details(tweet: TweetInteractiveClassifier) -> Tuple:
        description = input("Enter a short description:\n")
        # has_media = tweet.hasMedia
        has_slang = "?"
        while has_slang[0] not in "ynYN":
            has_slang = input("Does the message include slang?\n(Y/N)")
            if type(has_slang) is not str:
                has_slang = "?"
                continue
        if has_slang[0] in "yY":
            has_slang = True
        else:
            has_slang = False

        is_meme = "?"
        if tweet.hasMedia:
            while is_meme[0] not in "ynYN":
                is_meme = input("Is the image a meme?\n(Y/N)")
                if type(is_meme) is not str:
                    is_meme = "?"
            if is_meme[0] in "yY":
                is_meme = True
            else:
                is_meme = False
        else:
            is_meme = False

        return tweet.id, description, is_meme, has_slang

    def save_details(self, details: Tuple[str, bool, str, bool, Union[str, None], bool]):
        self.connect()
        cur = self.cursor()
        cur.execute(
            f"""INSERT INTO tweet_detail
            (
                "tweet_id", "has_media", "description",
                "is_meme", "language", "has_slang"
            )
            VALUES (?, ?, ?, ?, ?, ?);""",
            details
        )
        self.commit()
        cur.execute(
            "UPDATE tweet \
            SET state = ? \
            WHERE tweet_id = ?;",
            (PROCESSING_STAGES.FINALIZED.value, self.current_tweet_id,)
        )
        self.commit()
        cur.close()

    def save_user_details(self, details: Tuple[str, str, bool, bool]):
        self.connect()
        cur = self.cursor()
        cur.execute(
            f"""INSERT INTO tweet_user_detail
            (
                "tweet_id",
                "description",
                "is_meme",
                "has_slang"
            )
            VALUES (?, ?, ?, ?);""",
            details
        )
        self.commit()
        cur.close()

    def save_auto_details(
        self,
        tweet: TweetInteractiveClassifier,
        dateCreated: Union[float, datetime, None]
    ):
        """Save all details that can be extracted from the data dictionary 
        without human interaction."""
        self.connect()
        cur = self.cursor()
        if dateCreated is None:
            dateCreated = datetime.now()
        if type(dateCreated) is datetime:
            dateCreated = dateCreated.timestamp()
        try:
            datePublished: datetime = datetime.strptime(
                tweet.data.get("created_at"),
                '%a %b %d %H:%M:%S +0000 %Y'
            )
            datePublished = datePublished.timestamp()
        except Exception as err:
            logging.error(
                f"Could not generate datePublished: {tweet.data.get('created_at','MISSING')}"
            )
            logging.error(err)
            raise

        cur.execute(
            f"""INSERT INTO tweet_auto_detail
            (
                "tweet_id",
                "isBasedOn",
                "identifier",
                "url",
                "dateCreated",
                "datePublished",
                "user_id",
                "has_media",
                "language",
                "retweetCount",
                "quoteCount",
                "text"
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
            (
                tweet.id,
                tweet.isBasedOn(),
                tweet.urlByIDs(),
                tweet.url(),
                dateCreated,
                datePublished,
                tweet.user_id,
                tweet.hasMedia,
                tweet.language(),
                tweet.retweetCount,
                tweet.quoteCount,
                tweet.text()
            )
        )
        self.commit()

        cur.execute(
            f"""INSERT INTO tweet_user
            (
                "user_id",
                "user_url",
                "screen_name"
            )
            VALUES (?, ?, ?);""",
            (
                tweet.user_id,
                f"https://twitter.com/{tweet.user_screen_name}",
                tweet.user_screen_name
            )
        )
        self.commit()
        media_duplicates = 0
        media_duplicates_errors = []
        for media in tweet.localMedia:
            try:
                cur.execute(
                    """INSERT INTO tweet_media
                    (
                        "media_id",
                        "media_url",
                        "type"
                    )
                    VALUES (?, ?, ?);""",
                    (
                        media.id,
                        media.url(),
                        media.mtype()
                    )
                )
                self.commit()

                cur.execute(
                    """INSERT OR REPLACE INTO tweet_match_media
                    (
                        "tweet_id",
                        "media_id"
                    )
                    VALUES (?, ?);""",
                    (
                        tweet.id,
                        media.id
                    )
                )
                self.commit()
            except sqlite3.IntegrityError as err:
                if "unique" in str(err).lower():
                    media_duplicates += 1
                    media_duplicates_errors.append(err)
                    # logging.info(f"Duplicate Media Entity: {err}")
                else:
                    logging.error(err)
                    raise
            except Exception as err:
                logging.error(f"{media.id} - {media.mtype()} - {media.url()}")
                logging.error(err)
                selection = input("Continue?\n\tY/N: ")
                if selection.lower()[0] == "y":
                    continue
                else:
                    raise
        if media_duplicates > 0:
            logging.info(f"Found {media_duplicates} duplicates.\nLast Error: {media_duplicates_errors[-1]}")
        cur.close()

    def display_tweet(self, tweet_id, target_language_code: str = ""):
        try:
            tweet = TweetInteractiveClassifier(
                tweet_id=tweet_id,
                session=self.tweet_session
            )
        except Exception as err:
            logging.error(err)
            return

        html_content = tweet.oEmbeded()
        if target_language_code:
            text_translation = self.translate_tweet(
                tweet=tweet,
                target_language_code=target_language_code
            )
            if text_translation:
                html_content += f"<p>Translation to '{target_language_code}':</p>"
                html_content += f"<p>{text_translation}<p>"
        display(HTML(html_content))

    def display_accepted(
        self,
        per_page=5,
        page=0,
        target_language_code="en"
    ):
        self.connect()
        cur = self.cursor()
        offset = per_page * page
        cur.execute(
            """SELECT tweet_id FROM tweet
            WHERE state=? ORDER BY tweet_id LIMIT ? OFFSET ?""",
            (PROCESSING_STAGES.FINALIZED.value, per_page, offset))
        rows = cur.fetchall()
        tweet_ids = []
        for row in rows:
            tweet_ids.append(row[0])

        self.display_tweet_list(tweet_ids, target_language_code)

    def display_tweet_list(
        self,
        tweet_id_list: List[str],
        target_language_code: str = ""
    ):
        html_content = ""
        for tweet_id in tweet_id_list:
            try:
                tweet = TweetInteractiveClassifier(
                    tweet_id, self.tweet_session
                )
            except:
                html_content += f"""
                <div>Tweet {tweet_id} could not be loaded.</div>"""
                continue
            html_content += "<div>" + tweet.oEmbeded()
            if target_language_code:
                text_translation = self.translate_tweet(
                    tweet=tweet,
                    target_language_code=target_language_code
                )
                if text_translation:
                    html_content += f"<p>Translation to \
                        '{target_language_code}':<br>{text_translation}\n"
            html_content += "</div>"
        display(HTML(html_content))

    def display_another(
        self,
        stages: List[PROCESSING_STAGES] = [
            PROCESSING_STAGES.UNPROCESSED,
        ]
    ):
        while True:
            clear_output()
            # self.previous_tweet = self.current_tweet
            # self.current_tweet: TweetAnalyzer = None
            logging.info("Loading Tweet...")
            retry_count: int = 0
            self.current_tweet = None
            while self.current_tweet is None:
                retry_count += 1
                if retry_count > self._MAX_RETRIES:
                    logging.info(retry_count, "Too many missing")
                    break
                self.current_tweet = self.load_next_tweet(stages=stages)
            if not self.current_tweet:
                logging.info(f"No tweet loaded, {self.current_tweet}. Exiting")
                break
            self.current_tweet.display()
            msg = self.generate_message()

            option = input(msg)
            if option == "1":
                details = JsonLInteractiveClassifier.get_user_details(
                    self.current_tweet)
                logging.debug(f"Details: {details}")
                # sleep(2)
                self.save_user_details(details)
                self.save_auto_details(
                    self.current_tweet,
                    dateCreated=datetime.now().timestamp()
                )
                self.finalize_current()
            elif option == "2":
                self.reject_current()
            elif option == "3":
                self.skip_current()
            elif option == "4":
                self.skip_current()
                break

    def preprocess_batch(self, n:int=20):
        stages=[
            PROCESSING_STAGES.UNPROCESSED
        ]
        preload_n: int = int(n * 0.75)
        self.load_random_tweets(
            n= preload_n,
            stages=stages
        )
        count=0
        while count < n or not self._next_tweet_id.empty():
            tweet=self.load_next_tweet(stages=stages)
            self.save_auto_details(
                tweet,
                datetime.now().timestamp()
            )
            self.tweet_set_state(
                tweet.id, 
                PROCESSING_STAGES.PREPROCESSED
            )
            count+=1


    def finalize_current(self, *args, **kwargs):
        c_time = time()
        if c_time-self._last_submit > self._delay:
            self._last_submit = c_time
            self.finalize_tweet(self.current_tweet.id)

    def finalize_tweet(self, tweet_id: str):
        self.tweet_set_state(
            tweet_id,
            PROCESSING_STAGES.FINALIZED
        )

    def reject_current(self, *args, **kwargs):
        c_time = time()
        if c_time-self._last_submit > self._delay:
            self._last_submit = c_time
            self.reject_tweet(self.current_tweet.id)

    def reject_tweet(self, tweet_id: str):
        self.tweet_set_state(
            tweet_id,
            PROCESSING_STAGES.REJECTED
        )

    def tweet_set_state(self, tweet_id: str, state: PROCESSING_STAGES):
        self.connect()
        cur = self.cursor()
        cur.execute(
            """UPDATE tweet
            SET state = ?
            WHERE tweet_id = ?;""",
            (state.value, tweet_id,)
        )
        self.commit()
        cur.close()
        self.close()

    def skip_current(self, *args, **kwargs):
        c_time = time()
        if c_time-self._last_submit > self._delay:
            self._last_submit = c_time
            self.skip_tweet(self.current_tweet.id)

    def skip_tweet(self, tweet_id: str, fail=False):
        if fail:
            state = PROCESSING_STAGES.UNAVAILABLE_EMBEDING
        else:
            state = PROCESSING_STAGES.UNPROCESSED
        self.tweet_set_state(
            tweet_id,
            state
        )

    def skip_failed(self, *args, **kwargs):
        c_time = time()
        if c_time-self._last_submit > self._delay:
            self._last_submit = c_time
            self.skip_tweet(self.current_tweet_id, fail=True)

    def generate_message(self) -> str:
        msg = """
        What should we do?
            1)Accept
            2)Reject
            3)Skip
            4)Exit
        """

        # If Translator available append message
        if self.translate_client:
            text_translation = self.translate_tweet(
                self.current_tweet,
                self.target_language_code
            )
            msg = f"Translation: {text_translation}\n" + msg
        return msg

    def translate_tweet(
        self,
        tweet: TweetInteractiveClassifier,
        target_language_code: str
    ) -> str:
        if not self.translate_client or not target_language_code:
            # Return empty string if
            # target language missing or if translate client missing.
            return ""

        output = self.load_traduction(tweet.id, target_language_code)
        if output is not None:
            logging.debug(f"Cached Translation: {output}")
            return output
        else:
            output = ""

        split_text, mentions_and_hashtags = JsonLInteractiveClassifier.\
            text_to_list(tweet)
        logging.debug(str(split_text))
        logging.debug(str(mentions_and_hashtags))
        contents = JsonLInteractiveClassifier.clean_contents(split_text)
        # If something to translate
        if len(contents) > 0:
            logging.debug(contents)
            response: TranslateTextResponse = self.translate_client.\
                translate_text(
                    contents=contents,
                    target_language_code=target_language_code,
                    parent=f"projects/{self.google_credentials.project_id}",
                )

            recomposed_translation = JsonLInteractiveClassifier.lists_to_text(
                response.translations,
                split_text,
                mentions_and_hashtags
            )
            output = recomposed_translation
        self.save_tranduction(
            tweet, target_language_code, output
        )
        return output

    def load_traduction(
        self,
        tweet_id: str,
        target_language_code: str
    ) -> Union[None, str]:
        output = None
        self.connect()
        cur = self.cursor()
        cur.execute(
            """SELECT traduction FROM tweet_traduction
            WHERE tweet_id=? AND target_language_code=?;""",
            (tweet_id, target_language_code)
        )
        rows = cur.fetchall()  # Max one response due to PRIMARY KEY CONSTRAINT
        cur.close()
        for row in rows:
            output = row[0]
        return output

    def save_tranduction(
        self,
        tweet: TweetInteractiveClassifier,
        target_language_code: str,
        traduction: str
    ):
        self.connect()
        cur = self.cursor()
        cur.execute(
            "INSERT INTO tweet_traduction VALUES (?, ?, ?)",
            (tweet.id, target_language_code, traduction)
        )
        self.commit()
        cur.close()

    @staticmethod
    def clean_contents(split_text: List[str]) -> List[str]:
        contents = []
        for text in split_text:
            if text:
                contents.append(text)
        return contents

    @staticmethod
    def text_to_list(
        tweet: TweetInteractiveClassifier
    ) -> Tuple[List[str], List[dict]]:
        text = tweet.text()
        text_split = []
        tail_start = 0
        mentions_and_hashtags = JsonLInteractiveClassifier.\
            sorted_mentions_and_hashtags(tweet)
        mentions_and_hashtags
        for mh in mentions_and_hashtags:
            text_split.append(text[tail_start:mh["indices"][0]])
            tail_start = mh["indices"][1]
        text_split.append(text[tail_start:])
        return text_split, mentions_and_hashtags

    @staticmethod
    def lists_to_text(
        translations: RepeatedField, split_text: List[str], mentions_and_hashtags: List[dict]
    ) -> str:
        output = ""
        content_translations = []
        for trans in translations:
            content_translations.append(trans.translated_text)

        split_translations = []
        for idx in range(len(split_text)):
            if split_text[idx] == "":
                split_translations.append("")
            else:
                split_translations.append(content_translations.pop(0))

        while len(split_translations) > 1:
            body = split_translations.pop(0)
            mh = mentions_and_hashtags.pop(0)
            if "text" in mh.keys():
                entity = f"#{mh['text']}"
            elif "screen_name" in mh.keys():
                entity = f"@{mh['screen_name']}"
            else:
                entity = "#@!!!FAULT!!!"
            output = " ".join([
                output,
                body,
                entity
            ])
            pass
        return output + " " + split_translations[0]

    @staticmethod
    def sorted_mentions_and_hashtags(tweet: TweetInteractiveClassifier) -> List[dict]:
        from functools import cmp_to_key

        def compare(a: dict, b: dict):
            ai: int = a["indices"][0]
            bi: int = b["indices"][0]
            if ai < bi:
                return -1
            elif ai > bi:
                return 1
            else:
                return 0

        def key_func(a: dict) -> int:
            return a["indices"][0]

        m_and_h = tweet.user_mentions() + tweet.hashtags()
        m_and_h.sort(key=lambda x: x["indices"][0])
        return m_and_h
