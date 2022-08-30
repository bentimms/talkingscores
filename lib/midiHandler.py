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

    #get list of selected / unselected instruments from binary of number.  Leftmost value is always 1
    def get_selected_instruments(self):
        bsi = int(self.queryString.get("bsi"))
        self.selected_instruments = []
        while (bsi>1):
            print ("bsi = " + str(bsi))
            if (bsi&1==True):
                self.selected_instruments.append(True)
            else:
                self.selected_instruments.append(False)
            bsi=bsi>>1
        self.selected_instruments.reverse()
        print(self.selected_instruments)

        self.all_selected_parts = []
        self.all_unselected_parts = []
        self.selected_instruement_parts = {} #key = instrument, value = [parts]

        instrument_index=-1
        prev_instrument=""
        for part_index, part in enumerate(self.score.flat.getInstruments()):
            print ("part_index = " + str(part_index) )
            print (part)
            if part.partId!=prev_instrument:
                instrument_index+=1
                self.selected_instruement_parts.get(instrument_index)
                
            if (self.selected_instruments[instrument_index]==True):
                self.all_selected_parts.append(part_index)
                if (instrument_index in self.selected_instruement_parts.keys()):
                    self.selected_instruement_parts[instrument_index].append(part_index)
                else:
                    self.selected_instruement_parts[instrument_index] = [part_index]
            else:
                self.all_unselected_parts.append(part_index)

            prev_instrument=part.partId

        print("all_selected_parts = ")
        print(self.all_selected_parts)
        print("all_unselected_parts = ")
        print(self.all_unselected_parts)
        print("selected_instruement_parts = ")
        print(self.selected_instruement_parts)
    
    def make_midi_files(self):
        xml_file_path = os.path.join(*(MEDIA_ROOT, self.folder, self.filename)) #todo - might not be secure 
        self.score = converter.parse(xml_file_path+".musicxml") #todo - might be .xml instead of .musicxml
        self.get_selected_instruments()
            
        s = stream.Score(id='temp')
        
        if self.queryString.get("start") is None and self.queryString.get("end") is None:
            #todo - test for pickup bar
            start = self.score.parts[0].getElementsByClass('Measure')[0].number
            end = self.score.parts[0].getElementsByClass('Measure')[-1].number
        else:
            start = int(self.queryString.get("start"))
            end = int(self.queryString.get("end"))
            
        if (self.queryString.get("part")!=None):
            s.insert(self.score.parts[int(self.queryString.get("part"))].measures(start,end))
    

        midi_filepath = os.path.join(STATIC_ROOT, "data", self.folder, "%s" % ( self.midiname ) )
        s.write('midi', midi_filepath)


    def get_or_make_midi_file(self):
        self.midiname = self.filename
        if (self.queryString.get("selected")!=None):
            #todo - just selected parts will be tricky!
            self.midiname+="selected-"+self.queryString.get("selected")
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
            self.make_midi_files()
        
        return self.midiname