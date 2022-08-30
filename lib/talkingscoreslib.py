from collections import OrderedDict
from jinja2.loaders import FileSystemLoader

__author__ = 'BTimms'

import os
import json
import math
import pprint
import logging, logging.handlers, logging.config
from music21 import *
from lib.musicAnalyser import *
us = environment.UserSettings()
us['warnings'] = 0
from abc import ABCMeta, abstractmethod
from jinja2 import Template
from _datetime import datetime
logger = logging.getLogger("TSScore")

global settings

class TSEvent(object, metaclass=ABCMeta):
    duration = None
    beat = None
    bar = None
    part = None
    tie = None

    def render_colourful_output(self, text, pitchLetter, elementType):
        figureNoteColours = {"C" : "red", "D" : "brown", "E" : "grey", "F" : "blue", "G" : "black", "A" : "yellow", "B" : "green"}
        figureNoteContrastTextColours = {"C" : "white", "D" : "white", "E" : "white", "F" : "white", "G" : "white", "A" : "black", "B" : "white"}
        toRender = text
        
        if settings["colourPosition"]!="None":
            doColours = False
            if (elementType=="pitch" and settings["colourPitch"]==True):
                doColours=True  
            if (elementType=="rhythm" and settings["colourRhythm"]==True):
                doColours=True  
            if (elementType=="octave" and settings["colourOctave"]==True):
                doColours=True  
                          
            if doColours==True:
                if settings["colourPosition"]=="background":
                    toRender = "<span style='color:" + figureNoteContrastTextColours[pitchLetter] + "; background-color:" + figureNoteColours[pitchLetter] + ";'>" + text + "</span>"
                elif settings["colourPosition"]=="text":
                    toRender = "<span style='color:" + figureNoteColours[pitchLetter] + ";'>" + text + "</span>"

        return toRender

    def render(self, context=None, noteLetter=None):
        rendered_elements = []
        if (context is None or context.duration != self.duration or settings['rhythmAnnouncement']=="everyNote") and self.duration:
            if (noteLetter!=None):
                rendered_elements.append(self.render_colourful_output(self.duration, noteLetter, "rhythm"))
            else:
                rendered_elements.append(self.duration)

        if self.tie:
            rendered_elements.append("tie %s" % self.tie)
        return rendered_elements

class TSDynamic(TSEvent):
    short_name = None
    long_name = None

    def __init__(self, long_name=None, short_name=None):
        if (long_name!=None):
            self.long_name = long_name.capitalize()
        else:
            self.long_name = short_name
        
        self.short_name = short_name

    def render(self, context=None):
        return [self.long_name]

class TSPitch(TSEvent):
    pitch_name = None
    octave = None
    pitch_letter = None #used for looking up colour based on pitch and fixes sharp / flat problem when modulus and the pitch number

    def __init__(self, pitch_name, octave, pitch_number, pitch_letter):
        self.pitch_name = pitch_name
        self.octave = octave
        self.pitch_number = pitch_number
        self.pitch_letter = pitch_letter

    def render(self, context=None):
        global settings
        rendered_elements = []
        if settings['octavePosition']=="before":
            rendered_elements.append(self.render_octave(context))
        rendered_elements.append(self.render_colourful_output(self.pitch_name, self.pitch_letter, "pitch"))
        if settings['octavePosition']=="after":
            rendered_elements.append(self.render_octave(context))
        
        return rendered_elements

    def render_octave(self, context=None):
        show_octave = False
        if settings['octaveAnnouncement']=="brailleRules":
            if context==None:
                show_octave=True
            else:
                pitch_difference = abs(context.pitch_number - self.pitch_number)
                #if it is a 3rd or less, don't say octave
                if pitch_difference<=4:
                    show_octave=False # it already is...
                #if it is a 4th or 5th and octave changes, say octave
                elif pitch_difference>=5 and pitch_difference<=7:
                    if context.octave != self.octave:
                        show_octave=True
                #if it is more than a 5th, say octave
                else:
                    show_octave = True
        elif settings['octaveAnnouncement']=="everyNote":
            show_octave=True
        elif settings['octaveAnnouncement']=="firstNote" and context==None:
            show_octave=True
        elif settings['octaveAnnouncement']=="onChange":
            if context==None or (context!=None and context.octave != self.octave):
                show_octave=True
        
        if show_octave:
            return self.render_colourful_output(self.octave, self.pitch_letter, "octave")
        else:
            return ""

