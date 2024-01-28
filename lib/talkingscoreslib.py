from datetime import datetime  # start_time = datetime.now()
import time
from jinja2 import Template
from abc import ABCMeta, abstractmethod
from collections import OrderedDict
from jinja2.loaders import FileSystemLoader

__author__ = 'BTimms'

import os
import json
import math
import pprint
import logging
import logging.handlers
import logging.config
from music21 import *
from lib.musicAnalyser import *
us = environment.UserSettings()
us['warnings'] = 0
logger = logging.getLogger("TSScore")

global settings


class TSEvent(object, metaclass=ABCMeta):
    duration = None
    tuplets = ""
    endTuplets = ""
    beat = None
    bar = None
    part = None
    tie = None

    def render_colourful_output(self, text, pitchLetter, elementType):
        figureNoteColours = {"C": "red", "D": "brown", "E": "grey", "F": "blue", "G": "black", "A": "yellow", "B": "green"}
        figureNoteContrastTextColours = {"C": "white", "D": "white", "E": "white", "F": "white", "G": "white", "A": "black", "B": "white"}
        toRender = text

        if settings["colourPosition"] != "None":
            doColours = False
            if (elementType == "pitch" and settings["colourPitch"] == True):
                doColours = True
            if (elementType == "rhythm" and settings["colourRhythm"] == True):
                doColours = True
            if (elementType == "octave" and settings["colourOctave"] == True):
                doColours = True

            if doColours == True:
                if settings["colourPosition"] == "background":
                    toRender = "<span style='color:" + figureNoteContrastTextColours[pitchLetter] + "; background-color:" + figureNoteColours[pitchLetter] + ";'>" + text + "</span>"
                elif settings["colourPosition"] == "text":
                    toRender = "<span style='color:" + figureNoteColours[pitchLetter] + ";'>" + text + "</span>"

        return toRender

    def render(self, context=None, noteLetter=None):
        rendered_elements = []
        if (context is None or context.duration != self.duration or self.tuplets != "" or settings['rhythmAnnouncement'] == "everyNote"):
            rendered_elements.append(self.tuplets)
            if (noteLetter != None):
                rendered_elements.append(self.render_colourful_output(self.duration, noteLetter, "rhythm"))
            else:
                rendered_elements.append(self.duration)
        rendered_elements.append(self.endTuplets)

        if self.tie:
            rendered_elements.append(f"tie {self.tie}")
        return rendered_elements


class TSDynamic(TSEvent):
    short_name = None
    long_name = None

    def __init__(self, long_name=None, short_name=None):
        if (long_name != None):
            self.long_name = long_name.capitalize()
        else:
            self.long_name = short_name

        self.short_name = short_name

    def render(self, context=None):
        return [self.long_name]


class TSPitch(TSEvent):
    pitch_name = None
    octave = None
    pitch_letter = None  # used for looking up colour based on pitch and fixes sharp / flat problem when modulus and the pitch number

    def __init__(self, pitch_name, octave, pitch_number, pitch_letter):
        self.pitch_name = pitch_name
        self.octave = octave
        self.pitch_number = pitch_number
        self.pitch_letter = pitch_letter

    def render(self, context=None):
        global settings
        rendered_elements = []
        if settings['octavePosition'] == "before":
            rendered_elements.append(self.render_octave(context))
        rendered_elements.append(self.render_colourful_output(self.pitch_name, self.pitch_letter, "pitch"))
        if settings['octavePosition'] == "after":
            rendered_elements.append(self.render_octave(context))

        return rendered_elements

    def render_octave(self, context=None):
        show_octave = False
        if settings['octaveAnnouncement'] == "brailleRules":
            if context == None:
                show_octave = True
            else:
                pitch_difference = abs(context.pitch_number - self.pitch_number)
                # if it is a 3rd or less, don't say octave
                if pitch_difference <= 4:
                    show_octave = False  # it already is...
                # if it is a 4th or 5th and octave changes, say octave
                elif pitch_difference >= 5 and pitch_difference <= 7:
                    if context.octave != self.octave:
                        show_octave = True
                # if it is more than a 5th, say octave
                else:
                    show_octave = True
        elif settings['octaveAnnouncement'] == "everyNote":
            show_octave = True
        elif settings['octaveAnnouncement'] == "firstNote" and context == None:
            show_octave = True
        elif settings['octaveAnnouncement'] == "onChange":
            if context == None or (context != None and context.octave != self.octave):
                show_octave = True

        if show_octave:
            return self.render_colourful_output(self.octave, self.pitch_letter, "octave")
        else:
            return ""


