__author__ = 'PMarchant'

import os
import json
import math
import pprint
import logging, logging.handlers, logging.config
from tracemalloc import BaseFilter
from music21 import *
from talkingscores.settings import BASE_DIR, MEDIA_ROOT, STATIC_ROOT, STATIC_URL

logger = logging.getLogger("TSScore")

class MidiHandler:
    def __init__(self, get, folder, filename):
        self.queryString = get
        self.folder = folder
        self.filename = filename.replace(".mid", "")


    def make_midi_file(self):
        xml_file_path = os.path.join(*(MEDIA_ROOT, self.folder, self.filename)) #todo - might not be secure 
        score = converter.parse(xml_file_path+".musicxml") #todo - might be .xml instead of .musicxml
        s = stream.Score(id='temp')
        s.insert(score.parts[1])
        midi_filepath = os.path.join(STATIC_ROOT, "data", self.folder, "%s" % ( self.midiname ) )
        s.write('midi', midi_filepath)


    def get_or_make_midi_file(self):
        self.midiname = self.filename
        if (self.queryString.get("part")!=None):
            self.midiname+="p"+self.queryString.get("part")
        if (self.queryString.get("ins")!=None):
            self.midiname+="i"+self.queryString.get("ins")
        if (self.queryString.get("start")!=None):
            self.midiname+="s"+self.queryString.get("start")
        if (self.queryString.get("end")!=None):
            self.midiname+="e"+self.queryString.get("end")
        if (self.queryString.get("click")=="1"):
            self.midiname+="c"
        if (self.queryString.get("tempo")!=None):
            self.midiname+="t"+self.queryString.get("tempo")
        
        self.midiname+=".mid"
        
        midi_filepath = os.path.join(STATIC_ROOT, "data", self.folder, "%s" % ( self.midiname ) )
        if not os.path.exists(midi_filepath):
            self.make_midi_file()
        
        return self.midiname