class TSRest(TSEvent):
    pitch = None
    def render(self, context=None):
        rendered_elements = []
        # Render the duration
        rendered_elements.append(' '.join(super(TSRest, self).render(context)))
        # Render the pitch
        rendered_elements.append(' rest')
        return rendered_elements


class TSNote(TSEvent):
    pitch = None
    expressions = []

    def render(self, context=None):
        rendered_elements = []
        # Render the expressions
        for exp in self.expressions:
            rendered_elements.append(exp.name + ', ')
        # Render the duration
        rendered_elements.append(' '.join(super(TSNote, self).render(context, self.pitch.pitch_letter)))
        # Render the pitch
        rendered_elements.append(' '.join(self.pitch.render(getattr(context, 'pitch', None))))
        return rendered_elements

class TSChord(TSEvent):
    pitches = []

    def name(self):
        return ''

    def render(self, context=None):
        rendered_elements = ['%s-note chord' % len(self.pitches)]
        rendered_elements.append(' '.join(super(TSChord, self).render(context) ))
        previous_pitch = None
        for pitch in sorted(self.pitches, key=lambda TSPitch: TSPitch.pitch_number):
            rendered_elements.append(' '.join(pitch.render(previous_pitch) ))
            previous_pitch = pitch
        return [', '.join(rendered_elements)]

class TalkingScoreBase(object, metaclass=ABCMeta):
    @abstractmethod
    def get_title(self):
        pass

    @abstractmethod
    def get_composer(self):
        pass