class TSUnpitched(TSEvent):
    pitch = None

    def render(self, context=None):
        rendered_elements = []
        # Render the duration
        rendered_elements.append(' '.join(super(TSUnpitched, self).render(context)))
        # Render the pitch
        rendered_elements.append(' unpitched')
        return rendered_elements


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
        rendered_elements = [f'{len(self.pitches)}-note chord']
        rendered_elements.append(' '.join(super(TSChord, self).render(context)))
        previous_pitch = None
        for pitch in sorted(self.pitches, key=lambda TSPitch: TSPitch.pitch_number):
            rendered_elements.append(' '.join(pitch.render(previous_pitch)))
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
        0: '',
        1: 'dotted ',
        2: 'double dotted ',
        3: 'triple dotted '
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

    last_tempo_inserted_index = 0  # insert_tempos() doesn't need to recheck MetronomeMarkBoundaries that have already been used
    music_analyser = None

    def __init__(self, musicxml_filepath):
        self.filepath = os.path.realpath(musicxml_filepath)
        self.score = converter.parse(musicxml_filepath)
        super(Music21TalkingScore, self).__init__()

    def get_title(self):
        if self.score.metadata.title is not None:
            return self.score.metadata.title
        # Have a guess
        for tb in self.score.flat.getElementsByClass('TextBox'):
            # in some musicxml files - a textbox might not have those attributes - so we use hasattr()...
            if hasattr(tb, 'justifty') and tb.justify == 'center' and hasattr(tb, 'alignVertical') and tb.alignVertical == 'top' and hasattr(tb, 'size') and tb.size > 18:
                return tb.content
        return "Error reading title"

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
        m1 = self.score.parts[0].measures(1, 1)
        initial_time_signature = None
        if (len(self.score.parts[0].getElementsByClass('Measure')[0].getElementsByClass(meter.TimeSignature)) > 0):
            initial_time_signature = self.score.parts[0].getElementsByClass('Measure')[0].getElementsByClass(meter.TimeSignature)[0]
        return self.describe_time_signature(initial_time_signature)

    def describe_time_signature(self, ts):
        if ts != None:
            return " ".join(ts.ratioString.split("/"))
        else:
            return " error reading time signature...  "

    def get_initial_key_signature(self):
        m1 = self.score.parts[0].measures(1, 1)
        if len(m1.flat.getElementsByClass('KeySignature')) == 0:
            ks = key.KeySignature(0)
        else:
            ks = m1.flat.getElementsByClass('KeySignature')[0]
        return self.describe_key_signature(ks)

    def describe_key_signature(self, ks):
        strKeySig = "No sharps or flats"
        if (ks.sharps > 0):
            strKeySig = str(ks.sharps) + " sharps"
        elif (ks.sharps < 0):
            strKeySig = str(abs(ks.sharps)) + " flats"
        return strKeySig

    # this was used to get the first tempo - but MetronomeMarkBoundary is better
    def get_initial_text_expression(self):
        # Get the first measure of the first part
        m1 = self.score.parts[0].measures(1, 1)
        # Get the text expressions from that measure
        text_expressions = m1.flat.getElementsByClass('TextExpression')
        for te in text_expressions:
            return te.content

    def get_initial_tempo(self):
        global settings
        try:
            settings
        except NameError:
            settings = None
        if settings == None:
            settings = {}
            settings['dotPosition'] = "before"
            settings['rhythmDescription'] = "british"
        return self.describe_tempo(self.score.metronomeMarkBoundaries()[0][2])

    # some tempos have soundingNumber set but not number
    # we would get an error trying to scale a tempo.number of None
    # static so that it can be called by eg midiHandler when scaling tempos
    @staticmethod
    def fix_tempo_number(tempo):
        if (tempo.number == None):
            if (tempo.numberSounding != None):
                tempo.number = tempo.numberSounding
            else:
                tempo.number = 120
                tempo.text = "Error - " + tempo.text
        return tempo

    def describe_tempo(self, tempo):
        tempo_text = ""
        tempo = self.fix_tempo_number(tempo)
        if (tempo.text != None):
            tempo_text += tempo.text + " (" + str(math.floor(tempo.number)) + " bpm @ " + self.describe_tempo_referent(tempo) + ")"
        else:
            tempo_text += str(math.floor(tempo.number)) + " bpm @ " + self.describe_tempo_referent(tempo)
        return tempo_text

    # the referent is the beat duration ie are you counting crotchets or minims etc
    def describe_tempo_referent(self, tempo):
        global settings
        tempo_text = ""
        if settings['dotPosition'] == "before":
            tempo_text = self._DOTS_MAP.get(tempo.referent.dots)
        tempo_text += self.map_duration(tempo.referent)
        if settings['dotPosition'] == "after":
            tempo_text += " " + self._DOTS_MAP.get(tempo.referent.dots)

        return tempo_text

    def get_number_of_bars(self):
        return len(self.score.parts[0].getElementsByClass('Measure'))

    # eg flute, piano, recorder, piano
    # part_instruments = {1: ['Flute', 0, 1, 'P1'], 2: ['Piano', 1, 2, 'P2'], 3: ['Recorder', 3, 1, 'P3'], 4: ['Piano', 4, 2, 'P4']}
    # part_names = {1: 'Right hand', 2: 'Left hand', 4: 'Right hand', 5: 'Left hand'}
    # instrument names = ['Flute', 'Piano', 'Recorder', 'Piano']
    def get_instruments(self):
        # eg instrument.Name = Piano, instrument.partId = 1.  A piano has 2 staves ie two parts with the same name and same ID.  But if you have a second piano, it will have the same name but a different partId
        self.part_instruments = {}  # key = instrument (1 based), value = ["part name", 1st part index 0 based, number of parts, instrument.partId]
        self.part_names = {}  # key = part index 0 based, {part name eg "left hand" or "right hand" etc} - but part only included if instrument has multiple parts.
        instrument_names = []  # each instrument instrument once even if it has multiple parts.  still needed for Info / Options page
        ins_count = 1
        for c, instrument in enumerate(self.score.flat.getInstruments()):
            if len(self.part_instruments) == 0 or self.part_instruments[ins_count-1][3] != instrument.partId:
                pname = instrument.partName
                if pname == None:
                    pname = "Instrument  " + str(ins_count) + " (unnamed)"
                self.part_instruments[ins_count] = [pname, c, 1, instrument.partId]
                instrument_names.append(pname)

                ins_count += 1
            else:
                self.part_instruments[ins_count-1][2] += 1
                # todo - there is a more efficient way of doing this - or just let the user enter part names on the options screen - but these are OK for defaults
                if self.part_instruments[ins_count-1][2] == 2:
                    self.part_names[c-1] = "Right hand"
                    self.part_names[c] = "Left hand"
                elif self.part_instruments[ins_count-1][2] == 3:
                    self.part_names[c-2] = "Part 1"
                    self.part_names[c-1] = "Part 2"
                    self.part_names[c] = "Part 3"
                else:
                    self.part_names[c] = "Part " + str(self.part_instruments[ins_count-1][2])

        logger.debug(f"part instruments = {self.part_instruments}")
        print("part names = " + str(self.part_names))
        print("instrument names = " + str(instrument_names))
        return instrument_names

    def compare_parts_with_selected_instruments(self):
        global settings
        self.selected_instruments = []  # 1 based list of keys from part_instruments eg [1, 4]
        self.unselected_instruments = []  # eg [2,3]
        self.binary_selected_instruments = 1  # bitwise representation of all instruments - 0=not included, 1=included
        self.selected_part_names = []  # eg ["recorder", "piano - left hand", "piano - right hand"]
        for ins in self.part_instruments.keys():
            self.binary_selected_instruments = self.binary_selected_instruments << 1
            if ins in settings['instruments']:
                self.selected_instruments.append(ins)
                self.binary_selected_instruments += 1
            else:
                self.unselected_instruments.append(ins)

        for ins in self.selected_instruments:
            ins_name = self.part_instruments[ins][0]
            if self.part_instruments[ins][2] == 1:  # instrument only has one part
                self.selected_part_names.append(ins_name)
            else:  # instrument has multiple parts
                pn1index = self.part_instruments[ins][1]
                for pni in range(pn1index, pn1index+self.part_instruments[ins][2]):
                    self.selected_part_names.append(ins_name + " - " + self.part_names[pni])

        print("selected_part_names = " + str(self.selected_part_names))

        if len(self.unselected_instruments) == 0:  # All instruments selected - so no unselected instruments to play
            settings['playUnselected'] = False
        if len(self.selected_instruments) == len(self.part_instruments) and settings['playAll'] == True:  # played by Play All
            settings['playSelected'] = False
        if len(self.selected_instruments) == 1:  # played by individual part
            settings['playSelected'] = False
        if len(self.part_instruments) == 1:
            settings['playAll'] = False

        # todo - these maybe shouldn't really be part of score...
        self.binary_play_all = 1  # placeholder,all,selected,unslected
        self.binary_play_all = self.binary_play_all << 1
        if settings['playAll'] == True:
            self.binary_play_all += 1
        self.binary_play_all = self.binary_play_all << 1
        if settings['playSelected'] == True:
            self.binary_play_all += 1
        self.binary_play_all = self.binary_play_all << 1
        if settings['playUnselected'] == True:
            self.binary_play_all += 1

        print("selected_instruments = " + str(self.selected_instruments))

    def get_number_of_parts(self):
        self.get_instruments()
        return len(self.part_instruments)

    def get_bar_range(self, range_start, range_end):
        measures = self.score.measures(range_start, range_end)
        bars_for_parts = {}
        for part in measures.parts:
            bars_for_parts.setdefault(part.id, []).extend(part.getElementsByClass('Measure'))

        return bars_for_parts

    def get_events_for_bar_range(self, start_bar, end_bar, part_index):
        events_by_bar = {}

        # using collect=('TimeSignature') is slow.  It is almost twice as fast to use a dictionary of time signatures and insert at the start of each segment.
        measures = self.score.parts[part_index].measures(start_bar, end_bar)
        if measures.measure(start_bar) != None and len(measures.measure(start_bar).getElementsByClass(meter.TimeSignature)) == 0:
            measures.measure(start_bar).insert(0, self.timeSigs[start_bar])

        logger.info(f'Processing part - {part_index} - bars {start_bar} to {end_bar}')
        # Iterate over the bars one at a time
        # pickup bar has to request measures 0 to 1 above otherwise it returns an measures just has empty parts - so now restrict it just to bar 0...
        if start_bar == 0 and end_bar == 1:
            end_bar = 0
        for bar_index in range(start_bar, end_bar + 1):
            measure = measures.measure(bar_index)
            if measure is not None:
                self.update_events_for_measure(measure, events_by_bar)

        # Iterate over the spanners
        # todo - mention slurs?  Make it an option?
        # todo - this looks at spanners per part so eg crescendos are described for the right hand but not the left of a piano...
        # todo - it is a bit inefficient.  It looks spanners from the start of the part for each segment...
        for spanner in self.score.parts[part_index].spanners.elements:
            first = spanner.getFirst()
            last = spanner.getLast()
            if first.measureNumber is None or last.measureNumber is None:
                continue
            elif first.measureNumber > end_bar:  # all remaining spanners are after this segment so break the for loop
                break

            spanner_type = type(spanner).__name__
            if spanner_type == 'Crescendo' or spanner_type == 'Diminuendo':
                description_order = 0
                voice = 1

                if first.measureNumber >= start_bar and first.measureNumber <= end_bar:
                    event = TSDynamic(long_name=f'{spanner_type} start')
                    events_by_bar\
                        .setdefault(first.measureNumber, {})\
                        .setdefault(first.beat, {})\
                        .setdefault(voice, {})\
                        .setdefault(description_order, [])\
                        .append(event)

                if last.measureNumber >= start_bar and last.measureNumber <= end_bar:
                    event = TSDynamic(long_name=f'{spanner_type} end')
                    # todo -  Note - THIS WILL NOT HANDLE CRESCENDOS/DIMINUENDOS THAT SPAN MEASURES
                    events_by_bar\
                        .setdefault(last.measureNumber, {})\
                        .setdefault(last.beat + last.duration.quarterLength - 1, {})\
                        .setdefault(voice, {})\
                        .setdefault(description_order, [])\
                        .append(event)

        return events_by_bar

    def update_events_for_measure(self, measure, events, voice: int = 1):
        previous_beat = 1
        for element in measure.elements:
            element_type = type(element).__name__
            event = None
            if element_type == 'Note':
                event = TSNote()
                event.pitch = TSPitch(self.map_pitch(element.pitch), self.map_octave(element.pitch.octave), element.pitch.ps, element.pitch.name[0])
                description_order = 1
                if element.tie:
                    event.tie = element.tie.type

                event.expressions = element.expressions
            elif element_type == 'Unpitched':
                event = TSUnpitched()
                description_order = 1
            elif element_type == 'Rest':
                event = TSRest()
                description_order = 1

            elif element_type == 'Chord':
                event = TSChord()
                event.pitches = [TSPitch(self.map_pitch(element_pitch), self.map_octave(element_pitch.octave), element_pitch.ps, element_pitch.name[0]) for element_pitch in element.pitches]
                description_order = 1
                if element.tie:
                    event.tie = element.tie.type

            elif element_type == 'Dynamic':
                event = TSDynamic(long_name=element.longName, short_name=element.value)
                description_order = 0  # Always speak the dynamic first

            elif element_type == 'Voice':
                self.update_events_for_measure(element, events, int(element.id))

            if event is None:
                continue

            # This test isn't WORKING
            # if TSEvent.__class__ in event.__class__.__bases__:
            event.duration = ""
            if (len(element.duration.tuplets) > 0):
                if (element.duration.tuplets[0].type == "start"):
                    if (element.duration.tuplets[0].fullName == "Triplet"):
                        event.tuplets = "triplets "
                    else:
                        event.tuplets = element.duration.tuplets[0].fullName + " (" + str(element.duration.tuplets[0].tupletActual[0]) + " in " + str(element.duration.tuplets[0].tupletNormal[0]) + ") "
                elif (element.duration.tuplets[0].type == "stop" and element.duration.tuplets[0].fullName != "Triplet"):
                    event.endTuplets = "end tuplet "

            if settings['dotPosition'] == "before":
                event.duration += self.map_dots(element.duration.dots)
            event.duration += self.map_duration(element.duration)
            if settings['dotPosition'] == "after":
                event.duration += " " + self.map_dots(element.duration.dots)

            if (math.floor(element.beat) == math.floor(previous_beat)):  # eg was 1 now 1.5 ie same beat
                beat = previous_beat
            elif (math.floor(element.beat) == element.beat):  # was 1.5 now 2.0 - ie start of a new beat
                beat = math.floor(element.beat)  # strip off the point 0
            else:  # eg was 1 now 2.5 ie part way through a new beat - mention decimal
                beat = element.beat
            previous_beat = beat

            events\
                .setdefault(measure.measureNumber, {})\
                .setdefault(beat, {})\
                .setdefault(voice, {})\
                .setdefault(description_order, [])\
                .append(event)

    def group_chord_pitches_by_octave(self, chord):
        chord_pitches_by_octave = {}
        for pitch in chord.pitches:
            chord_pitches_by_octave.setdefault(self._PITCH_MAP.get(str(pitch.octave), '?'), []).append(pitch.name)

        return chord_pitches_by_octave

    # for all / selected / unselected
    def generate_midi_filename_sel(self, prefix, range_start=None, range_end=None, output_path="", sel=""):
        base_filename = os.path.splitext(os.path.basename(self.filepath))[0]
        if (range_start != None):
            midi_filename = os.path.join(output_path, f"{base_filename}.mid?sel={sel}&start={range_start}&end={range_end}&t=100&c=n")
        else:
            midi_filename = os.path.join(output_path, f"{base_filename}.mid?sel={sel}&t=100&c=n")
        return (prefix+os.path.basename(midi_filename))

    def generate_part_descriptions(self, instrument, start_bar, end_bar):
        part_descriptions = []
        for pi in range(self.part_instruments[instrument][1], self.part_instruments[instrument][1]+self.part_instruments[instrument][2]):
            part_descriptions.append(self.get_events_for_bar_range(start_bar, end_bar, pi))

        return part_descriptions

    def generate_midi_filenames(self, prefix, range_start=None, range_end=None, add_instruments=[], output_path="", postfix_filename=""):
        part_midis = []
        if range_start is None and range_end is None:
            for ins in add_instruments:
                for pi in range(self.part_instruments[ins][1], self.part_instruments[ins][1]+self.part_instruments[ins][2]):
                    if self.part_instruments[ins][2] > 1:
                        base_filename = os.path.splitext(os.path.basename(self.filepath))[0]
                        midi_filename = os.path.join(output_path, f"{base_filename}.mid?part={pi}&t=100&c=n")
                        part_midis.append(midi_filename)
        else:  # specific measures
            for ins in add_instruments:
                for pi in range(self.part_instruments[ins][1], self.part_instruments[ins][1]+self.part_instruments[ins][2]):
                    if self.part_instruments[ins][2] > 1:
                        base_filename = os.path.splitext(os.path.basename(self.filepath))[0]
                        midi_filename = os.path.join(output_path, f"{base_filename}.mid?part={pi}&start={range_start}&end={range_end}&t=100&c=n")
                        part_midis.append(midi_filename)

        base_filename = os.path.splitext(os.path.basename(self.filepath))[0]
        if (range_start != None):
            midi_filename = os.path.join(output_path, f"{base_filename}.mid?ins={ins}&start={range_start}&end={range_end}&t=100&c=n")
        else:
            midi_filename = os.path.join(output_path, f"{base_filename}.mid?ins={ins}&t=100&c=n")
        part_midis = [prefix + os.path.basename(s) for s in part_midis]
        return (prefix+os.path.basename(midi_filename), part_midis)

    def generate_midi_for_instruments(self, prefix, range_start=None, range_end=None, add_instruments=[], output_path="", postfix_filename=""):
        part_midis = []
        s = stream.Score(id='temp')

        if range_start is None and range_end is None:
            for ins in add_instruments:
                for pi in range(self.part_instruments[ins][1], self.part_instruments[ins][1]+self.part_instruments[ins][2]):
                    s.insert(self.score.parts[pi])
                    if self.part_instruments[ins][2] > 1:
                        part_midis.append(self.generate_midi_parts_for_instrument(range_start, range_end, ins, pi-self.part_instruments[ins][1], output_path, postfix_filename))

        else:  # specific measures
            postfix_filename += "_" + str(range_start) + str(range_end)
            for ins in add_instruments:
                firstPart = True
                for pi in range(self.part_instruments[ins][1], self.part_instruments[ins][1]+self.part_instruments[ins][2]):
                    if self.part_instruments[ins][2] > 1:
                        part_midis.append(self.generate_midi_parts_for_instrument(range_start, range_end, ins, pi-self.part_instruments[ins][1], output_path, postfix_filename))
                    pi_measures = self.score.parts[pi].measures(range_start, range_end, collect=('Clef', 'TimeSignature', 'Instrument', 'KeySignature', 'TempoIndication'))
                    if firstPart:
                        if pi != 0:  # only part 0 has tempos
                            self.insert_tempos(pi_measures, self.score.parts[0].measure(range_start).offset)
                        firstPart = False

                    # music21 v6.3.0 tries to expand repeats - which causes error if segment only includes the start repeat mark
                    for m in pi_measures.getElementsByClass('Measure'):
                        m.removeByClass('Repeat')
                    s.insert(pi_measures)

        base_filename = os.path.splitext(os.path.basename(self.filepath))[0]
        midi_filename = os.path.join(output_path, f"{base_filename}{postfix_filename}.mid")
        # todo - might need to add in tempos if part 0 is not included
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
            midi_filename = os.path.join(output_path, f"{base_filename}{postfix_filename}_p{(part+1)}.mid")
            if not os.path.exists(midi_filename):
                s.write('midi', midi_filename)
        else:  # specific measures
            postfix_filename += "_" + str(range_start) + str(range_end)
            s = stream.Score(id='temp')
            print("506 instrument = " + str(instrument) + " part = " + str(part))
            pi_measures = self.score.parts[self.part_instruments[instrument][1]+part].measures(range_start, range_end, collect=('Clef', 'TimeSignature', 'Instrument', 'KeySignature', 'TempoIndication'))
            if self.part_instruments[instrument][1]+part != 0:  # only part 0 has tempos
                self.insert_tempos(pi_measures, self.score.parts[0].measure(range_start).offset)

            # music21 v6.3.0 tries to expand repeats - which causes error if segment only includes the start repeat mark
            for m in pi_measures.getElementsByClass('Measure'):
                m.removeByClass('Repeat')
            s.insert(pi_measures)

            base_filename = os.path.splitext(os.path.basename(self.filepath))[0]
            midi_filename = os.path.join(output_path, f"{base_filename}{postfix_filename}_p{(part+1)}.mid")
            if not os.path.exists(midi_filename):
                s.write('midi', midi_filename)
        return midi_filename

    def generate_midi_for_part_range(self, range_start=None, range_end=None, parts=[], output_path=""):

        base_filename = os.path.splitext(os.path.basename(self.filepath))[0]
        if range_start is None and range_end is None:
            # Export the whole score
            midi_filename = os.path.join(output_path, f"{base_filename}.mid")
            if not os.path.exists(midi_filename):
                self.score.write('midi', midi_filename)
            return midi_filename
        elif len(parts) > 0:  # individual parts
            for p in self.score.parts:
                if p.id not in parts:
                    continue

                midi_filename = os.path.join(output_path, f"{base_filename}_p{p.id}_{range_start}_{range_end}.mid")
                if not os.path.exists(midi_filename):
                    midi_stream = p.measures(range_start, range_end, collect=('Clef', 'TimeSignature', 'Instrument', 'KeySignature', 'TempoIndication'))
                    if p != self.score.parts[0]:  # only part 0 has tempos
                        self.insert_tempos(midi_stream, self.score.parts[0].measure(range_start).offset)
                    # music21 v6.3.0 tries to expand repeats - which causes error if segment only includes the start repeat mark
                    for m in midi_stream.getElementsByClass('Measure'):
                        m.removeByClass('Repeat')
                    midi_stream.write('midi', midi_filename)
                return midi_filename
        else:  # both hands
            midi_filename = os.path.join(output_path, f"{base_filename}_{range_start}_{range_end}.mid")
            if not os.path.exists(midi_filename):
                midi_stream = self.score.measures(range_start, range_end, collect=('Clef', 'TimeSignature', 'Instrument', 'KeySignature', 'TempoIndication'))
                # music21 v6.3.0 tries to expand repeats - which causes error if segment only includes the start repeat mark
                for pa in midi_stream.getElementsByClass('Part'):
                    for m in pa.getElementsByClass('Measure'):
                        m.removeByClass('Repeat')
                midi_stream.write('midi', midi_filename)
            return midi_filename

        return None

    # TODO need to make more efficient when working with multiple parts ie more than just the left hand piano part
    # music21 might have a better way of doing this.  If part 0 is included then tempos are already present.
    def insert_tempos(self, stream, offset_start):
        if (self.last_tempo_inserted_index > 0):  # one tempo change might need to be in many segments - especially the last tempo change in the score
            self.last_tempo_inserted_index -= 1
        for mmb in self.score.metronomeMarkBoundaries()[self.last_tempo_inserted_index:]:
            if (mmb[0] >= offset_start+stream.duration.quarterLength):  # ignore tempos that start after stream ends
                return
            if (mmb[1] > offset_start):  # if mmb ends during the segment
                if (mmb[0]) <= offset_start:  # starts before segment so insert it at the start of the stream
                    stream.insert(0, tempo.MetronomeMark(number=mmb[2].number))
                    self.last_tempo_inserted_index += 1
                else:  # starts during segment so insert it part way through the stream
                    stream.insert(mmb[0]-offset_start, tempo.MetronomeMark(number=mmb[2].number))
                    self.last_tempo_inserted_index += 1

    def map_octave(self, octave):
        global settings
        if settings['octaveDescription'] == "figureNotes":
            return self._OCTAVE_FIGURENOTES_MAP.get(octave, "?")
        elif settings['octaveDescription'] == "name":
            return self._OCTAVE_MAP.get(octave, "?")
        elif settings['octaveDescription'] == "none":
            return ""
        elif settings['octaveDescription'] == "number":
            return str(octave)

        # return f"{self._PITCH_MAP.get(pitch[-1], '')} {pitch[0]}"

    def map_pitch(self, pitch):
        global settings
        if settings['pitchDescription'] == "colourNotes":
            pitch_name = self._PITCH_FIGURENOTES_MAP.get(pitch.name[0], "?")
        if settings['pitchDescription'] == "noteName":
            pitch_name = pitch.name[0]
        elif settings['pitchDescription'] == "none":
            pitch_name = ""
        elif settings['pitchDescription'] == "phonetic":
            pitch_name = self._PITCH_PHONETIC_MAP.get(pitch.name[0], "?")

        if pitch.accidental and pitch.accidental.displayStatus and pitch_name != "":
            pitch_name = f"{pitch_name} {pitch.accidental.fullName}"
        return pitch_name

    def map_duration(self, duration):
        global settings
        if settings['rhythmDescription'] == "american":
            return duration.type
        elif settings['rhythmDescription'] == "british":
            return self._DURATION_MAP.get(duration.type, f'Unknown duration {duration.type}')
        elif settings['rhythmDescription'] == "none":
            return ""

    def map_dots(self, dots):
        if settings['rhythmDescription'] == "none":
            return ""
        else:
            return self._DOTS_MAP.get(dots)


