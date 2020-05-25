from collections import OrderedDict
from jinja2.loaders import FileSystemLoader

__author__ = 'BTimms'

import os
import json
import math
import pprint
from music21 import *
us = environment.UserSettings()
us['warnings'] = 0
from abc import ABCMeta, abstractmethod
from jinja2 import Template

class TSEvent(object, metaclass=ABCMeta):
    duration = None
    beat = None
    bar = None
    part = None
    tie = None

    def render(self, context=None):
        rendered_elements = []
        if (context is None or context.duration != self.duration) and self.duration:
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

class TSPitch():
    pitch_name = None
    octave = None

    PITCH_NUMBER_DIFFERENCE_THRESHOLD = 4 # A major third

    def __init__(self, pitch_name, octave, pitch_number):
        self.pitch_name = pitch_name
        self.octave = octave
        self.pitch_number = pitch_number

    def render(self, context=None):
        rendered_elements = []
        if context is None \
                or (context.octave != self.octave
                    and abs(context.pitch_number - self.pitch_number) > self.PITCH_NUMBER_DIFFERENCE_THRESHOLD):
            rendered_elements.append(self.octave)
        rendered_elements.append(self.pitch_name)
        return rendered_elements

class TSNote(TSEvent):
    pitch = None

    def render(self, context=None):
        rendered_elements = []
        # Render the duration
        rendered_elements.append(' '.join(super(TSNote, self).render(context)))
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

    _DURATION_MAP = {
        'half': 'minim',
        'quarter': 'crotchet',
        'eighth': 'quaver',
        '16th': 'semi-quaver',
        '32nd': 'demi-semi-quaver',
        '64th': 'hemi-demi-semi-quaver',
    }

    last_tempo_inserted_index = 0 # insert_tempos() doesn't need to recheck MetronomeMarkBoundaries that have already been used

    def __init__(self, musicxml_filepath):
        self.filepath = os.path.realpath(musicxml_filepath)
        self.score = converter.parse(musicxml_filepath)
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
        instruments = []
        for instrument in self.score.flat.getInstruments():
            if len(instruments) == 0 or instruments[-1] != instrument.partName:
                instruments.append(instrument.partName)
        return instruments

    def get_number_of_parts(self):
        return len(self.get_instruments())

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
                pitch_index = 0
                voice = 1

                if first.measureNumber >= start_bar and first.measureNumber <= end_bar:
                    event = TSDynamic(long_name='%s start' % spanner_type)
                    events_by_bar\
                        .setdefault(first.measureNumber, {})\
                        .setdefault(math.floor(first.beat), {})\
                        .setdefault('Both', {})\
                        .setdefault(voice, {})\
                        .setdefault(pitch_index, [])\
                        .append(event)

                if last.measureNumber >= start_bar and last.measureNumber <= end_bar:
                    event = TSDynamic(long_name='%s end' % spanner_type)
                     # Note - THIS WILL NOT HANDLE CRESCENDOS/DIMINUENDOS THAT SPAN MEASURES
                    events_by_bar\
                        .setdefault(last.measureNumber, {})\
                        .setdefault(math.floor(last.beat) + last.duration.quarterLength - 1, {})\
                        .setdefault('BothAfter', {})\
                        .setdefault(voice, {})\
                        .setdefault(pitch_index, [])\
                        .append(event)

        measures = self.score.measures(start_bar, end_bar)
        for part in measures.parts:
            print("Processing part %s, bars %s to %s" % (part.id, start_bar, end_bar))
            # Iterate over the bars one at a time
            for bar_index in range(start_bar, end_bar + 1):
                measure = part.measure(bar_index)
                self.update_events_for_measure(measure, part.id, events_by_bar)

        return events_by_bar

    def update_events_for_measure(self, measure, part_id, events, voice=1):

        for element in measure.elements:
            element_type = type(element).__name__
            event = None
            hand = ('Left', 'Right')[part_id == 'P1-Staff1']

            if element_type == 'Note':
                event = TSNote()
                event.pitch = TSPitch( self.map_pitch(element.pitch), self.map_octave(element.pitch.octave), element.pitch.ps )
                pitch_index = element.pitch.ps
                if element.tie:
                    event.tie = element.tie.type

            elif element_type == 'Chord':
                event = TSChord()
                event.pitches = [ TSPitch(self.map_pitch(element_pitch), self.map_octave(element_pitch.octave), element_pitch.ps) for element_pitch in element.pitches ]
                pitch_index = element.bass().ps # Take the bottom note of the chord for ordering
                if element.tie:
                    event.tie = element.tie.type

            elif element_type == 'Dynamic':
                event = TSDynamic(long_name = element.longName, short_name=element.value)
                pitch_index = 0 # Always speak the dynamic first
                hand = 'Both'

            elif element_type == 'Voice':
                self.update_events_for_measure(element, part_id, events, element.id)

            if event is None:
                continue

            # This test isn't WORKING
            # if TSEvent.__class__ in event.__class__.__bases__:
            event.duration = self.map_duration(element.duration)

            events\
                .setdefault(measure.measureNumber, {})\
                .setdefault(math.floor(element.beat), {})\
                .setdefault(hand, {})\
                .setdefault(voice, {})\
                .setdefault(pitch_index, [])\
                .append(event)


    def group_chord_pitches_by_octave(self, chord):
        chord_pitches_by_octave = {}
        for pitch in chord.pitches:
            chord_pitches_by_octave.setdefault(self._PITCH_MAP.get(str(pitch.octave),'?'), []).append(pitch.name)

        return chord_pitches_by_octave

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
                    midi_stream.write('midi', midi_filename)
                return midi_filename
        else: # both hands
            midi_filename = os.path.join(output_path, "%s_%s_%s.mid" % ( base_filename, range_start, range_end ))
            if not os.path.exists(midi_filename):
                midi_stream = self.score.measures(range_start, range_end, collect=('Clef', 'TimeSignature', 'Instrument', 'KeySignature', 'TempoIndication'))
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
        return self._OCTAVE_MAP.get(octave, "?")
        # return "%s %s" % (self._PITCH_MAP.get(pitch[-1], ''), pitch[0] )

    def map_pitch(self, pitch):
        pitch_name = pitch.name[0]
        if pitch.accidental and pitch.accidental.displayStatus:
            pitch_name = "%s %s" % (pitch_name, pitch.accidental.fullName)
        return pitch_name

    def map_duration(self, duration):
        return self._DURATION_MAP.get(duration.type, 'Unknown duration %s'%duration.type)