class Music21TalkingScore(TalkingScoreBase):

    _OCTAVE_MAP = {
        1: 'bottom',
        2: 'lower',
        3: 'low',
        4: 'mid',
        5: 'high',
        6: 'higher',
        7: 'top'
    }

    _OCTAVE_FIGURENOTES_MAP = {
        1: 'bottom',
        2: 'cross',
        3: 'square',
        4: 'circle',
        5: 'triangle',
        6: 'higher',
        7: 'top'
    }

    _DOTS_MAP = {
        0 : '',
        1 : 'dotted ',
        2 : 'double dotted ',
        3 : 'triple dotted '
    }

    _DURATION_MAP = {
        'whole': 'semibreve',
        'half': 'minim',
        'quarter': 'crotchet',
        'eighth': 'quaver',
        '16th': 'semi-quaver',
        '32nd': 'demi-semi-quaver',
        '64th': 'hemi-demi-semi-quaver',
        'zero': 'grace note',
    }

    _PITCH_FIGURENOTES_MAP = {
        'C': 'red',
        'D': 'brown',
        'E': 'grey',
        'F': 'blue',
        'G': 'black',
        'A': 'yellow',
        'B': 'green',
    }

    _PITCH_PHONETIC_MAP = {
        'C': 'charlie',
        'D': 'bravo',
        'E': 'echo',
        'F': 'foxtrot',
        'G': 'golf',
        'A': 'alpha',
        'B': 'bravo',
    }

    last_tempo_inserted_index = 0 # insert_tempos() doesn't need to recheck MetronomeMarkBoundaries that have already been used
    music_analyser = None;

    def __init__(self, musicxml_filepath):
        self.filepath = os.path.realpath(musicxml_filepath)
        self.score = converter.parse(musicxml_filepath)
        self.music_analyser = MusicAnalyser()
        self.music_analyser.setScore(self.score)
        super(Music21TalkingScore, self).__init__()

    def get_title(self):
        if self.score.metadata.title is not None:
            return self.score.metadata.title
        # Have a guess
        for tb in self.score.flat.getElementsByClass('TextBox'):
            if tb.justify == 'center' and tb.alignVertical == 'top' and tb.size > 18:
                return tb.content
        return "Unknown"


    def get_composer(self):
        if self.score.metadata.composer != None:
            return self.score.metadata.composer
        # Look for a text box in the top right of the first page
        for tb in self.score.getElementsByClass('TextBox'):
            if tb.style.justify == 'right':
                return tb.content
        return "Unknown"

    def get_initial_time_signature(self):
        # Get the first measure of the first part
        m1 = self.score.parts[0].measures(1,1)
        initial_time_signature = m1.getTimeSignatures()[0]
        return " ".join(initial_time_signature.ratioString.split("/"))
        # return "4 4"

    def get_initial_key_signature(self):
        m1 = self.score.parts[0].measures(1,1)
        ks = m1.flat.getElementsByClass('KeySignature')[0]
        strKeySig = "No sharps or flats"
        if (ks.sharps>0):
            strKeySig = str(ks.sharps) + " sharps"
        elif (ks.sharps<0):
            strKeySig = str(abs(ks.sharps)) + " flats"

        return strKeySig

    def get_initial_tempo(self):
        # Get the first measure of the first part
        m1 = self.score.parts[0].measures(1,1)
        # Get the text expressions from that measure
        text_expressions = m1.flat.getElementsByClass('TextExpression')
        for te in text_expressions:
            return te.content

    def get_number_of_bars(self):
        return len(self.score.parts[0].getElementsByClass('Measure'))

    def get_instruments(self):
        #eg instrument.Name = Piano, instrument.partId = 1.  A piano has 2 staves ie two parts with the same name and same ID.  But if you have a second piano, it will have the same name but a different partId
        self.part_instruments={} # key = instrument (1 based), value = ["part name", 1st part, number of parts, instrument.partId] 
        self.part_names = {} # left or right hand etc
        instrument_names=[] #still needed for Info / Options page
        ins_count = 1
        for c, instrument in enumerate(self.score.flat.getInstruments()):
            if len(self.part_instruments) == 0 or self.part_instruments[ins_count-1][3] != instrument.partId:
                pname = instrument.partName
                if pname==None:
                    pname = "Instrument  " + str(ins_count) + " (unnamed)"
                self.part_instruments[ins_count] = [pname, c, 1, instrument.partId]
                instrument_names.append(pname)
                
                ins_count+=1
            else:
                self.part_instruments[ins_count-1][2]+=1
                #todo - there is a more efficient way of doing this - or just let the user enter part names on the options screen - but these are OK for defaults
                if self.part_instruments[ins_count-1][2] == 2:
                   self.part_names[c-1] = "Right hand"
                   self.part_names[c] = "Left hand"
                elif self.part_instruments[ins_count-1][2] == 3:
                   self.part_names[c-2] = "Part 1"
                   self.part_names[c-1] = "Part 2"
                   self.part_names[c] = "Part 3"
                else:
                    self.part_names[c] = "Part " + str(self.part_instruments[ins_count-1][2])

        print("part_instruments = " + str(self.part_instruments))
        print("part names = " + str(self.part_names))
        return instrument_names 

    def compare_parts_with_selected_instruments(self):
        global settings
        self.selected_instruments = []
        self.unselected_instruments = []
        self.binary_selected_instruments = 1 #bitwise representation of all instruments - 0=not included, 1=included
        for ins in self.part_instruments.keys():
            self.binary_selected_instruments =  self.binary_selected_instruments<<1
            if ins in settings['instruments']:
                self.selected_instruments.append(ins)
                self.binary_selected_instruments+=1
            else:
                self.unselected_instruments.append(ins)
        
        if len(self.unselected_instruments)==0: #All instruments selected - so no unselected instruments to play
            settings['playUnselected'] = False
        if len(self.selected_instruments)==len(self.part_instruments) and settings['playAll']==True: #played by Play All
            settings['playSelected'] = False
        if len(self.selected_instruments)==1: #played by individual part
            settings['playSelected'] = False

    def get_number_of_parts(self):
        self.get_instruments()
        return len(self.part_instruments)

    def get_bar_range(self, range_start, range_end):
        measures = self.score.measures(range_start, range_end)
        bars_for_parts = {}
        for part in measures.parts:
            bars_for_parts.setdefault(part.id, []).extend(part.getElementsByClass('Measure'))

        return bars_for_parts

    def get_events_for_bar_range(self, start_bar, end_bar):
        events_by_bar = {}

        # Iterate over the spanners
        for spanner in self.score.flat.spanners.elements:
            spanner_type = type(spanner).__name__

            if spanner_type == 'Crescendo' or spanner_type == 'Diminuendo':
                first = spanner.getFirst()
                last  = spanner.getLast()
                if first.measureNumber is None or last.measureNumber is None:
                    continue
                description_order = 0
                voice = 1

                if first.measureNumber >= start_bar and first.measureNumber <= end_bar:
                    event = TSDynamic(long_name='%s start' % spanner_type)
                    events_by_bar\
                        .setdefault(first.measureNumber, {})\
                        .setdefault(math.floor(first.beat), {})\
                        .setdefault('Both', {})\
                        .setdefault(voice, {})\
                        .setdefault(description_order, [])\
                        .append(event)

                if last.measureNumber >= start_bar and last.measureNumber <= end_bar:
                    event = TSDynamic(long_name='%s end' % spanner_type)
                     # Note - THIS WILL NOT HANDLE CRESCENDOS/DIMINUENDOS THAT SPAN MEASURES
                    events_by_bar\
                        .setdefault(last.measureNumber, {})\
                        .setdefault(math.floor(last.beat) + last.duration.quarterLength - 1, {})\
                        .setdefault('BothAfter', {})\
                        .setdefault(voice, {})\
                        .setdefault(description_order, [])\
                        .append(event)

        measures = self.score.measures(start_bar, end_bar)
        for part in measures.parts:
            print("\n\nProcessing part %s, bars %s to %s" % (part.id, start_bar, end_bar))
            # Iterate over the bars one at a time
            # pickup bar has to request measures 0 to 1 above otherwise it returns an measures just has empty parts - so now restrict it just to bar 0...
            if start_bar==0 and end_bar==1:
                end_bar=0
            for bar_index in range(start_bar, end_bar + 1):
                measure = part.measure(bar_index)
                if measure is not None:
                    self.update_events_for_measure(measure, part.id, events_by_bar)

        return events_by_bar

    def update_events_for_measure(self, measure, part_id, events, voice=1):

        for element in measure.elements:
            element_type = type(element).__name__
            event = None
            hand = ('Left', 'Right')[part_id == 'P1-Staff1']

            if element_type == 'Note':
                event = TSNote()
                event.pitch = TSPitch( self.map_pitch(element.pitch), self.map_octave(element.pitch.octave), element.pitch.ps, element.pitch.name[0] )
                description_order = 1
                if element.tie:
                    event.tie = element.tie.type
 
                event.expressions = element.expressions
            elif element_type == 'Rest':
                event = TSRest()
                description_order = 1
                
            elif element_type == 'Chord':
                event = TSChord()
                event.pitches = [ TSPitch(self.map_pitch(element_pitch), self.map_octave(element_pitch.octave), element_pitch.ps, element_pitch.name[0]) for element_pitch in element.pitches ]
                description_order = 1
                if element.tie:
                    event.tie = element.tie.type

            elif element_type == 'Dynamic':
                event = TSDynamic(long_name = element.longName, short_name=element.value)
                description_order = 0 # Always speak the dynamic first
                hand = 'Both'

            elif element_type == 'Voice':
                self.update_events_for_measure(element, part_id, events, element.id)

            if event is None:
                continue

            # This test isn't WORKING
            # if TSEvent.__class__ in event.__class__.__bases__:
            event.duration = ""
            if settings['dotPosition']=="before":
                event.duration = self.map_dots(element.duration.dots)
            event.duration += self.map_duration(element.duration)
            if settings['dotPosition']=="after":
                event.duration += " " + self.map_dots(element.duration.dots)

            events\
                .setdefault(measure.measureNumber, {})\
                .setdefault(math.floor(element.beat), {})\
                .setdefault(hand, {})\
                .setdefault(voice, {})\
                .setdefault(description_order, [])\
                .append(event)


    def group_chord_pitches_by_octave(self, chord):
        chord_pitches_by_octave = {}
        for pitch in chord.pitches:
            chord_pitches_by_octave.setdefault(self._PITCH_MAP.get(str(pitch.octave),'?'), []).append(pitch.name)

        return chord_pitches_by_octave

     

    def generate_midi_filenames(self, prefix, range_start=None, range_end=None, add_instruments=[], output_path="", postfix_filename=""):
        part_midis = []
        if range_start is None and range_end is None:
            for ins in add_instruments:
                for pi in range (self.part_instruments[ins][1], self.part_instruments[ins][1]+self.part_instruments[ins][2]):
                    if self.part_instruments[ins][2]>1:
                        base_filename = os.path.splitext(os.path.basename(self.filepath))[0]
                        midi_filename = os.path.join(output_path, "%s%s.mid?part=%s" % ( base_filename, postfix_filename, str((pi-self.part_instruments[ins][1])+1) ) )
                        part_midis.append(midi_filename)
        else: #specific measures
            #postfix_filename += "_" + str(range_start) + str(range_end)
            for ins in add_instruments:
                for pi in range (self.part_instruments[ins][1], self.part_instruments[ins][1]+self.part_instruments[ins][2]):
                    if self.part_instruments[ins][2]>1:
                        base_filename = os.path.splitext(os.path.basename(self.filepath))[0]
                        midi_filename = os.path.join(output_path, "%s.mid?part=%d&start=%d&end=%d" % ( base_filename, pi, range_start, range_end ) )
                        part_midis.append(midi_filename)

        base_filename = os.path.splitext(os.path.basename(self.filepath))[0]
        if (range_start!=None):
            midi_filename = os.path.join(output_path, ("%s.mid?ins=%d&start=%d&end=%d" % ( base_filename,ins, range_start,range_end )) )
        else:
            midi_filename = os.path.join(output_path, ("%s.mid?ins=%d" % ( base_filename,ins,  )) )
        #todo - might need to add in tempos if part 0 is not included
        part_midis = [prefix + os.path.basename(s) for s in part_midis]
        return (prefix+os.path.basename(midi_filename), part_midis)

    
    def generate_midi_for_instruments(self, prefix, range_start=None, range_end=None, add_instruments=[], output_path="", postfix_filename=""):
        part_midis = []
        s = stream.Score(id='temp')
        
        if range_start is None and range_end is None:
            for ins in add_instruments:
                for pi in range (self.part_instruments[ins][1], self.part_instruments[ins][1]+self.part_instruments[ins][2]):
                    s.insert(self.score.parts[pi])
                    if self.part_instruments[ins][2]>1:
                        part_midis.append(self.generate_midi_parts_for_instrument(range_start, range_end, ins, pi-self.part_instruments[ins][1], output_path, postfix_filename))

        else: #specific measures
            postfix_filename += "_" + str(range_start) + str(range_end)
            for ins in add_instruments:
                firstPart = True
                for pi in range (self.part_instruments[ins][1], self.part_instruments[ins][1]+self.part_instruments[ins][2]):
                    if self.part_instruments[ins][2]>1:
                        part_midis.append(self.generate_midi_parts_for_instrument(range_start, range_end, ins, pi-self.part_instruments[ins][1], output_path, postfix_filename))
                    pi_measures = self.score.parts[pi].measures(range_start, range_end, collect=('Clef', 'TimeSignature', 'Instrument', 'KeySignature', 'TempoIndication'))
                    if firstPart:
                        if pi!=0: # only part 0 has tempos
                            self.insert_tempos(pi_measures, self.score.parts[0].measure(range_start).offset)
                        firstPart=False
                    
                    #music21 v6.3.0 tries to expand repeats - which causes error if segment only includes the start repeat mark
                    for m in pi_measures.getElementsByClass('Measure'):
                        m.removeByClass('Repeat') 
                    s.insert(pi_measures)            

        base_filename = os.path.splitext(os.path.basename(self.filepath))[0]
        midi_filename = os.path.join(output_path, "%s%s.mid" % ( base_filename, postfix_filename ) )
        #todo - might need to add in tempos if part 0 is not included
        if not os.path.exists(midi_filename):
            s.write('midi', midi_filename)
        part_midis = [prefix + os.path.basename(s) for s in part_midis]
        return (prefix+os.path.basename(midi_filename), part_midis)

    def generate_midi_parts_for_instrument(self, range_start=None, range_end=None, instrument=0, part=0, output_path="", postfix_filename=""):
        s = stream.Score(id='temp')   
        if range_start is None and range_end is None:
            s = stream.Score(id='temp')
            s.insert(self.score.parts[self.part_instruments[instrument][1]+part])
            base_filename = os.path.splitext(os.path.basename(self.filepath))[0]
            midi_filename = os.path.join(output_path, "%s%s_p%s.mid" % ( base_filename, postfix_filename, str(part+1) ) )
            if not os.path.exists(midi_filename):
                s.write('midi', midi_filename)
        else: #specific measures
            postfix_filename += "_" + str(range_start) + str(range_end)
            s = stream.Score(id='temp')
            print("506 instrument = " + str(instrument) + " part = " + str(part))
            pi_measures = self.score.parts[self.part_instruments[instrument][1]+part].measures(range_start, range_end, collect=('Clef', 'TimeSignature', 'Instrument', 'KeySignature', 'TempoIndication'))
            if self.part_instruments[instrument][1]+part!=0: # only part 0 has tempos
                self.insert_tempos(pi_measures, self.score.parts[0].measure(range_start).offset)
            
            #music21 v6.3.0 tries to expand repeats - which causes error if segment only includes the start repeat mark
            for m in pi_measures.getElementsByClass('Measure'):
                m.removeByClass('Repeat') 
            s.insert(pi_measures)            

            base_filename = os.path.splitext(os.path.basename(self.filepath))[0]
            midi_filename = os.path.join(output_path, "%s%s_p%s.mid" % ( base_filename, postfix_filename, str(part+1) ) )
            if not os.path.exists(midi_filename):
                s.write('midi', midi_filename)
        return midi_filename

    def generate_midi_for_part_range(self, range_start=None, range_end=None, parts=[], output_path=""):
        
        base_filename = os.path.splitext(os.path.basename(self.filepath))[0]
        if range_start is None and range_end is None:
            # Export the whole score
            midi_filename = os.path.join(output_path, "%s.mid" % ( base_filename ) )
            if not os.path.exists(midi_filename):
                self.score.write('midi', midi_filename)
            return midi_filename
        elif len(parts) > 0: #individual parts
            for p in self.score.parts:
                if p.id not in parts:
                    continue

                midi_filename = os.path.join(output_path, "%s_p%s_%s_%s.mid" % ( base_filename, p.id, range_start, range_end ) )
                if not os.path.exists(midi_filename):
                    midi_stream = p.measures(range_start, range_end, collect=('Clef', 'TimeSignature', 'Instrument', 'KeySignature', 'TempoIndication'))
                    if p!=self.score.parts[0]: # only part 0 has tempos
                        self.insert_tempos(midi_stream, self.score.parts[0].measure(range_start).offset)
                    #music21 v6.3.0 tries to expand repeats - which causes error if segment only includes the start repeat mark
                    for m in midi_stream.getElementsByClass('Measure'):
                        m.removeByClass('Repeat')   
                    midi_stream.write('midi', midi_filename)
                return midi_filename
        else: # both hands
            midi_filename = os.path.join(output_path, "%s_%s_%s.mid" % ( base_filename, range_start, range_end ))
            if not os.path.exists(midi_filename):
                midi_stream = self.score.measures(range_start, range_end, collect=('Clef', 'TimeSignature', 'Instrument', 'KeySignature', 'TempoIndication'))
                #music21 v6.3.0 tries to expand repeats - which causes error if segment only includes the start repeat mark
                for pa in midi_stream.getElementsByClass('Part'):
                    for m in pa.getElementsByClass('Measure'):
                        m.removeByClass('Repeat') 
                midi_stream.write('midi', midi_filename)
            return midi_filename

        return None
       
    #TODO need to make more efficient when working with multiple parts ie more than just the left hand piano part
    #music21 might have a better way of doing this.  If part 0 is included then tempos are already present.
    def insert_tempos(self, stream, offset_start):       
        if (self.last_tempo_inserted_index>0): # one tempo change might need to be in many segments - especially the last tempo change in the score
            self.last_tempo_inserted_index-=1
        for mmb in self.score.metronomeMarkBoundaries()[self.last_tempo_inserted_index:]:
            if (mmb[0]>=offset_start+stream.duration.quarterLength): # ignore tempos that start after stream ends
                return           
            if (mmb[1]>offset_start): # if mmb ends during the segment
                if (mmb[0])<=offset_start: # starts before segment so insert it at the start of the stream
                    stream.insert(0, tempo.MetronomeMark(number=mmb[2].number))
                    self.last_tempo_inserted_index+=1
                else: # starts during segment so insert it part way through the stream
                    stream.insert(mmb[0]-offset_start, tempo.MetronomeMark(number=mmb[2].number))
                    self.last_tempo_inserted_index+=1
       
    def map_octave(self, octave):
        global settings
        if settings['octaveDescription']=="figureNotes":
            return self._OCTAVE_FIGURENOTES_MAP.get(octave, "?")
        elif settings['octaveDescription']=="name":
            return self._OCTAVE_MAP.get(octave, "?")
        elif settings['octaveDescription']=="none":
            return ""
        elif settings['octaveDescription']=="number":
            return str(octave)
        
        # return "%s %s" % (self._PITCH_MAP.get(pitch[-1], ''), pitch[0] )

    def map_pitch(self, pitch):
        global settings
        if settings['pitchDescription']=="colourNotes":
            pitch_name = self._PITCH_FIGURENOTES_MAP.get(pitch.name[0], "?")
        if settings['pitchDescription']=="noteName":
            pitch_name = pitch.name[0]
        elif settings['pitchDescription']=="none":
            pitch_name = ""
        elif settings['pitchDescription']=="phonetic":
            pitch_name = self._PITCH_PHONETIC_MAP.get(pitch.name[0], "?")
        
        if pitch.accidental and pitch.accidental.displayStatus and pitch_name!="":
            pitch_name = "%s %s" % (pitch_name, pitch.accidental.fullName)
        return pitch_name

    def map_duration(self, duration):
        global settings
        if settings['rhythmDescription']=="american":
            return duration.type
        elif settings['rhythmDescription']=="british":
            return self._DURATION_MAP.get(duration.type, 'Unknown duration %s'%duration.type)
        elif settings['rhythmDescription']=="none":
            return ""
        

    def map_dots(self, dots):
        if settings['rhythmDescription']=="none":
            return ""
        else:
            return self._DOTS_MAP.get(dots)

