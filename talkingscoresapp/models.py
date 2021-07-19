from django.db import models

import os
import errno
import hashlib
import requests
import logging, logging.handlers, logging.config
from talkingscores.settings import BASE_DIR, MEDIA_ROOT, STATIC_ROOT, STATIC_URL
from urllib.parse import urlparse
from urllib.request import url2pathname
import tempfile
from talkingscoreslib import Music21TalkingScore, HTMLTalkingScoreFormatter

log_format = "%(asctime)s - %(levelname)s - %(message)s"
logging.basicConfig(filename=os.path.join(*(MEDIA_ROOT, "log1.txt")), format=log_format)
logger = logging.getLogger("TSScore")
    

def hashfile(afile, hasher, blocksize=65536):
    buf = afile.read(blocksize)
    while len(buf) > 0:
        hasher.update(buf)
        buf = afile.read(blocksize)
    return hasher.hexdigest()

class TSScoreState(object):
    IDLE = "idle"
    FETCHING = "fetching"
    AWAITING_OPTIONS = "awaiting options"
    AWAITING_PROCESSING = "awaiting processing"
    PROCESSED = "processed"

class TSScore(object):
    
    # I can't seem to find a way of getting the class object in scope at this point to dynamically populate the name
    logger = logging.getLogger("TSScore")
    logger.level = logging.DEBUG
    def __init__(self, id=None, initial_state=TSScoreState.IDLE, url=None, filename=None):
        self._state = initial_state
        self.url   = url
        self.id    = id
        self.filename = filename

    def state(self):
        data_filepath = self.get_data_file_path()
        opts_filepath = data_filepath + '.opts'
        output_filepath = data_filepath + '.html'

        if not os.path.exists(data_filepath):
            return TSScoreState.FETCHING
        elif not os.path.exists(opts_filepath):
            return TSScoreState.AWAITING_OPTIONS
        elif not os.path.exists(output_filepath):
            return TSScoreState.AWAITING_PROCESSING
        else:
            return TSScoreState.PROCESSED


    def info(self):
        data_filepath = self.get_data_file_path()
        score = Music21TalkingScore(data_filepath)

        return {
            'title': score.get_title(),
            'composer': score.get_composer(),
            'time_signature': score.get_initial_time_signature(),
            'key_signature': score.get_initial_key_signature(),
            'tempo': score.get_initial_tempo(),
            'instruments': score.get_instruments(),
            'number_of_bars': score.get_number_of_bars(),
            'number_of_parts': score.get_number_of_parts(),
            'repetition_right_hand' : score.music_analyser.repetition_right_hand,
            'repetition_left_hand' : score.music_analyser.repetition_left_hand,
            'summary_right_hand' : score.music_analyser.summary_right_hand,
            'summary_left_hand' : score.music_analyser.summary_left_hand,
        }


    def store(self, src_filepath, filename):

        if self.id is None:
            self.id = hashfile(open(src_filepath, 'rb'), hashlib.sha256())
        if self.filename is None:
            self.filename = filename
        # logger.info("File hash is %s" % file_hash)

        data_file_path = self.get_data_file_path()

        try:
            os.rename(src_filepath, data_file_path)
        except OSError as e:
            if e.errno == errno.EEXIST:  # file exists error?
                self.logger.info("File %s exists" % data_file_path)
            else:
                raise  # re-raise the exception
        return self.id

    def get_data_file_path(self, root=MEDIA_ROOT, createDirs=True):
        data_file_path = os.path.join(*(root, self.id, self.filename)) # removed slashes in directory structure to make files easier to brwose to
        if createDirs:
            dir_to_create = os.path.dirname(data_file_path)
            try:
                os.makedirs(dir_to_create)
            except OSError as e:
                if e.errno == errno.EEXIST:  # file exists error?
                    self.logger.info("Directory %s exists" % dir_to_create)
                else:
                    raise  # re-raise the exception
        return data_file_path

    def fetch(self):
        if self.url is None:
            self.logger.warn("Trying to fetch a score without a URL")
            return

        temporary_file = tempfile.NamedTemporaryFile(delete=False,dir=os.path.join(BASE_DIR,'tmp'))
        self.logger.debug("Temporary file: %s" % temporary_file.name)
        r = requests.get(self.url, stream=True)
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                temporary_file.write(chunk)
                temporary_file.flush()
        temporary_file.close()
        return temporary_file.name

    def html(self):
        data_path = self.get_data_file_path()
        html_path = self.get_data_file_path(root=os.path.join(BASE_DIR, STATIC_ROOT, 'data')) + '.html'
        web_path  = os.path.dirname(self.get_data_file_path(root="/scores",createDirs=False))
        if not os.path.exists(html_path):
            mxmlScore = Music21TalkingScore(data_path)
            tsf = HTMLTalkingScoreFormatter(mxmlScore)
            html = tsf.generateHTML(output_path=os.path.dirname(html_path),web_path=web_path)
            with open(html_path, "w") as fh:
                fh.write(html)
        else:
            self.logger.info("Score already processed, fetching existing HTML")
            with open(html_path, 'r') as html_fh:
                html = html_fh.read()
        return html


    @classmethod
    def from_uploaded_file(cls, uploaded_file):
        temporary_file = tempfile.NamedTemporaryFile(delete=False,suffix='.xml',dir=os.path.join(BASE_DIR,'tmp'))
        logger.debug("Temporary file: %s" % temporary_file.name)
        for chunk in uploaded_file.chunks():
            temporary_file.write(chunk)
        temporary_file.close()

        # Validate this file is loadable
        try:
            mxml_score = Music21TalkingScore(temporary_file.name)
        except Exception as ex:
            logger.exception("Unparsable file: %s" % temporary_file.name + " --- " + str(ex))
            raise ex;

        score = TSScore(filename=os.path.basename(uploaded_file.name))
        score.store(temporary_file.name, score.filename)
        return score

    @classmethod
    def from_url(cls, url):
        logger.info("URL is: '%s'" % url)
        parsed_url = urlparse(url)
        score = TSScore(url=url)
        score_temp_filepath = score.fetch()
        score_filename = url2pathname(os.path.basename(parsed_url.path))
        score.store(score_temp_filepath, score_filename)
        return score