class HTMLTalkingScoreFormatter():

    def __init__(self, talking_score, settings={}):

        self.score = talking_score

        options_path = self.score.filepath + '.opts'
        with open(options_path, "r") as options_fh:
                options = json.load(options_fh)
        self.settings = {
            'pitchBeforeDuration': False,
            'describeBy': 'beat',
            'handsTogether': True,
            'barsAtATime': int(options["bars_at_a_time"])
        }

    def generateHTML(self,output_path="",web_path=""):

        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader(os.path.dirname(__file__)))
        template = env.get_template('talkingscore.html')
        return template.render({'settings' : self.settings,
                                'basic_information': self.get_basic_information(),
                                'preamble': self.get_preamble(),
                                'full_score': "/midis/" + os.path.basename(web_path) + "/" + os.path.basename(self.score.generate_midi_for_part_range(output_path=output_path)),
                                'music_segments': self.get_music_segments(output_path,web_path)
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

        music_segments = []

        number_of_bars = self.score.get_number_of_bars()

        for bar_index in range( 1, number_of_bars, self.settings['barsAtATime'] ):
            end_bar_index = bar_index + self.settings['barsAtATime'] - 1
            if end_bar_index > number_of_bars:
                end_bar_index = number_of_bars

            events_by_bar_and_beat = self.score.get_events_for_bar_range(bar_index, end_bar_index)
            # for offset, events in events_for_bar_range.iteritems():
            # events_ordered_by_beat = OrderedDict(sorted(events_for_bar_range.items(), key=lambda t: t[0]))

            # pp = pprint.PrettyPrinter(indent=4)
            # pp.pprint(events_by_bar_and_beat)


            midi_filenames = {
                #'both': os.path.join(web_path, os.path.basename( self.score.generate_midi_for_part_range(bar_index, end_bar_index,output_path=output_path) ) ),
                # 'right': os.path.join(web_path, os.path.basename( self.score.generate_midi_for_part_range(bar_index, end_bar_index, ['P1-Staff1'],output_path=output_path) ) ),
            }

            both_hands_midi = self.score.generate_midi_for_part_range(bar_index, end_bar_index,
                                                                     output_path=output_path)
            midi_filenames['both'] = "/midis/" + os.path.basename(web_path) + "/" + os.path.basename(both_hands_midi)
                
            left_hand_midi = self.score.generate_midi_for_part_range(bar_index, end_bar_index, ['P1-Staff2'],
                                                                     output_path=output_path)
            right_hand_midi = self.score.generate_midi_for_part_range(bar_index, end_bar_index, ['P1-Staff1'],
                                                                     output_path=output_path)
            if left_hand_midi is not None:
                midi_filenames['left'] = "/midis/" + os.path.basename(web_path) + "/" + os.path.basename(left_hand_midi)
            if right_hand_midi is not None:
                midi_filenames['right'] = "/midis/" + os.path.basename(web_path) + "/" + os.path.basename(right_hand_midi)

            music_segment = {'start_bar':bar_index, 'end_bar': end_bar_index, 'events_by_bar_and_beat': events_by_bar_and_beat, 'midi_filenames': midi_filenames }
            music_segments.append(music_segment)

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