class HTMLTalkingScoreFormatter():

    def __init__(self, talking_score):
        global settings
        
        self.score:Music21TalkingScore = talking_score

        options_path = self.score.filepath + '.opts'
        with open(options_path, "r") as options_fh:
                options = json.load(options_fh)
        settings = {
            'pitchBeforeDuration': False,
            'describeBy': 'beat',
            'handsTogether': True,
            'barsAtATime': int(options["bars_at_a_time"]),
            'playAll':options["play_all"],
            'playSelected':options["play_selected"],
            'playUnselected':options["play_unselected"],
            'instruments':options["instruments"],
            'pitchDescription':options["pitch_description"],
            'rhythmDescription':options["rhythm_description"],
            'dotPosition':options["dot_position"],
            'rhythmAnnouncement':options["rhythm_announcement"],
            'octaveDescription':options["octave_description"],
            'octavePosition':options["octave_position"],
            'octaveAnnouncement':options["octave_announcement"],
            'colourPosition':options["colour_position"],
            'colourPitch':options["colour_pitch"],
            'colourRhythm':options["colour_rhythm"],
            'colourOctave':options["colour_octave"],
        }
        

    def generateHTML(self,output_path="",web_path=""):
        global settings
        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader(os.path.dirname(__file__)))
        template = env.get_template('talkingscore.html')
        
        self.score.get_instruments()
        self.score.compare_parts_with_selected_instruments()
        print ("Settings...")
        print (settings)
        
        full_score_selected = ""
        if settings['playSelected']==True:
            full_score_selected = self.score.generate_midi_filenames(prefix="/midis/" + os.path.basename(web_path) + "/", output_path=output_path, add_instruments=self.score.selected_instruments, postfix_filename="s")[0]
        full_score_unselected = ""
        if settings['playUnselected']==True:
            full_score_unselected = self.score.generate_midi_filenames(prefix="/midis/" + os.path.basename(web_path) + "/", output_path=output_path, add_instruments=self.score.unselected_instruments, postfix_filename="u")[0]
        
        return template.render({'settings' : settings,
                                'basic_information': self.get_basic_information(),
                                'preamble': self.get_preamble(),
                                'full_score': "/midis/" + os.path.basename(web_path) + "/" + os.path.basename(self.score.generate_midi_for_part_range(output_path=output_path)),
                                'full_score_selected': "/midis/" + os.path.basename(web_path) + "/" + os.path.basename(full_score_selected),
                                'full_score_unselected': "/midis/" + os.path.basename(web_path) + "/" + os.path.basename(full_score_unselected),
                                'music_segments': self.get_music_segments(output_path,web_path, ),
                                'instruments' : self.score.part_instruments,
                                'part_names' : self.score.part_names,
                                'binary_selected_instruments' : self.score.binary_selected_instruments,
                                })

    def get_basic_information(self):
        return {
            'title': self.score.get_title(),
            'composer': self.score.get_composer(),
        }

    def get_preamble(self):
        return {
            'time_signature': self.score.get_initial_time_signature(),
            'key_signature': self.score.get_initial_key_signature(),
            'tempo': self.score.get_initial_tempo(),
            'number_of_bars': self.score.get_number_of_bars(),
            'number_of_parts': self.score.get_number_of_parts(),
        }

    

    def get_music_segments(self,output_path,web_path):
        print ("web path = ")
        print(web_path)
        print("base name webpath = ")
        print(os.path.basename(web_path)) 

        global settings
        logger.info("Start of get_music_segments")
        music_segments = []
        number_of_bars = self.score.get_number_of_bars()
        #pickup bar
        if self.score.score.parts[0].getElementsByClass('Measure')[0].number != self.score.score.parts[0].measures(1,2).getElementsByClass('Measure')[0].number:
            events_by_bar_and_beat = self.score.get_events_for_bar_range(0, 1)
            
            selected_instruments_midis = {}
            for index, ins in enumerate(self.score.selected_instruments):
                midis = self.score.generate_midi_filenamesgenerate_midi_for_instruments(prefix="/midis/" + os.path.basename(web_path) + "/", range_start=0, range_end=0, output_path=output_path, add_instruments=[ins], postfix_filename="ins"+str(index))
                selected_instruments_midis[ins] = {"ins":ins,  "midi":midis[0], "midi_parts":midis[1]}

            music_segment = {'start_bar':'0 - pickup', 'end_bar':'0 - pickup', 'events_by_bar_and_beat': events_by_bar_and_beat, 'selected_instruments_midis':selected_instruments_midis }
            music_segments.append(music_segment)
            number_of_bars-=1
 
        #everything except the pickup
        for bar_index in range( 1, number_of_bars+1, settings['barsAtATime'] ):
            end_bar_index = bar_index + settings['barsAtATime'] - 1
            if end_bar_index > number_of_bars:
                end_bar_index = number_of_bars

            events_by_bar_and_beat = self.score.get_events_for_bar_range(bar_index, end_bar_index, )
            # for offset, events in events_for_bar_range.iteritems():
            # events_ordered_by_beat = OrderedDict(sorted(events_for_bar_range.items(), key=lambda t: t[0]))

            # pp = pprint.PrettyPrinter(indent=4)
            # pp.pprint(events_by_bar_and_beat)

            selected_instruments_midis = {}
            for index, ins in enumerate(self.score.selected_instruments):
                midis = self.score.generate_midi_filenames(prefix="/midis/" + os.path.basename(web_path) + "/", range_start=bar_index, range_end=end_bar_index, output_path=output_path, add_instruments=[ins], postfix_filename="ins"+str(index))
                selected_instruments_midis[ins] = {"ins":ins,  "midi":midis[0], "midi_parts":midis[1]}
            
            music_segment = {'start_bar':bar_index, 'end_bar': end_bar_index, 'events_by_bar_and_beat': events_by_bar_and_beat, 'selected_instruments_midis':selected_instruments_midis }
            music_segments.append(music_segment)

        logger.info("End of get_music_segments")
        
        return music_segments




if __name__ == '__main__':
    
    # testScoreFilePath = '../talkingscoresapp/static/data/macdowell-to-a-wild-rose.xml'
    testScoreFilePath = '../media/172a28455fa5cfbdaa4eecd5f63a0a2ebaddd92d569980fb402811b9cd5cce4a/MozartPianoSonata.xml'
    # testScoreFilePath = '../talkingscores/talkingscoresapp/static/data/bach-2-part-invention-no-13.xml'

    testScoreOutputFilePath = testScoreFilePath.replace('.xml','.html')

    testScore = Music21TalkingScore(testScoreFilePath)
    tsf = HTMLTalkingScoreFormatter(testScore)
    html = tsf.generateHTML()

    with open(testScoreOutputFilePath, "wb") as fh:
        fh.write(html)

    os.system('open http://0.0.0.0:8000/static/data/%s'%os.path.basename(testScoreOutputFilePath))


