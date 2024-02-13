__author__ = 'PMarchant'

import os
import json
import math
import logging
import logging.handlers
import logging.config
from tracemalloc import BaseFilter
from music21 import *
from talkingscores.settings import BASE_DIR, MEDIA_ROOT, STATIC_ROOT, STATIC_URL
from talkingscoreslib import Music21TalkingScore

logger = logging.getLogger("TSScore")


class MidiHandler:
    def __init__(self, get, folder, filename):
        self.queryString = get
        self.folder = folder
        self.filename = filename.replace(".mid", "")

    # get list of selected / unselected instruments from binary of number.  Leftmost value is always 1
    def get_selected_instruments(self):
        bsi = int(self.queryString.get("bsi"))
        self.selected_instruments = []
        while (bsi > 1):
            logger.debug(f"bsi = {bsi}")
            if (bsi & 1 == True):
                self.selected_instruments.append(True)
            else:
                self.selected_instruments.append(False)
            bsi = bsi >> 1
        self.selected_instruments.reverse()
        logger.debug(f"selected_instruments = {self.selected_instruments}")

        self.all_selected_parts = []
        self.all_unselected_parts = []
        self.selected_instruement_parts = {}  # key = instrument, value = [parts]

        instrument_index = -1
        prev_instrument = ""
        for part_index, part in enumerate(self.score.flat.getInstruments()):
            logger.debug(f"part_index = {part_index}")
            logger.debug(part)
            if part.partId != prev_instrument:
                instrument_index += 1
                self.selected_instruement_parts.get(instrument_index)

            if (self.selected_instruments[instrument_index] == True):
                self.all_selected_parts.append(part_index)
                if (instrument_index in self.selected_instruement_parts.keys()):
                    self.selected_instruement_parts[instrument_index].append(part_index)
                else:
                    self.selected_instruement_parts[instrument_index] = [part_index]
            else:
                self.all_unselected_parts.append(part_index)
                self.selected_instruement_parts[instrument_index] = []

            prev_instrument = part.partId

        logger.debug(f"all_selected_parts = {self.all_selected_parts}")
        logger.debug(f"all_unselected_parts = {self.all_unselected_parts}")
        logger.debug(f"selected_instruement_parts = {self.selected_instruement_parts}")

        # play together - all / selected / unselected instruments
        bpi = int(self.queryString.get("bpi"))
        self.play_together_unselected = bpi & 1
        bpi = bpi >> 1
        self.play_together_selected = bpi & 1
        bpi = bpi >> 1
        self.play_together_all = bpi & 1
        bpi = bpi >> 1

        while (bsi > 1):
            logger.debug(f"bsi = {bsi}")
            if (bsi & 1 == True):
                self.selected_instruments.append(True)
            else:
                self.selected_instruments.append(False)
            bsi = bsi >> 1

    def make_midi_files(self):
        # todo - it is a bit slow for big musicxml files eg chaconne!
        # todo maybe get the segment of all parts then get parts from that.
        xml_file_path = os.path.join(*(MEDIA_ROOT, self.folder, self.filename))  # todo - might not be secure
        self.score = converter.parse(xml_file_path+".musicxml")  # todo - might be .xml instead of .musicxml
        self.get_selected_instruments()

        s = stream.Score(id='temp')

        if self.queryString.get("start") is None and self.queryString.get("end") is None:
            # todo - test for pickup bar
            start = self.score.parts[0].getElementsByClass('Measure')[0].number
            end = self.score.parts[0].getElementsByClass('Measure')[-1].number

        else:
            start = int(self.queryString.get("start"))
            end = int(self.queryString.get("end"))

        offset = self.score.parts[0].measure(start).offset

        # in very rough tests (same bars) using the segment then getting parts from that (instead of original stream) saves 1 or 2 seconds with 2 parts 261 bars, 2,060kb.
        # maybe a deep copy would be better?
        self.scoreSegment = stream.Score(id='tempSegment')
        for p in self.score.parts:
            # fix with pickup bar
            if start == 0 and end == 0:
                end = 1
            for m in p.measures(start, end).getElementsByClass('Measure'):
                # todo - test with repeats
                m.removeByClass('Repeat')
            self.scoreSegment.insert(p.measures(start, end, ))
            if start == 0 and end == 1:
                end = 0

        for click in ['n', 'be']:
            self.tempo_shift = 0  # in a pickup bar - a rest is added to the start of bar 0 to make it a full bar - this offset needs adding to all future tempos
            for tempo in [50, 100, 150]:
                # play all parts together
                if self.play_together_all:
                    self.make_midi_together(start, end, offset, tempo, click, "all")

                # play all selected parts together
                if self.play_together_selected:
                    self.make_midi_together(start, end, offset, tempo, click, "sel")

                # play all unselected parts together
                if self.play_together_unselected:
                    self.make_midi_together(start, end, offset, tempo, click, "un")

                # each instrument (with 1 or more parts) - if selected
                for index, parts_list in enumerate(self.selected_instruement_parts.values()):
                    if (len(parts_list) > 0):
                        s = stream.Score(id='temp')
                        for pi in parts_list:
                            s.insert(self.scoreSegment.parts[pi].measures(start, end, collect=('Clef', 'TimeSignature', 'Instrument', 'KeySignature')))
                        self.insert_tempos(s, offset, tempo/100)
                        self.insert_click_track(s, click)
                        s.write('midi', self.make_midi_path_from_options(start=start, end=end, ins=index+1, tempo=tempo, click=click))

                        # now each separate part if the instrument has more than 1 part
                        if (len(parts_list) > 1):
                            for pi in parts_list:
                                s = stream.Score(id='temp')
                                s.insert(self.scoreSegment.parts[pi].measures(start, end, collect=('Clef', 'TimeSignature', 'Instrument', 'KeySignature')))
                                self.insert_tempos(s, offset, tempo/100)
                                self.insert_click_track(s, click)
                                s.write('midi', self.make_midi_path_from_options(start=start, end=end, part=pi, tempo=tempo, click=click))

    # make a midi file of all / selected / unselected instruments played together

    def make_midi_together(self, start, end, offset, tempo, click, which_parts):
        parts_in = []
        if (which_parts == "sel"):
            parts_in = self.all_selected_parts
        elif (which_parts == "un"):
            parts_in = self.all_unselected_parts

        s = stream.Score(id='temp')
        for part_index, p in enumerate(self.scoreSegment.parts):
            if which_parts == "all" or part_index in parts_in:
                s.insert(p.measures(start, end, collect=('Clef', 'TimeSignature', 'Instrument', 'KeySignature')))
        self.insert_tempos(s, offset, tempo/100)
        self.insert_click_track(s, click)
        s.write('midi', self.make_midi_path_from_options(start=start, end=end, sel=which_parts, tempo=tempo, click=click))

    # If there is a pickup bar - add rests to the start - so the click track can start on beat 1
    def insert_click_track(self, s, click):
        if click == 'n':
            return

        # todo - use eg instrument.HiHatCymbal() etc after updating music21
        clicktrack = stream.Stream()
        # ins = instrument.Woodblock() # workds d#1 and d#5 ok ish.  beat 1 is too quiet
        ins = instrument.Percussion()
        ins.midiChannel = 9
        clicktrack.insert(0, ins)
        ts: meter.TimeSignature = None
        shift_measure_offset = 0
        for m in s.getElementsByClass(stream.Part)[0].getElementsByClass(stream.Measure):
            if len(m.getElementsByClass(meter.TimeSignature)) > 0:
                ts = m.getElementsByClass(meter.TimeSignature)[0]
            else:
                if (ts == None):
                    ts: meter.TimeSignature = m.previous('TimeSignature')
                # if the score didn't have a time signature - then just set it to 1/4 to get the first beat of each bar...
                if (ts == None):
                    ts = meter.TimeSignature('1/4')
            clickmeasure = stream.Measure()
            clickmeasure.mergeAttributes(m)
            clickmeasure.duration = ts.barDuration
            clickNote = note.Note('D2')
            clickNote.duration = ts.getBeatDuration(0)  # specify beat number for complex time signatures...
            clickmeasure.append(clickNote)
            beatpos = ts.getBeatDuration(0).quarterLength
            # if it is a pickup bar then add rests to bar 0 and shift the start offset of the future bars
            # todo - slight cludge for if the bar doesn't have anything in it (no notes or rests) - possibly should add in the rests at the start of processing
            if (m.duration.quarterLength < ts.barDuration.quarterLength and len(m.getElementsByClass(['Note', 'Rest'])) > 0):
                rest_duration = ts.barDuration.quarterLength - m.duration.quarterLength
                r = note.Rest()
                r.duration.quarterLength = rest_duration
                logger.debug(f"pickup bar - rest_duration = {rest_duration}")
                for p in self.scoreSegment.parts:  # change the bar start offset for all future streams.  Add a rest in all streams (including this one)
                    r = note.Rest()
                    r.duration.quarterLength = rest_duration
                    p.getElementsByClass(stream.Measure)[0].insertAndShift(0, r)
                    for ms in p.getElementsByClass(stream.Measure)[1:]:
                        ms.offset += rest_duration

                    logger.debug(f"now added rest to parts - duration = {rest_duration} and measure 0 duration = {p.getElementsByClass(stream.Measure)[0].duration.quarterLength}")
                for p in s.parts:  # change the bar start offsets for this stream
                    for ms in p.getElementsByClass(stream.Measure)[1:]:
                        ms.offset += rest_duration

                shift_measure_offset = rest_duration
                # update tempo offsets
                for t in s.getElementsByClass(tempo.MetronomeMark):
                    if (t.offset > 0):
                        t.offset += shift_measure_offset

                self.tempo_shift = rest_duration

            for b in range(0, ts.beatCount-1):
                clickNote = note.Note('F#2')
                clickNote.duration = ts.getBeatDuration(beatpos)
                beatpos += clickNote.duration.quarterLength
                clickmeasure.append(clickNote)

            clicktrack.append(clickmeasure)

        s.insert(clicktrack)

    # music21 might have a better way of doing this.
    # s.insert(self.score.parts[int(self.queryString.get("part"))].measures(start,end, collect=('Clef', 'TimeSignature', 'Instrument', 'KeySignature', 'TempoIndication'))) - collect doesn't seem to do anything!
    # If part 0 is included then tempos are already present.
    def insert_tempos(self, stream, offset_start, scale):
        for mmb in self.score.metronomeMarkBoundaries():
            if (mmb[0] >= offset_start+stream.duration.quarterLength):  # ignore tempos that start after stream ends
                return
            if (mmb[1] > offset_start):  # if mmb ends during the segment
                tempoNumber = Music21TalkingScore.fix_tempo_number(tempo=mmb[2]).number
                if (mmb[0]) <= offset_start:  # starts before segment so insert it at the start of the stream
                    # if there is a tempo already in the stream at offset 0 and we insert a different tempo - it seems to happen just before the original tempo so is ignored...
                    stream.insert(0.001, tempo.MetronomeMark(number=tempoNumber*scale, referent=mmb[2].referent))
                else:  # starts during segment so insert it part way through the stream
                    stream.insert(mmb[0]-offset_start + self.tempo_shift, tempo.MetronomeMark(number=tempoNumber*scale, referent=mmb[2].referent))

    def make_midi_path_from_options(self, sel=None, part=None, ins=None, start=None, end=None, click=None, tempo=None):
        self.midiname = self.filename
        if (sel != None):
            self.midiname += "sel-"+str(sel)
        if (part != None):
            self.midiname += "p"+str(part)
        if (ins != None):
            self.midiname += "i"+str(ins)
        if (start != None):
            self.midiname += "s"+str(start)
        if (end != None):
            self.midiname += "e"+str(end)
        if (click != None):
            self.midiname += "c"+str(click)
        if (tempo != None):
            self.midiname += "t"+str(tempo)

        self.midiname += ".mid"
        logger.debug(f"midifilename = {self.midiname}")
        return os.path.join(BASE_DIR, STATIC_ROOT, "data", self.folder, self.midiname)

    def get_or_make_midi_file(self):
        self.midiname = self.filename
        if (self.queryString.get("sel") != None):
            self.midiname += "sel-"+self.queryString.get("sel")  # sel-sel, sel-all, sel-un
        if (self.queryString.get("part") != None):
            self.midiname += "p"+self.queryString.get("part")
        if (self.queryString.get("ins") != None):
            self.midiname += "i"+self.queryString.get("ins")
        if (self.queryString.get("start") != None):
            self.midiname += "s"+self.queryString.get("start")
        if (self.queryString.get("end") != None):
            self.midiname += "e"+self.queryString.get("end")
        if (self.queryString.get("c") != None):
            self.midiname += "c"+self.queryString.get("c")
        if (self.queryString.get("t") != None):
            self.midiname += "t"+self.queryString.get("t")

        self.midiname += ".mid"
        toReturn = self.midiname
        midi_filepath = os.path.join(BASE_DIR, STATIC_ROOT, "data", self.folder, "%s" % (self.midiname))
        if not os.path.exists(midi_filepath):
            logger.debug(f"midi file not found - {self.midiname} - making it...")
            self.make_midi_files()

        return toReturn