class HTMLTalkingScoreFormatter():

    def __init__(self, talking_score):
        global settings

        self.score: Music21TalkingScore = talking_score

        options_path = self.score.filepath + '.opts'
        with open(options_path, "r") as options_fh:
            options = json.load(options_fh)
        settings = {
            'pitchBeforeDuration': False,
            'describeBy': 'beat',
            'handsTogether': True,
            'barsAtATime': int(options["bars_at_a_time"]),
            'playAll': options["play_all"],
            'playSelected': options["play_selected"],
            'playUnselected': options["play_unselected"],
            'instruments': options["instruments"],
            'pitchDescription': options["pitch_description"],
            'rhythmDescription': options["rhythm_description"],
            'dotPosition': options["dot_position"],
            'rhythmAnnouncement': options["rhythm_announcement"],
            'octaveDescription': options["octave_description"],
            'octavePosition': options["octave_position"],
            'octaveAnnouncement': options["octave_announcement"],
            'colourPosition': options["colour_position"],
            'colourPitch': options["colour_pitch"],
            'colourRhythm': options["colour_rhythm"],
            'colourOctave': options["colour_octave"],
        }

    def generateHTML(self, output_path="", web_path=""):
        global settings
        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader(os.path.dirname(__file__)))
        template = env.get_template('talkingscore.html')

        self.score.get_instruments()
        self.score.compare_parts_with_selected_instruments()
        print("Settings...")
        print(settings)

        self.music_analyser = MusicAnalyser()
        self.music_analyser.setScore(self.score)
        start = self.score.score.parts[0].getElementsByClass('Measure')[0].number
        end = self.score.score.parts[0].getElementsByClass('Measure')[-1].number
        selected_instruments_midis = {}
        for index, ins in enumerate(self.score.selected_instruments):
            midis = self.score.generate_midi_filenames(prefix="/midis/" + os.path.basename(web_path) + "/", range_start=start, range_end=end, output_path=output_path, add_instruments=[ins], postfix_filename="ins"+str(index))
            selected_instruments_midis[ins] = {"ins": ins,  "midi": midis[0], "midi_parts": midis[1]}

        midiAll = self.score.generate_midi_filename_sel(prefix="/midis/" + os.path.basename(web_path) + "/", output_path=output_path, range_start=start, range_end=end, sel="all")
        midiSelected = self.score.generate_midi_filename_sel(prefix="/midis/" + os.path.basename(web_path) + "/", output_path=output_path, range_start=start, range_end=end, sel="sel")
        midiUnselected = self.score.generate_midi_filename_sel(prefix="/midis/" + os.path.basename(web_path) + "/", output_path=output_path, range_start=start, range_end=end, sel="un")
        full_score_midis = {'selected_instruments_midis': selected_instruments_midis, 'midi_all': midiAll, 'midi_sel': midiSelected, 'midi_un': midiUnselected}

        return template.render({'settings': settings,
                                'basic_information': self.get_basic_information(),
                                'preamble': self.get_preamble(),
                                'full_score_midis': full_score_midis,
                                'music_segments': self.get_music_segments(output_path, web_path, ),
                                'instruments': self.score.part_instruments,
                                'part_names': self.score.part_names,
                                'binary_selected_instruments': self.score.binary_selected_instruments,
                                'binary_play_all': self.score.binary_play_all,
                                'play_all': settings['playAll'],
                                'play_selected': settings['playSelected'],
                                'play_unselected': settings['playUnselected'],
                                'time_and_keys': self.time_and_keys,
                                'parts_summary': self.music_analyser.summary_parts,
                                'general_summary': self.music_analyser.general_summary,
                                'repetition_in_contexts': self.music_analyser.repetition_in_contexts,
                                'selected_part_names': self.score.selected_part_names,
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

    def get_music_segments(self, output_path, web_path):
        print("web path = ")
        print(web_path)
        print("base name webpath = ")
        print(os.path.basename(web_path))

        global settings
        logger.info("Start of get_music_segments")
        music_segments = []
        number_of_bars = self.score.get_number_of_bars()

        t1s = time.time()
        self.time_and_keys = {}  # index is bar number, key = "Time sig x of y - 4 4..."
        total = len(self.score.score.parts[0].flat.getElementsByClass('TimeSignature'))
        for count, ts in enumerate(self.score.score.parts[0].flat.getElementsByClass('TimeSignature')):
            description = "Time signature - " + str(count+1) + " of " + str(total) + " is " + self.score.describe_time_signature(ts) + ".  "
            self.time_and_keys.setdefault(ts.measureNumber, []).append(description)

        total = len(self.score.score.parts[0].flat.getElementsByClass('KeySignature'))
        for count, ks in enumerate(self.score.score.parts[0].flat.getElementsByClass('KeySignature')):
            description = "Key signature - " + str(count+1) + " of " + str(total) + " is " + self.score.describe_key_signature(ks) + ".  "
            self.time_and_keys.setdefault(ks.measureNumber, []).append(description)

        self.score.timeSigs = {}  # key=bar number.  Value = timeSig
        previous_ts = self.score.score.parts[0].getElementsByClass('Measure')[0].getTimeSignatures()[0]

        # pickup bar
        if self.score.score.parts[0].getElementsByClass('Measure')[0].number != self.score.score.parts[0].measures(1, 2).getElementsByClass('Measure')[0].number:
            previous_ts = self.score.score.parts[0].getElementsByClass('Measure')[0].getElementsByClass(meter.TimeSignature)[0]
            self.score.timeSigs[0] = previous_ts
            # todo - where should spanners and dynamics etc go?
            selected_instruments_descriptions = {}  # key = instrument index, {[part descriptions]}

            selected_instruments_midis = {}
            for index, ins in enumerate(self.score.selected_instruments):
                logger.debug(f"enumerate selected instruments... index = {index} and ins ={ins}")
                midis = self.score.generate_midi_filenames(prefix="/midis/" + os.path.basename(web_path) + "/", range_start=0, range_end=0, output_path=output_path, add_instruments=[ins], postfix_filename="ins"+str(index))
                selected_instruments_midis[ins] = {"ins": ins,  "midi": midis[0], "midi_parts": midis[1]}
                selected_instruments_descriptions[ins] = self.score.generate_part_descriptions(instrument=ins, start_bar=0, end_bar=1)
            midiAll = self.score.generate_midi_filename_sel(prefix="/midis/" + os.path.basename(web_path) + "/", output_path=output_path, range_start=0, range_end=0, sel="all")
            midiSelected = self.score.generate_midi_filename_sel(prefix="/midis/" + os.path.basename(web_path) + "/", output_path=output_path, range_start=0, range_end=0, sel="sel")
            midiUnselected = self.score.generate_midi_filename_sel(prefix="/midis/" + os.path.basename(web_path) + "/", output_path=output_path, range_start=0, range_end=0, sel="un")

            music_segment = {'start_bar': '0 - pickup', 'end_bar': '0 - pickup', 'selected_instruments_descriptions': selected_instruments_descriptions, 'selected_instruments_midis': selected_instruments_midis,  'midi_all': midiAll, 'midi_sel': midiSelected, 'midi_un': midiUnselected}
            music_segments.append(music_segment)
            number_of_bars -= 1

        # everything except the pickup
        for bar_index in range(1, number_of_bars+1, settings['barsAtATime']):
            end_bar_index = bar_index + settings['barsAtATime'] - 1
            if end_bar_index > number_of_bars:
                end_bar_index = number_of_bars

            # cludge to not have None bars - but will actually ignore some...
            # todo - we get the number of bars just by the length and use that as the maximum bar number.  However- sometimes bars are called "X1" for half bars next to a repeat.  Or Finale re-uses bar numbers for sections - so need a better way of getting each bar...
            if (self.score.score.parts[0].measure(bar_index) == None):
                print("start bar is none...")
                break
            while (end_bar_index >= 1 and self.score.score.parts[0].measure(end_bar_index+1) == None):
                end_bar_index = end_bar_index - 1
                print("end bar index was too big - now " + str(end_bar_index))
            # if there is only 1 bar - and it isn't a pickup bar
            if end_bar_index == 0 and self.score.score.parts[0].measure(0) == None:
                end_bar_index = 1
            for checkts in range(bar_index, end_bar_index+1):
                if (self.score.score.parts[0].measure(bar_index) == None):
                    print("bar " + str(bar_index) + " is None...")
                elif len(self.score.score.parts[0].measure(bar_index).getElementsByClass(meter.TimeSignature)) > 0:
                    previous_ts = self.score.score.parts[0].measure(bar_index).getElementsByClass(meter.TimeSignature)[0]
                self.score.timeSigs[checkts] = previous_ts

            # for offset, events in events_for_bar_range.iteritems():
            # events_ordered_by_beat = OrderedDict(sorted(events_for_bar_range.items(), key=lambda t: t[0]))

            # pp = pprint.PrettyPrinter(indent=4)
            # pp.pprint(events_by_bar_and_beat)

            selected_instruments_descriptions = {}  # key = instrument index,
            selected_instruments_midis = {}
            for index, ins in enumerate(self.score.selected_instruments):
                logger.debug(f"adding to selected_instruments_descriptions - index = {index} and ins = {ins}")
                midis = self.score.generate_midi_filenames(prefix="/midis/" + os.path.basename(web_path) + "/", range_start=bar_index, range_end=end_bar_index, output_path=output_path, add_instruments=[ins], postfix_filename="ins"+str(index))
                selected_instruments_midis[ins] = {"ins": ins,  "midi": midis[0], "midi_parts": midis[1]}
                selected_instruments_descriptions[ins] = self.score.generate_part_descriptions(instrument=ins, start_bar=bar_index, end_bar=end_bar_index)

            midiAll = self.score.generate_midi_filename_sel(prefix="/midis/" + os.path.basename(web_path) + "/", output_path=output_path, range_start=bar_index, range_end=end_bar_index, sel="all")
            midiSelected = self.score.generate_midi_filename_sel(prefix="/midis/" + os.path.basename(web_path) + "/", output_path=output_path, range_start=bar_index, range_end=end_bar_index, sel="sel")
            midiUnselected = self.score.generate_midi_filename_sel(prefix="/midis/" + os.path.basename(web_path) + "/", output_path=output_path, range_start=bar_index, range_end=end_bar_index, sel="un")

            music_segment = {'start_bar': bar_index, 'end_bar': end_bar_index,  'selected_instruments_descriptions': selected_instruments_descriptions, 'selected_instruments_midis': selected_instruments_midis, 'midi_all': midiAll, 'midi_sel': midiSelected, 'midi_un': midiUnselected}
            music_segments.append(music_segment)

        logger.info("End of get_music_segments")
        t1e = time.time()
        print("described parts etc = " + str(t1e-t1s))
        return music_segments


if __name__ == '__main__':

    # testScoreFilePath = '../talkingscoresapp/static/data/macdowell-to-a-wild-rose.xml'
    testScoreFilePath = '../media/172a28455fa5cfbdaa4eecd5f63a0a2ebaddd92d569980fb402811b9cd5cce4a/MozartPianoSonata.xml'
    # testScoreFilePath = '../talkingscores/talkingscoresapp/static/data/bach-2-part-invention-no-13.xml'

    testScoreOutputFilePath = testScoreFilePath.replace('.xml', '.html')

    testScore = Music21TalkingScore(testScoreFilePath)
    tsf = HTMLTalkingScoreFormatter(testScore)
    html = tsf.generateHTML()

    with open(testScoreOutputFilePath, "wb") as fh:
        fh.write(html)

    os.system(f'open http://0.0.0.0:8000/static/data/{os.path.basename(testScoreOutputFilePath)}')
