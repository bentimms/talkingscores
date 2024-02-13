__author__ = 'PMarchant'

import json
import math
import pprint
import logging
import logging.handlers
import logging.config
from music21 import *

logger = logging.getLogger("TSScore")

"""
This code attempts to identify common elements in the music, along with their distribution and look for patterns or repetition.
The basic idea is to make a separate index (or bucket) of each musical attribute we want to consider eg pitch / rhythm / interval / chord name etc.  

To do this - we give some musical attributes a Dictionary - eg for pitch, the key is eg the midi pitch and the value is a List of all the indexes of those events in the Part.  
Other musical attributes use a List to store what they are - because they are not a suitable datatype for a Dictionary key - eg the pitches in a chord; where each element is a List of pitches.  Then, similar to before, we use a dictionary but the key is the index in that List and again the value is a List of all the indexes of those events in the Part.

We then have an AnalyseIndex class which combines the indexes of all the musical attributes for each event.
There is a List of AnalyseIndex instances where each one corresponds to eg a note / chord / rest etc in the Part.  And this stores the index of the type of musical attribute eg the A4 notes when looking at pitch, along with the index of this particular event from the dictionary of all the A4 notes.
From this we can take any event and discern when the previous / next matching event occurs from any of its musical attributes.  

A similar technique is applied to Measures to create indexes (or buckets) of Measures and then groups of Measures.  

"""


class AnalyseIndex:
    def __init__(self, ei):
        self.event_index = ei
        self.event_type = ''  # n c r - note / chord / rest

        # [the particular eg chord_interval_index, the occurance of that particular event in eg AnalysePart.chord_pitches_dictionary]
        self.chord_interval_index = [-1, -1]
        self.chord_pitches_index = [-1, -1]
        self.chord_name_index = ['', -1]

        self.pitch_number_index = [-1, -1]
        self.pitch_name_index = ['', -1]
        self.interval_index = [None, -1]
        # possibly only needs one rhythm index
        self.rhythm_note_index = [-1, -1]
        self.rhythm_chord_index = [-1, -1]
        self.rhythm_rest_index = [-1, -1]

    def print_info(self):
        print("EventIndex..." + str(self.event_index) + " - type " + self.event_type)
        if (self.event_type == 'n'):
            print(self.pitch_name_index + self.pitch_number_index + self.interval_index)
            print("rhythm " + str(self.rhythm_note_index))
        elif (self.event_type == 'c'):
            print(self.chord_pitches_index + self.chord_interval_index + self.chord_name_index)
            print("rhythm " + str(self.rhythm_chord_index))
        elif (self.event_type == 'r'):
            print("rhythm " + str(self.rhythm_rest_index))


class AnalyseSection:
    def __init__(self):
        self.analyse_indexes = []  # all the notes etc in the section
        self.section_start_event_indexes = []  # the event indexes each time this section starts

    def print_info(self):
        print("section length = " + str(len(self.analyse_indexes)))
        # for ai in self.analyse_indexes:
        # ai.print_info


class MusicAnalyser:
    score = None
    analyse_parts = []
    summary = ""
    repetition_parts = []
    repetition_right_hand = ""
    repetition_left_hand = ""

    def setScore(self, ts):
        self.ts = ts
        self.score = ts.score
        part_index = 0
        self.analyse_parts = []
        self.repetition_parts = []
        self.summary_parts = []
        self.repetition_in_contexts = {}  # key = part index
        self.general_summary = ""

        analyse_index = 0
        for ins in ts.part_instruments:
            if ins in ts.selected_instruments:
                start_part = ts.part_instruments[ins][1]
                instrument_len = ts.part_instruments[ins][2]
                for part_index in range(start_part, start_part+instrument_len):
                    self.analyse_parts.append(AnalysePart())
                    self.analyse_parts[analyse_index].set_part(self.score.parts[part_index])
                    summary = self.analyse_parts[analyse_index].describe_summary()
                    summary += self.analyse_parts[analyse_index].describe_repetition_summary()
                    self.repetition_in_contexts[part_index] = (self.analyse_parts[analyse_index].describe_repetition_in_context())
                    self.summary_parts.append(summary)

                    # self.repetition_parts.append(self.analyse_parts[analyse_index].describe_repetition())
                    analyse_index = analyse_index + 1

        self.general_summary += self.describe_general_summary()

    # summarise time / key / tempo changes
    def describe_general_summary(self):
        num_measures = len(self.score.parts[0].getElementsByClass('Measure'))
        generalSummary = ""
        generalSummary += "There are " + str(num_measures) + " bars...  "

        timesigs = self.score.parts[0].flat.getElementsByClass('TimeSignature')
        generalSummary += self.summarise_key_and_time_changes(timesigs, "time signature")
        keysigs = self.score.parts[0].flat.getElementsByClass('KeySignature')
        generalSummary += self.summarise_key_and_time_changes(keysigs, "key signature")
        tempos = self.score.flat.getElementsByClass('MetronomeMark')
        generalSummary += self.summarise_key_and_time_changes(tempos, "tempo")

        return generalSummary

    # if there are only a couple of changes - list them out with their bar number.
    # if there are more - just say the number
    def summarise_key_and_time_changes(self, changes_dictionary: dict, changes_name: str):
        print("summarise key and time changes")

        changes = ""
        numchanges = len(changes_dictionary) - 1  # the first one isn't a change!
        if numchanges > 4:
            changes = "There are " + str(numchanges) + " " + changes_name + " changes..."
        elif numchanges > 0:
            changes = "The " + changes_name + " changes to "
            index = 0
            for ch in changes_dictionary:
                if (index > 0):
                    if (changes_name == "time signature"):
                        changes += self.ts.describe_time_signature(ch)
                    elif (changes_name == "key signature"):
                        changes += self.ts.describe_key_signature(ch)
                    elif (changes_name == "tempo"):
                        changes += self.ts.describe_tempo(ch)

                    changes += " at bar " + str(ch.measureNumber)
                    if index == numchanges-1:
                        changes += " and "
                    elif index < numchanges-1:
                        changes += ", "
                index += 1

        if (changes != ""):
            changes += ".  "
        return changes


class AnalysePart:

    # position based on quarters of the Score
    _position_map = {
        0: 'near the start',
        1: 'in the 2nd quarter',
        2: 'in the 3rd quarter',
        3: 'near the end'
    }

    _interval_map = {
        0: 'unison',
        1: 'minor 2nd',
        2: 'major 2nd',
        3: 'minor 3rd',
        4: 'major 3rd',
        5: 'perfect 4th',
        6: 'augmented 4th / tritone',
        7: 'perfect 5th',
        8: 'minor 6th',
        9: 'major 6th',
        10: 'minor 7th',
        11: 'major 7th',
        12: 'octave',
        13: 'minor 9th',
        14: 'major 9th',
        15: 'minor 10th',
        16: 'major 10th',
        17: 'perfect 11th',
        18: 'augmented 11th',
        19: 'perfect 12th',
        20: 'minor 13th',
        21: 'major 13th',
        22: 'minor 14th',
        23: 'major 14th',
        24: '2 octaves',
    }

    _DURATION_MAP = {
        4.0: 'semibreves',
        3.0: 'dotted minims',
        2.0: 'minims',
        1.5: 'dotted crotchets',
        1.0: 'crotchets',
        0.75: 'dotted quavers',
        0.5: 'quavers',
        0.375: 'dotted semi-quavers',
        0.25: 'semi-quavers',
        0.1875: 'dotted demi-semi-quavers',
        0.125: 'demi-semi-quavers',
        0.09375: 'dotted hemi-demi-semi-quavers',
        0.0625: 'hemi-demi-semi-quavers',
        0.0: 'grace notes',
    }

    def compare_sections(self, s1: AnalyseSection, s2: AnalyseSection, compare_type):
        to_return = True
        if (len(s1.analyse_indexes) != len(s2.analyse_indexes)):
            to_return = False
        else:
            for i in range(len(s1.analyse_indexes)):
                if (compare_type == 0 and self.compare_indexes(s1.analyse_indexes[i], s2.analyse_indexes[i]) == False):
                    to_return = False
                    break
                elif (compare_type == 1 and self.compare_indexes_rhythm(s1.analyse_indexes[i], s2.analyse_indexes[i]) == False):
                    to_return = False
                    break
                elif (compare_type == 2 and self.compare_indexes_intervals(s1.analyse_indexes[i], s2.analyse_indexes[i]) == False):
                    to_return = False
                    break
        return to_return

    # one might have a chord or play a note in octaves - and this will say the intervals don't match - because it is expecting single notes...
    def compare_indexes_intervals(self, ai1: AnalyseIndex, ai2: AnalyseIndex):
        to_return = True
        if not (ai1.event_type == ai2.event_type):
            to_return = False
        elif (ai1.event_type == 'n'):
            if (ai1.interval_index[0] != ai2.interval_index[0]):
                to_return = False

        return to_return

    # rest durations must match.  Chords / single notes are interchangeable - but their durations must match
    def compare_indexes_rhythm(self, ai1: AnalyseIndex, ai2: AnalyseIndex):
        to_return = True
        if (ai1.event_type == 'r' and not ai2.event_type == 'r'):
            to_return = False
        elif ((ai1.event_type == 'n' or ai1.event_type == 'c') and ai2.event_type == 'r'):
            to_return = False
        elif ((ai1.rhythm_chord_index[0] != ai2.rhythm_chord_index[0])):
            to_return = False
        elif ((ai1.rhythm_note_index[0] != ai2.rhythm_note_index[0])):
            to_return = False
        elif ((ai1.rhythm_rest_index[0] != ai2.rhythm_rest_index[0])):
            to_return = False

        return to_return

    # Check for the same event type then compare the important attributes of that particular event type
    def compare_indexes(self, ai1: AnalyseIndex, ai2: AnalyseIndex):
        to_return = True
        if not (ai1.event_type == ai2.event_type):
            to_return = False
        elif (ai1.event_type == 'n'):
            if (ai1.rhythm_note_index[0] != ai2.rhythm_note_index[0]):
                to_return = False
            if (ai1.pitch_number_index[0] != ai2.pitch_number_index[0]):
                to_return = False
        elif (ai1.event_type == 'c'):
            if (ai1.rhythm_chord_index[0] != ai2.rhythm_chord_index[0]):
                to_return = False
            if (ai1.chord_pitches_index[0] != ai2.chord_pitches_index[0]):
                to_return = False
        elif (ai1.event_type == 'r'):
            if (ai1.rhythm_rest_index[0] != ai2.rhythm_rest_index[0]):
                to_return = False
        return to_return

    def __init__(self):
        self.analyse_indexes_list = []  # a list of AnalyseIndex - each unique event}
        self.analyse_indexes_dictionary = {}  # {index of event, [List of event indexes]
        self.analyse_indexes_all = {}  # {event index, [index from analyse_indexes_list, index from analyse_indexes_dictionary]}

        self.measure_indexes = {}  # the event index (from the Part) of the first event of each meausre.  A dictionary instead of a list because there might be a pickup bar

        self.measure_analyse_indexes_list = []  # each element represents a unique measure as an AnalyseSection - which includes a list of AnalyseIndexes
        self.measure_analyse_indexes_dictionary = {}  # {index in measure_analyse_indexes_list, [list of measure indexes]}
        self.measure_analyse_indexes_all = {}  # the index of every measure within measure_analyse_indexes_list {meausre_index, [index from measure_analyse_indexes_list, index from measure_analyse_indexes_dictionary]}
        self.repeated_measures_lists = []  # List of lists of measure indexes where measures match [[1, 3, 6], [2, 4]]
        self.measure_groups_list = []  # groups of repeated measures [ [[1st group 1st occurance start bar, 1st group 1st occurance last bar], [1st group 2nd occurance start bar, 1st group 2nd occurance last bar]], [[2nd group 1st occurance start bar, 2nd group 1st occurance last bar], [2nd group 2nd occurance start bar, 2nd group 2nd occurance last bar]] ] eg [ [[1, 4], [9, 12]], [[7, 8], [15, 16]] ]
        self.repeated_measures_not_in_groups_dictionary = {}  # repeated measures that aren't in a group.  measure index, list of measures it is repeated at

        self.measure_rhythm_analyse_indexes_list = []  # each element is an AnalyseSection for a unique measure (containing a list of AnalyseIndex) - but ignoring pitch and intervals etc
        self.measure_rhythm_analyse_indexes_dictionary = {}  # index of each measure occurrence with particular rhythm
        self.measure_rhythm_analyse_indexes_all = {}  # the index of every measure within measure_rhythm_analyse_indexes_list
        self.repeated_measures_lists_rhythm = []  # where the rhythm matches - but the measure isn't already a full match. [[1, 3, 6], [2, 4]]
        self.measure_rhythm_not_full_match_groups_list = []  # [ [[1, 4], [9, 12]], [[7, 8], [15, 16]] ] ie measures 1 to 4 are used at 9 to 12 and 7 to 8 are used at 15 to 16.
        self.repeated_rhythm_measures_not_full_match_not_in_groups_dictionary = {}  # measure index, list of measures it is repeated at

        self.measure_intervals_analyse_indexes_list = []  # each element is an AnalyseSection for a unique measure (containing a list of AnalyseIndex) - but ignoring rhythm etc
        self.measure_intervals_analyse_indexes_dictionary = {}  # index of each measure occurrence with particular intervals
        self.measure_intervals_analyse_indexes_all = {}  # the index of every measure within measure_intervals_analyse_indexes_list
        self.repeated_measures_lists_intervals = []  # where the intervals match - but the measure isn't already a full match. [[1, 3, 6], [2, 4]]
        self.measure_intervals_not_full_match_groups_list = []  # [ [[1, 4], [9, 12]], [[7, 8], [15, 16]] ]
        self.repeated_intervals_measures_not_full_match_not_in_groups_dictionary = {}  # measure index, list of measures it is repeated at

        self.pitch_number_dictionary = {}  # midi pitch number, list of event indexes
        for i in range(128):
            self.pitch_number_dictionary[i] = []
        self.pitch_name_dictionary = {}  # pitch name (without octave), [event indexes]
        self.interval_dictionary = {}  # interval (in semitones +x / -x / 0), [event indexes]
        self.rhythm_note_dictionary = {}  # duration (in fractions of quarter notes) of single notes, [event indexes]
        self.rhythm_rest_dictionary = {}  # duration (in fractions of quarter notes) of rests, [event indexes]
        self.rhythm_chord_dictionary = {}  # duration (in fractions of quarter notes) of chords, [event indexes]

        self.count_accidentals_in_measures = {}  # {measure number, number of accidentals in it}
        self.count_gracenotes_in_measures = {}  # {measure number, number of accidentals in it}
        self.count_rests_in_measures = {}  # {measure number, number of accidentals in it}

        self.chord_pitches_list = []  # each unique chord based on pitches (midi number)
        self.chord_pitches_dictionary = {}  # index in chord_pitches_list, [event indexes]
        self.chord_intervals_list = []  # each unique chord based on the intervals in it
        self.chord_intervals_dictionary = {}  # index in chord_intervals_list, [event indexes]
        self.chord_common_name_dictionary = {}  # chord name, [event indexes]

        self.count_pitches = []  # [[pitch number, count]] ordered by descending count. produced by count_dictionary()
        self.count_pitch_names = []  # [[pitch name, count]] ordered by descending count. produced by count_dictionary()
        self.count_intervals = []  # [[interval +x / -x / 0, count]] ordered by descending count. produced by count_dictionary()
        self.count_intervals_abs = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]  # count of intervals (unison to 2 octaves) - ignore ascending or descending
        self.count_chord_pitches = []  # [[key from chord_pitches_dictionary, count]] ordered by descending count. produced by count_dictionary()
        self.count_chord_intervals = []  # [[key from chord_intervals_dictionary, count]] ordered by descending count. produced by count_dictionary()
        self.count_chord_common_names = []  # [[chord common name, count]] ordered by descending count. produced by count_dictionary()
        self.count_notes_in_chords = {2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0, 10: 0}  # {number of notes in chord, number of occurances}
        self.count_rhythm_note = []  # [[duration of individual note, count]] ordered by descending count. produced by count_dictionary()
        self.count_rhythm_rest = []  # [[duration of rest, count]] ordered by descending count. produced by count_dictionary()
        self.count_rhythm_chord = []  # [[duration of chord, count]] ordered by descending count. produced by count_dictionary()

        # used for calculating percentages etc
        self.total_note_duration = 0
        self.note_count = 0
        self.interval_count = 0
        self.interval_ascending_count = 0
        self.interval_descending_count = 0
        self.interval_unison_count = 0
        self.total_rest_duration = 0
        self.rest_count = 0
        self.total_chord_duration = 0
        self.chord_count = 0
        self.accidental_count = 0  # displayed accidentals ie not in the key signature
        self.gracenote_count = 0
        self.possible_accidental_count = 0  # each note - on its own or part of a chord

        self.part = None

    # if a section doesn't contain any consecutive notes - then it doesn't contain any intervals...
    # since all the interval indexes default to None so we check this first otherwise compare_sections will think it is a match for intervals!
    def does_section_contain_intervals(self, section: AnalyseSection):
        for ai in section.analyse_indexes:
            if (ai.interval_index[0] != None):
                return True
        return False

    # compare_type - 0 = all, 1=rhythm, 2=intervals
    def find_section(self, section_to_find: AnalyseSection, sections_to_search, compare_type):
        i = 0
        for s in sections_to_search:
            if self.compare_sections(s, section_to_find, compare_type):
                return i
            i += 1
        return -1

    def find_analyse_index(self, ai):
        ai_index = 0
        for a in self.analyse_indexes_list:
            if self.compare_indexes(ai, a):
                return ai_index
            ai_index += 1
        return -1

    # find chord (based on midi pitches) in self.chord_pitches_list
    def find_chord(self, chord):
        chord_index = 0
        find = sorted(p.midi for p in chord.pitches)
        for c in self.chord_pitches_list:
            if c == find:
                return chord_index
            chord_index += 1
        return -1

    # find chord (based on intervals) in self.chord_intervals_list
    def find_chord_intervals(self, chord_intervals):
        chord_index = 0
        for c in self.chord_intervals_list:
            if c == chord_intervals:
                return chord_index
            chord_index += 1
        return -1

    # return a sorted list of ascending intervals from lowest note - don't include 0
    # major triad = [4, 7]
    def make_chord_intervals(self, chord):
        p1 = chord.pitches[0].midi
        pitches = sorted(p.midi for p in chord.pitches[1:])
        intervals = [p-p1 for p in pitches]
        return intervals

    # measure_index = when is this measure next used
    # from_all eg self.measure_analyse_indexes_all = {} # the index of every measure within measure_analyse_indexes_list {meausre_index, [index from measure_analyse_indexes_list, index from measure_analyse_indexes_dictionary]}
    # from_indexes_dictionary eg self.measure_analyse_indexes_dictionary = {} # {index in measure_analyse_indexes_list, [list of measure indexes]}
    # returns the measure number or -1 if not found.
    def when_is_measure_next_used(self, measure_index, from_all, from_indexes_dictionary):
        mia = from_indexes_dictionary[from_all[measure_index][0]]
        if len(mia)-1 > from_all[measure_index][1]:
            return mia[from_all[measure_index][1]+1]
        else:
            return -1

    # from_list = list of lists where measure (eg rhythm) is repeated - eg [[1, 3, 6], [2, 4]] ie measure 1 is used at 3 and 6.  Measure 2 is used at 4.
    # basically depending which list is passed in - see if two measures have the same rhythm / intervals etc
    def are_measures_in(self, group_list, measure_index1, measure_index2):
        for group in group_list:
            if measure_index1 in group and measure_index2 in group:
                return True
        return False

    # do two measures have matching pitch / rhythm / intervals etc
    def is_measure_used_at(self, indexes_all, current_measure_index, check_measure_index):
        # todo - these two checks are in case a measure doesn't have anything in then won't be added as a key to the dictionary...
        if not check_measure_index in indexes_all:
            return False
        elif not current_measure_index in indexes_all:
            return False
        else:
            if (indexes_all[current_measure_index][0] == indexes_all[check_measure_index][0]):
                return True
            else:
                return False

    # mg = start and end measure in group [1,4]
    # mg_lists = list of lists of measure groups eg [ [[1,4],[5,8]], [[9,10],[11,12]] ]
    def find_measure_group(self, mg, mg_lists):
        mg_index = 0
        for measure_groups in mg_lists:
            for group in measure_groups:
                if mg == group:
                    return mg_index
            mg_index += 1
        return -1

    # from_measures_dictionary will be eg measure_analyse_indexes_dictionary eg {0: [1,3], 1:[2,4]}
    # not_full_match - when true, find eg rhythm or interval measures that are not a complete match
    # returns eg [[1, 3], [2, 4]]
    # does not return measures that are only used once
    def calculate_repeated_measures_lists(self, from_measure_dictionary, not_full_match):
        to_list = []
        for measure_indexes in from_measure_dictionary.values():
            if len(measure_indexes) > 1:  # this measure is used more than once
                measures = []
                for measure_index in measure_indexes:
                    if (not_full_match == False or len(self.measure_analyse_indexes_dictionary[self.measure_analyse_indexes_all[measure_index][0]]) == 1):
                        measures.append(measure_index)
                if len(measures) > 1:
                    to_list.append(measures)
        return to_list

    # find repeated measures that aren't already in a group
    def calculate_repeated_measures_not_in_groups(self, measures_list, groups_list):
        output_dictionary = {}
        for measure_indexes in measures_list:
            if len(measure_indexes) > 1:  # the measure is used more than once
                measures = []
                for measure_index in measure_indexes:
                    if not self.in_measure_groups(measure_index, groups_list):
                        measures.append(measure_index)

                if len(measures) > 1:
                    output_dictionary[measures[0]] = measures[1:]
        return output_dictionary

    # is a measure already in a list of measure groups
    def in_measure_groups(self, measure_index, groups_list):
        for mgl in groups_list:
            for mg in mgl:
                if measure_index >= mg[0] and measure_index <= mg[1]:
                    return True
        return False

    # are both measures already in the same group.  Ie 1 to 4 is used at 5 to 8.  So 2 to is used at 6 to 8 - but you don't want to say that.
    def are_measures_in_same_group(self, measure_index1, measure_index2, groups_list):
        for mgl in groups_list:
            for mg in mgl:
                if measure_index1 >= mg[0] and measure_index1 <= mg[1] and measure_index2 >= mg[0] and measure_index2 <= mg[1]:
                    return True
        return False

    # from_indexes_all eg self.measure_analyse_indexes_all - {meausre_index, [index from measure_analyse_indexes_list, index from measure_analyse_indexes_dictionary]}
    # from_indexes_dictionary eg measure_analyse_indexes_dictionary - {index in measure_analyse_indexes_list, [list of measure indexes]}
    # returns eg self.measure_groups_list = [] #groups of repeated measures [ [[1, 4], [9, 12]], [[5, 6], [7,8]] ]
    # TODO - improve so it the first measure in the group can be used more than once
    def calculate_measure_groups(self, from_indexes_all, from_indexes_dictionary):
        to_list = []
        next_used_at = 1
        group_size = 1
        gap = 1
        skip = 0
        for look_at_measure in from_indexes_all:
            # if measures 1 to 4 are repeated then don't mention that 2 to 4 and 3 to 4 are also repeated!
            if (skip > 0):
                skip -= 1
                continue

            # see when the current measure is next used
            next_used_at = self.when_is_measure_next_used(look_at_measure, from_indexes_all, from_indexes_dictionary)
            if next_used_at > -1:
                gap = next_used_at - look_at_measure
                # eg if 4 is used at 6, check if 5 is used at 7
                if gap > 1:
                    group_size = 1
                    while (group_size < gap and (look_at_measure + group_size + gap) in from_indexes_all) and (self.is_measure_used_at(from_indexes_all, look_at_measure + group_size, look_at_measure + group_size + gap)):
                        group_size += 1

                    group_size -= 1

                    # if a group of bars is actually repeated
                    if (group_size > 0):
                        measure_group = [look_at_measure, look_at_measure + group_size]
                        measure_group_index = self.find_measure_group(measure_group, to_list)
                        if (measure_group_index == -1):  # ie need to add 1st and 2nd occurance.  When you come to 2nd and 3rd occurance - the 2nd occurance will already have been added.  Does it this way to avoid not adding the final occurance
                            to_list.append([measure_group])
                            to_list[len(to_list)-1].append([look_at_measure + gap, look_at_measure + gap + group_size])
                        else:
                            to_list[measure_group_index].append([look_at_measure + gap, look_at_measure + gap + group_size])

                        skip = group_size  # not great as it overlooks possible smaller gruops within large groups eg it will find 1 t 8 being used at 9 to 16 but miss 1 to 4 being used at 17 to 20.
        return to_list

    def describe_repetition_percentage(self, percent):
        if percent > 99:
            return "all"
        elif percent > 85:
            return "almost all"
        elif percent > 75:
            return "over three quarters"
        elif percent > 50:
            return "over half"
        elif percent > 33:
            return "over a thrid"
        else:
            return ""

    # return a list with commas plus an and in the right place
    # eg [1,4,6] = "1, 4 and 6"
    def comma_and_list(self, l):
        output = ""
        for index, v in enumerate(l):
            if index == len(l)-1 and index > 0:
                output += " and "
            elif index < len(l)-1 and index > 0:
                output += ", "
            output += str(v)
        return output

    # count_in_measures = a dictionary {measure index, number of eg rests accidentals in that measure}
    # total = the total number of rests / accidentals

    def describe_distribution(self, count_in_measures, total):
        distribution = ""

        # make a dictionary of percentages for each measure then sort by percent descending
        measure_percents = {}
        for k, c in count_in_measures.items():
            if c > 0:
                measure_percents[k] = (c/total)*100
        sorted_percent = dict(sorted(measure_percents.items(), reverse=True, key=lambda item: item[1]))

        # get any measures with more than a high percent (eg 20%) to name individually
        ms = []
        to_pop = []  # can't pop during for loop
        for m, p in sorted_percent.items():
            if p > 20:
                ms.append(m)
                to_pop.append(m)
        percent_remaining = 100
        for tp in to_pop:
            percent_remaining -= measure_percents[tp]
            measure_percents.pop(tp)

        if len(ms) > 0:
            distribution += " mostly in bar"
            if len(ms) > 1:
                distribution += "s"
            distribution += " "
            distribution += self.comma_and_list(ms)

        # now see if the remaining measures are mostly in a particular quarter
        if len(measure_percents) > 0:
            if not distribution == "":
                distribution += " and "
            dist = {0: 0, 1: 0, 2: 0, 3: 0}
            for index, mp in measure_percents.items():
                if (index > len(count_in_measures)*0.75):
                    dist[3] += (mp/percent_remaining)*100
                elif (index > len(count_in_measures)*0.5):
                    dist[2] += (mp/percent_remaining)*100
                elif (index > len(count_in_measures)*0.25):
                    dist[1] += (mp/percent_remaining)*100
                else:
                    dist[0] += (mp/percent_remaining)*100
            sorted_dist = sorted(dist.items(), reverse=True, key=lambda item: item[1])
            positions = " "
            # if over half are in one quarter - mention it
            if sorted_dist[0][1] > 50:
                positions += self._position_map[sorted_dist[0][0]]
            # if over 70% are in two quarters - name them
            elif sorted_dist[0][1] + sorted_dist[1][1] > 70:
                positions += self._position_map[sorted_dist[0][0]] + " and " + self._position_map[sorted_dist[1][0]]
            else:
                # not in any two quarters - so just say how many bars
                positions += "in " + str(len(measure_percents)) + " bars throughout"

            distribution += positions

        return distribution.strip()

    # eg notes or chords as a percentage of events
    def describe_percentage(self, percent):
        if percent > 99:
            return "all"
        elif percent > 90:
            return "almost all"
        elif percent > 75:
            return "most"
        elif percent > 45:
            return "lots of"
        elif percent > 30:
            return "some"
        elif percent > 10:
            return "a few"
        elif percent > 1:
            return "very few"
        else:
            return ""

    # an event that is uncommon - like accidentals - so the descriptions are weighted differently
    def describe_percentage_uncommon(self, percent):
        if percent > 5:
            return "many"
        elif percent > 2:
            return "a lot of"
        elif percent > 1:
            return "quite a few"
        elif percent > 0.5:
            return "a few"
        else:
            return "some"

    def describe_count_list(self, count_list, total):
        description = ""
        if total > 0:
            for index, count_item in enumerate(count_list):
                if count_item[1]/total > 0.98:
                    description += "all " + str(count_item[0]) + ", "
                elif count_item[1]/total > 0.90:
                    description += "almost all " + str(count_item[0]) + ", "
                elif count_item[1]/total > 0.6:
                    description += "mostly " + str(count_item[0]) + ", "
                elif count_item[1]/total > 0.3:
                    description += "some " + str(count_item[0]) + ", "

        description = self.replace_end_with(description, ", ", "")

        return description

    # if no single item is over 30% for describe_count_list - then we might want to
    def describe_count_list_several(self, count_list, total, item_name):
        description = ""
        if total > 0:
            upto_percent = []
            remaining_count = 0
            progress_percent = 0
            for index, count_item in enumerate(count_list):
                if progress_percent < 40:
                    upto_percent.append(count_item[0])
                    progress_percent += (count_item[1]/total)*100
                else:
                    if count_item[1] > 0:
                        remaining_count += 1

            if len(upto_percent) <= 4:
                description = "mostly " + self.comma_and_list(upto_percent)
                if remaining_count > 1:
                    description += "; plus " + str(remaining_count) + " other " + item_name
            else:
                description = str(len(upto_percent)) + " " + item_name
                description += ", the most common is " + enumerate(count_list)[0][0]
        return description

    def describe_summary(self):
        summary = ""
        event_count = self.chord_count + self.note_count + self.rest_count
        event_duration = self.total_chord_duration + self.total_note_duration + self.total_rest_duration

        # lower weighting to number of items than to duration - ie 1 bar of semiquavers vs 8 bars of minims!
        percent_dictionary = {}
        percent_dictionary["chords"] = ((self.chord_count/event_count*50) + (self.total_chord_duration/event_duration*150)) / 2
        percent_dictionary["individual notes"] = ((self.note_count/event_count*50) + (self.total_note_duration/event_duration*150)) / 2
        percent_dictionary["rests"] = ((self.rest_count/event_count*50) + (self.total_rest_duration/event_duration*150)) / 2

        for k, v in sorted(percent_dictionary.items(), key=lambda item: item[1], reverse=True):
            if v > 1:
                summary += self.describe_percentage(v) + " " + k
                if k == "chords":
                    describe_count = self.describe_count_list(self.count_chord_common_names, self.chord_count)
                    if describe_count != "":
                        describe_count += ", "
                    chord_count = self.describe_count_list(self.count_rhythm_chord, self.chord_count)
                    if chord_count != "":
                        describe_count += chord_count + ", "
                    count_notes_in_chords_list = sorted(self.count_notes_in_chords.items(), reverse=True, key=lambda item: item[1])
                    note_count = self.describe_count_list(count_notes_in_chords_list, self.chord_count)
                    if note_count != "":
                        describe_count += note_count + " notes, "
                    if describe_count != "":
                        describe_count = self.replace_end_with(describe_count, ", ", "")
                        summary += " (" + describe_count + ")"
                elif k == "individual notes":
                    describe_count = ""
                    temp = self.describe_count_list(self.count_rhythm_note, self.note_count)
                    if temp != "":
                        describe_count += temp + ", "

                    temp = self.describe_count_list(self.count_pitch_names, self.note_count)
                    if temp != "":
                        describe_count += temp + ", "

                    sorted_abs_intervals = dict(sorted(enumerate(self.count_intervals_abs), reverse=True, key=lambda item: item[1]))
                    named_abs_intervals = {}
                    for index, count in sorted_abs_intervals.items():
                        named_abs_intervals[self._interval_map[index]] = count
                    temp = self.describe_count_list(named_abs_intervals.items(), self.interval_count)
                    temp = self.replace_end_with(temp, ", ", "")
                    if temp == "":
                        temp = self.describe_count_list_several(named_abs_intervals.items(), self.interval_count, "intervals")

                    # mostly ascending or descending
                    if self.interval_ascending_count > self.interval_descending_count*2:
                        temp += ", mostly ascending"
                    elif self.interval_descending_count > self.interval_ascending_count*2:
                        temp += ", mostly descending"

                    if temp != "":
                        describe_count += temp

                    summary += " (" + describe_count + ")"
                elif k == "rests":
                    describe_count = self.describe_count_list(self.count_rhythm_rest, self.rest_count)
                    dist = (self.describe_distribution(self.count_rests_in_measures, self.rest_count))
                    if describe_count != "":
                        summary += " (" + describe_count + " - " + dist + ")"
                summary += ", "

        dist = ""
        # describe the number of accidentals and where they mostly occur
        if self.accidental_count > 1:
            accidental_percent = (self.accidental_count/self.possible_accidental_count)*100
            summary += self.describe_percentage_uncommon(accidental_percent) + " accidentals"
            dist = (self.describe_distribution(self.count_accidentals_in_measures, self.accidental_count))
            if not dist == "":
                summary += " (" + dist + "), "

        # describe the number of grace notes and where they mostly occur
        if self.gracenote_count > 1:
            gracenote_percent = (self.gracenote_count/self.possible_accidental_count)*100
            summary += self.describe_percentage_uncommon(gracenote_percent) + " grace notes"
            dist = (self.describe_distribution(self.count_gracenotes_in_measures, self.gracenote_count))
            if not dist == "":
                summary += " (" + dist + ")."

        summary = self.replace_end_with(summary, ", ", ".  ").capitalize()
        return summary

    def replace_end_with(self, original: str, remove: str, add: str):
        to_return = original
        if original.endswith(remove):
            to_return = original[0:original.rfind(remove)]
            to_return += add
        return to_return

    def describe_measure_repeated_many(self, measures_dictionary: dict, description: str):
        repetition = ""
        for key, ms in measures_dictionary.items():
            percent_usage = len(ms) / len(self.measure_indexes)*100
            if percent_usage > 33:
                repetition += "The " + description + " in bar " + str(key) + " is used "
                repetition += self.describe_percentage(percent_usage)
                repetition += " of the way through.  "
        return repetition

    def describe_measure_group_repeated_many(self, measure_group_list: list, description: str):
        repetition = ""
        for group in measure_group_list:
            group_repetition_percent = ((group[0][1]-group[0][0]+1)*len(group)/len(self.measure_indexes))*100
            if group_repetition_percent > 33:
                if (group[0][1]-group[0][0] == 1):  # x and y or x to y.
                    repetition += "The " + description + " in bars " + str(group[0][0]) + " and " + str(group[0][1])
                else:
                    repetition += "The " + description + " in bars " + str(group[0][0]) + " to " + str(group[0][1])
                repetition += " are used "
                repetition += self.describe_repetition_percentage(group_repetition_percent)
                repetition += " of the way through.  "
        return repetition

    # eg bars 1-4 are repeated all the way through...
    # eg a few individual bars repeated several times...
    # eg 1 and 2 bar sections repeated a lot...
    # how many individual bars out of the total - are unique?
    # how many have the same rhythm / intervals ?
    # don't list out every time that every bar is used.

    def describe_repetition_summary(self):
        repetition = ""

        # see if a group of bars repetition is over a third of the score
        repetition += self.describe_measure_group_repeated_many(self.measure_groups_list, "pitch and rhythm")
        # see if an individual bar is used in over a thrid of the score
        repetition += self.describe_measure_repeated_many(self.repeated_measures_not_in_groups_dictionary, "pitch and rhythm")

        # see if a group of bars (just rhythm - not full match) is over a third of the score
        repetition += self.describe_measure_group_repeated_many(self.measure_rhythm_not_full_match_groups_list, "rhythm")
        # see if an individual bar (just rhythm - not full match) is used in over a thrid of the score
        repetition += self.describe_measure_repeated_many(self.repeated_rhythm_measures_not_full_match_not_in_groups_dictionary, "rhythm")

        # see if a group of bars (just intervals - not full match) is over a third of the score
        repetition += self.describe_measure_group_repeated_many(self.measure_intervals_not_full_match_groups_list, "intervals")
        # see if an individual bar (just intervals - not full match) is used in over a thrid of the score
        repetition += self.describe_measure_repeated_many(self.repeated_intervals_measures_not_full_match_not_in_groups_dictionary, "intervals")

        # at this point if you have some bars that are the same pitch and rhythm - and some bars that are the same rhythm and also the same rhythm as the previous full matches - but neither is more than 33% - then nothing gets mentioned...
        if repetition == "":
            check_rhythm_match = self.calculate_repeated_measures_lists(self.measure_rhythm_analyse_indexes_dictionary, False)
            check_rhythm_match.sort(reverse=True, key=lambda item: len(item))
            for check in check_rhythm_match:
                percent_usage = (len(check) / len(self.measure_indexes))*100
                if percent_usage > 33:
                    repetition += "The rhythm in bar " + str(check[0]) + " is used "
                    repetition += self.describe_percentage(percent_usage)
                    repetition += " of the way through.  "
                else:
                    break

            # check intervals too
            check_intervals_match = self.calculate_repeated_measures_lists(self.measure_intervals_analyse_indexes_dictionary, False)
            check_intervals_match.sort(reverse=True, key=lambda item: len(item))
            for check in check_intervals_match:
                percent_usage = (len(check) / len(self.measure_indexes))*100
                if percent_usage > 33:
                    repetition += "The intervals in bar " + str(check[0]) + " is used "
                    repetition += self.describe_percentage(percent_usage)
                    repetition += " of the way through.  "
                else:
                    break

        # look at number of each repetition length
        # todo - maybe repetition_lengths should be {[section length, number of usages]}
        repetition_lengths = {}  # full match.  key = length. {number of individual sections of that length.  Not the number of times they are repeated}
        rhythm_interval_repetition_lengths = {}  # full match - just rhythm or interval.  key = length. {number of individual sections of that length.  Not the number of times they are repeated}
        total_lengths = 0
        for group in self.measure_groups_list:
            length = group[0][1]-group[0][0]+1
            if length in repetition_lengths:
                repetition_lengths[length] = repetition_lengths[length] + 1
            else:
                repetition_lengths[length] = 1

        for group in self.measure_rhythm_not_full_match_groups_list:
            length = group[0][1]-group[0][0]+1
            if length in repetition_lengths:
                rhythm_interval_repetition_lengths[length] = repetition_lengths[length] + 1
            else:
                rhythm_interval_repetition_lengths[length] = 1

        for group in self.measure_intervals_not_full_match_groups_list:
            length = group[0][1]-group[0][0]+1
            if length in repetition_lengths:
                rhythm_interval_repetition_lengths[length] = repetition_lengths[length] + 1
            else:
                rhythm_interval_repetition_lengths[length] = 1

        repetition_lengths[1] = len(self.repeated_measures_not_in_groups_dictionary)
        rhythm_interval_repetition_lengths[1] = len(self.repeated_rhythm_measures_not_full_match_not_in_groups_dictionary)
        rhythm_interval_repetition_lengths[1] += len(self.repeated_intervals_measures_not_full_match_not_in_groups_dictionary)
        print("repetition lengths = " + str(repetition_lengths))
        print("rhythm and interval repetition lengths = " + str(rhythm_interval_repetition_lengths))

        for k, v in repetition_lengths.items():
            total_lengths += v
        sorted_repetition_lengths = sorted(repetition_lengths.items(), reverse=False, key=lambda item: item)
        temp = self.describe_count_list(sorted_repetition_lengths, total_lengths)
        temp = self.replace_end_with(temp, ", ", "")
        if temp == "":
            temp = self.describe_count_list_several(sorted_repetition_lengths, total_lengths, "lengths")
        if temp != "":
            repetition += "The repeated sections are " + temp + " measures long.  "

        # rhythm or interval
        total_lengths = 0
        for k, v in rhythm_interval_repetition_lengths.items():
            total_lengths += v
        sorted_repetition_lengths = sorted(rhythm_interval_repetition_lengths.items(), reverse=False, key=lambda item: item)
        temp = self.describe_count_list(sorted_repetition_lengths, total_lengths)
        temp = self.replace_end_with(temp, ", ", "")
        if temp == "":
            temp = self.describe_count_list_several(sorted_repetition_lengths, total_lengths, "lengths")
        if temp != "":
            repetition += "The repeated sections of just rhythm / intervals are " + temp + " measures long.  "

        if (len(self.part.getElementsByClass('Measure')) > 1):
            repetition += "There are " + str(len(self.measure_analyse_indexes_list)) + " unique measures - "
            repetition += " of these, " + str(len(self.measure_rhythm_analyse_indexes_list)) + " measures have unique rhythm "
            repetition += " and " + str(len(self.measure_intervals_analyse_indexes_list)) + " measures have unique intervals...  "

        if repetition != "":
            repetition = "<br/>"+repetition.capitalize()
        return repetition

    # you get a KeyError if you do dict[key] += value if the key doesn't already exist...
    def insert_or_plus_equals(self, dict, key, value):
        if key in dict:
            dict[key] += value
        else:
            dict[key] = value

    # updates dictionary at the index of the first bar each time where a section is used
    # section first usage - says how many times it is used later.
    # section second usage - says when it was first used.
    # after second usage - says first and most recent time it was used
    # repeat_what eg "full match", "rhythm", "intervals"
    # modifies the repetition_in_context dictionary
    def describe_section_usage_in_context(self, groups_list, repeat_what, repetition_in_context):
        for group in groups_list:
            # see if a group repetition is used a lot so change what we say about it to avoid becoming too verbose
            group_repetition_percent = ((group[0][1]-group[0][0]+1)*len(group)/len(self.measure_indexes))*100
            used_lots = False  # todo maybe say something about this
            if group_repetition_percent > 50:
                used_lots = True

            and_or_through = " through "
            if (group[0][1]-group[0][0] == 1):  # x and y or x to y.
                and_or_through = " and "

            temp = ""
            for index, usage in enumerate(group):
                if index >= 1:
                    temp = repeat_what + str(usage[0]) + and_or_through + str(usage[1])
                    temp += " were first used at " + str(group[0][0])
                    if index >= 2:
                        temp += " and lately used at " + str(group[index-1][0])
                else:
                    temp = "Bars " + str(usage[0]) + and_or_through + str(usage[1])
                    temp += " are used " + (str(len(group)-1)) + " more times.  "

                self.insert_or_plus_equals(repetition_in_context, usage[0], temp + ".  ")

    # updates dictionary at the index the bar each tine where a bar is used
    # bar first usage - says how many times it is used later.
    # bar second usage - says when it was first used.
    # after second usage - says first and most recent time it was used
    # repeat_what eg "full match", "rhythm", "intervals"
    # modifies the repetition_in_context dictionary
    def describe_measure_usage_in_context(self, repeated_measures_not_in_groups_dictionary, repeat_what, repetition_in_context):
        for key, ms in repeated_measures_not_in_groups_dictionary.items():
            temp = repeat_what + str(key) + " is used " + str(len(ms)) + " more times.  "
            self.insert_or_plus_equals(repetition_in_context, key, temp)

            for index, m in enumerate(ms):
                temp = repeat_what + str(m)
                temp += " was first used at " + str(key)
                if index >= 1:
                    temp += " and lately used at " + str(ms[index-1])

                self.insert_or_plus_equals(repetition_in_context, m, temp + ".  ")

    # when was a measure or section first used, when was it last used up until this point
    # measures 20, to, 23 are first used at 6 and last used at bar 12
    # measures 7 AND 8 are used first used at 1 and last used at bar 6

    def describe_repetition_in_context(self):
        print("describe repetition in context...")

        repetition_in_context = {}  # key = measure number.  value = string
        # todo - could eg bar 4 could be full match for another bar - but only rhythm match for another bar.  The later rhythm match will say when it was first used - but the earlier full match won't treat it like the first rhythm match and say how many times it was used.
        self.describe_section_usage_in_context(self.measure_groups_list, "Bars ", repetition_in_context)
        self.describe_measure_usage_in_context(self.repeated_measures_not_in_groups_dictionary, "Bar ", repetition_in_context)

        self.describe_section_usage_in_context(self.measure_rhythm_not_full_match_groups_list, "The rhythm in bars ", repetition_in_context)
        self.describe_measure_usage_in_context(self.repeated_rhythm_measures_not_full_match_not_in_groups_dictionary, "The rhythm in bar ", repetition_in_context)

        self.describe_section_usage_in_context(self.measure_intervals_not_full_match_groups_list, "The intervals in bars ", repetition_in_context)
        self.describe_measure_usage_in_context(self.repeated_intervals_measures_not_full_match_not_in_groups_dictionary, "The intervals in bar ", repetition_in_context)

        return repetition_in_context

    # describes groups of measures and individual measures where the notes pitches and / or rhythm are the same
    # but puts them all in one long string - which isn't very useful

    def describe_repetition(self):
        repetition = ""
        if len(self.measure_groups_list) > 0:
            for group in self.measure_groups_list:
                # see if a group repetition is over half the score
                group_repetition_percent = ((group[0][1]-group[0][0]+1)*len(group)/len(self.measure_indexes))*100
                if group_repetition_percent > 50:
                    if (group[0][1]-group[0][0] == 1):  # x and y or x to y.
                        repetition += "Bars " + str(group[0][0]) + " and " + str(group[0][1])
                    else:
                        repetition += "Bars " + str(group[0][0]) + " to " + str(group[0][1])
                    repetition += " are used "
                    repetition += self.describe_repetition_percentage(group_repetition_percent)
                    repetition += " of the way through.  "
                else:
                    # just describe where the group is repeated
                    if (group[0][1]-group[0][0] == 1):  # x and y or x to y.
                        repetition += "Bars " + str(group[0][0]) + " and " + str(group[0][1])
                    else:
                        repetition += "Bars " + str(group[0][0]) + " to " + str(group[0][1])
                    repetition += " are used at "
                    for index, ms in enumerate(group[1:]):
                        if index == len(group)-2 and index > 0:
                            repetition += " and "
                        elif index < len(group)-1 and index > 0:
                            repetition += ", "
                        repetition += str(ms[0])
                    repetition += ".  "

        # individual bars repeated
        for key, ms in self.repeated_measures_not_in_groups_dictionary.items():
            repetition += "Bar " + str(key) + " is used at "
            for index, m in enumerate(ms):
                if index == len(ms)-1 and index > 0:
                    repetition += " and "
                elif index < len(ms)-1 and index > 0:
                    repetition += ", "
                repetition += str(m)
            repetition += ".  "

        if repetition == "":
            repetition += "There are no repeated bars...  "

        # just rhythm
        rhythm_repetition = ""
        if len(self.measure_rhythm_not_full_match_groups_list) > 0:
            for group in self.measure_rhythm_not_full_match_groups_list:
                if (group[0][1]-group[0][0] == 1):  # x and y or x to y.
                    rhythm_repetition += "The rhythm in bars " + str(group[0][0]) + " and " + str(group[0][1])
                else:
                    rhythm_repetition += "The rhythm in bars " + str(group[0][0]) + " to " + str(group[0][1])
                rhythm_repetition += " are used at "
                for index, ms in enumerate(group[1:]):
                    if index == len(group)-1 and index > 0:
                        rhythm_repetition += " and "
                    elif index < len(group)-1 and index > 0:
                        rhythm_repetition += ", "

                    rhythm_repetition += str(ms[0])
                rhythm_repetition += ".  "

        # individual measures with repeated rhythm
        for key, ms in self.repeated_rhythm_measures_not_full_match_not_in_groups_dictionary.items():
            rhythm_repetition += "The rhythm in bar " + str(key) + " is used at "
            for index, m in enumerate(ms):
                if index == len(ms)-1 and index > 0:
                    rhythm_repetition += " and "
                elif index < len(ms)-1 and index > 0:
                    rhythm_repetition += ", "
                rhythm_repetition += str(m)
            rhythm_repetition += ".  "

        if rhythm_repetition == "":
            rhythm_repetition = "There are no bars with just the same rhythm...  "

        repetition += rhythm_repetition

        # intervals
        interval_repetition = ""
        if len(self.measure_intervals_not_full_match_groups_list) > 0:
            for group in self.measure_intervals_not_full_match_groups_list:
                if (group[0][1]-group[0][0] == 1):  # x and y or x to y.
                    interval_repetition += "The intervals in bars " + str(group[0][0]) + " and " + str(group[0][1])
                else:
                    interval_repetition += "The intervals in bars " + str(group[0][0]) + " to " + str(group[0][1])
                interval_repetition += " are used at "
                for index, ms in enumerate(group[1:]):
                    if index == len(group)-1 and index > 0:
                        interval_repetition += " and "
                    elif index < len(group)-1 and index > 0:
                        interval_repetition += ", "

                    interval_repetition += str(ms[0])
                interval_repetition += ".  "

        # individual measures with repeated intervals
        for key, ms in self.repeated_intervals_measures_not_full_match_not_in_groups_dictionary.items():
            interval_repetition += "The intervals in bar " + str(key) + " are used at "
            for index, m in enumerate(ms):
                if index == len(ms)-1 and index > 0:
                    interval_repetition += " and "
                elif index < len(ms)-1 and index > 0:
                    interval_repetition += ", "
                interval_repetition += str(m)
            interval_repetition += ".  "

        if interval_repetition == "":
            interval_repetition = "There are no bars with just the same intervals...  "

        repetition += interval_repetition

        return repetition

    # analyse each part

    def set_part(self, p):
        self.part = p

        event_index = 0
        previous_note_pitch = -1  # needed to work out intervals
        current_measure = -1
        measure_analyse_indexes = AnalyseSection()
        measure_accidentals = 0  # count
        measure_gracenotes = 0  # count
        measure_rests = 0  # count
        for n in self.part.flat.notesAndRests:
            # the start of a new measure
            if (n.measureNumber > current_measure):
                # todo - if a measure doesn't have any notes or rests then it won't be added to measure_indexes etc and will cause errors later when looking for groups etc
                self.measure_indexes[n.measureNumber] = event_index
                current_measure = n.measureNumber
                if (len(measure_analyse_indexes.analyse_indexes) > 0):  # first time through will be empty
                    self.count_accidentals_in_measures[current_measure-1] = measure_accidentals
                    measure_accidentals = 0
                    self.count_gracenotes_in_measures[current_measure-1] = measure_gracenotes
                    measure_gracenotes = 0
                    self.count_rests_in_measures[current_measure-1] = measure_rests
                    measure_rests = 0

                    index = self.find_section(measure_analyse_indexes, self.measure_analyse_indexes_list, 0)
                    if index == -1:
                        self.measure_analyse_indexes_list.append(measure_analyse_indexes)
                        index = len(self.measure_analyse_indexes_list)-1
                        self.measure_analyse_indexes_dictionary[index] = [current_measure-1]
                        self.measure_analyse_indexes_all[current_measure-1] = [index, 0]
                    else:
                        self.measure_analyse_indexes_dictionary[index].append(current_measure-1)
                        self.measure_analyse_indexes_all[current_measure-1] = [index, len(self.measure_analyse_indexes_dictionary[index])-1]

                    # measures with matching rhythm
                    index = self.find_section(measure_analyse_indexes, self.measure_rhythm_analyse_indexes_list, 1)
                    if index == -1:
                        self.measure_rhythm_analyse_indexes_list.append(measure_analyse_indexes)
                        index = len(self.measure_rhythm_analyse_indexes_list)-1
                        self.measure_rhythm_analyse_indexes_dictionary[index] = [current_measure-1]
                        self.measure_rhythm_analyse_indexes_all[current_measure-1] = [index, 0]
                    else:
                        self.measure_rhythm_analyse_indexes_dictionary[index].append(current_measure-1)
                        self.measure_rhythm_analyse_indexes_all[current_measure-1] = [index, len(self.measure_rhythm_analyse_indexes_dictionary[index])-1]

                    # measures with matching intervals
                    if (self.does_section_contain_intervals(measure_analyse_indexes)):
                        index = self.find_section(measure_analyse_indexes, self.measure_intervals_analyse_indexes_list, 2)
                        if index == -1:
                            self.measure_intervals_analyse_indexes_list.append(measure_analyse_indexes)
                            index = len(self.measure_intervals_analyse_indexes_list)-1
                            self.measure_intervals_analyse_indexes_dictionary[index] = [current_measure-1]
                            self.measure_intervals_analyse_indexes_all[current_measure-1] = [index, 0]
                        else:
                            self.measure_intervals_analyse_indexes_dictionary[index].append(current_measure-1)
                            self.measure_intervals_analyse_indexes_all[current_measure-1] = [index, len(self.measure_intervals_analyse_indexes_dictionary[index])-1]

                    measure_analyse_indexes = AnalyseSection()
                    previous_note_pitch = -1  # reset interval comparison for each measure

            ai = AnalyseIndex(event_index)
            if n.isRest:
                ai.event_type = 'r'
                measure_rests += 1
                d = n.duration.quarterLength
                if self.rhythm_rest_dictionary.get(d) == None:
                    self.rhythm_rest_dictionary[d] = [event_index]
                else:
                    self.rhythm_rest_dictionary[d].append(event_index)
                ai.rhythm_rest_index = [d, len(self.rhythm_rest_dictionary.get(d))-1]

                previous_note_pitch = -1
                self.total_rest_duration += d
                self.rest_count += 1
            elif n.isChord and type(n).__name__ != 'ChordSymbol':
                # todo - maybe analyse ChordSymbol too - it won't cause an error - just thinks they are grace notes and affects counting notes / pitches / repetition etc
                ai.event_type = 'c'

                d = n.duration.quarterLength
                if d == 0.0:
                    measure_gracenotes += len(n.pitches)
                    self.gracenote_count += len(n.pitches)

                if d > 0.0:  # bigger than a grace note because they are counted separately
                    if self.rhythm_chord_dictionary.get(d) == None:
                        self.rhythm_chord_dictionary[d] = [event_index]
                    else:
                        self.rhythm_chord_dictionary[d].append(event_index)
                    ai.rhythm_chord_index = [d, len(self.rhythm_chord_dictionary.get(d))-1]

                if len(n.pitches) < 11:  # unlikely as not enough fingers - but best to check!
                    self.count_notes_in_chords[len(n.pitches)] += 1

                index = self.find_chord(n)
                if index == -1:
                    self.chord_pitches_list.append(sorted(p.midi for p in n.pitches))
                    index = len(self.chord_pitches_list)-1
                    self.chord_pitches_dictionary[index] = [event_index]
                else:
                    self.chord_pitches_dictionary[index].append(event_index)
                ai.chord_pitches_index = [index, len(self.chord_pitches_dictionary.get(index))-1]

                chord_intervals = self.make_chord_intervals(n)
                index = self.find_chord_intervals(chord_intervals)
                if index == -1:
                    self.chord_intervals_list.append(chord_intervals)
                    index = len(self.chord_intervals_list)-1
                    self.chord_intervals_dictionary[index] = [event_index]
                else:
                    self.chord_intervals_dictionary[index].append(event_index)
                ai.chord_interval_index = [index, len(self.chord_intervals_dictionary.get(index))-1]

                common_name = n.commonName
                # music21 describes eg A, D, E as a quatral trichord - ie E, A, D are perfect fourths - but I prefer Suspended 4ths or 2nds...
                if chord_intervals == [0, 5, 7]:
                    common_name = "Suspended 4th"
                elif chord_intervals == [0, 2, 7]:
                    common_name = "Suspended 2nd"
                if self.chord_common_name_dictionary.get(common_name) == None:
                    self.chord_common_name_dictionary[common_name] = [event_index]
                else:
                    self.chord_common_name_dictionary[common_name].append(event_index)
                ai.chord_name_index = [common_name, len(self.chord_common_name_dictionary.get(common_name))-1]

                # count accidentals in the chord
                for p in n.pitches:
                    if p.accidental is not None and p.accidental.displayStatus == True:
                        measure_accidentals += 1
                        self.accidental_count += 1
                self.possible_accidental_count += len(n.pitches)

                self.total_chord_duration += d
                self.chord_count += 1
            elif n.isChord == False:
                if isinstance(n, note.Unpitched):
                    ai.event_type = 'u'
                else:

                    ai.event_type = 'n'

                    if n.pitch.accidental is not None and n.pitch.accidental.displayStatus == True:
                        measure_accidentals += 1
                        self.accidental_count += 1
                    self.possible_accidental_count += 1

                    self.pitch_number_dictionary[n.pitch.midi].append(event_index)
                    ai.pitch_number_index = [n.pitch.midi, len(self.pitch_number_dictionary[n.pitch.midi])-1]

                    if self.pitch_name_dictionary.get(n.pitch.name) == None:
                        self.pitch_name_dictionary[n.pitch.name] = [event_index]
                    else:
                        self.pitch_name_dictionary[n.pitch.name].append(event_index)
                    ai.pitch_name_index = [n.pitch.name, len(self.pitch_name_dictionary[n.pitch.name])-1]

                    # intervals
                    if (previous_note_pitch > -1):
                        interval = n.pitch.midi-previous_note_pitch
                        if self.interval_dictionary.get(interval) == None:
                            self.interval_dictionary[interval] = [event_index]
                        else:
                            self.interval_dictionary[interval].append(event_index)
                        ai.interval_index = [interval, len(self.interval_dictionary.get(interval))-1]

                        if interval > 0:
                            self.interval_ascending_count += 1
                        elif interval < 0:
                            self.interval_descending_count += 1
                        else:
                            self.interval_unison_count += 1
                        self.interval_count += 1

                        interval_abs = abs(interval)
                        if interval_abs < 24:
                            self.count_intervals_abs[interval_abs] += 1

                # duration
                d = n.duration.quarterLength  # numeric value
                if d == 0.0:
                    measure_gracenotes += 1
                    self.gracenote_count += 1
                    print("I'm a grace note note...")
                    print(n)
                if d > 0.0:  # bigger than a grace note because they are counted separately
                    if self.rhythm_note_dictionary.get(d) == None:
                        self.rhythm_note_dictionary[d] = [event_index]
                    else:
                        self.rhythm_note_dictionary[d].append(event_index)
                    ai.rhythm_note_index = [d, len(self.rhythm_note_dictionary.get(d))-1]

                if isinstance(n, note.Unpitched):
                    previous_note_pitch = -1
                else:
                    previous_note_pitch = n.pitch.midi
                self.total_note_duration += d
                self.note_count += 1

            # AnalyseIndex - ie is it a unique event
            index = self.find_analyse_index(ai)
            if index == -1:
                self.analyse_indexes_list.append(ai)
                index = len(self.analyse_indexes_list)-1
                self.analyse_indexes_dictionary[index] = [event_index]
                self.analyse_indexes_all[event_index] = [index, 0]
            else:
                self.analyse_indexes_dictionary[index].append(event_index)
                self.analyse_indexes_all[event_index] = [index, len(self.analyse_indexes_dictionary[index])-1]

            # self.analyse_indexes.append(ai)
            measure_analyse_indexes.analyse_indexes.append(ai)
            event_index = event_index + 1

        # add last measure
        if (len(measure_analyse_indexes.analyse_indexes) > 0):
            self.count_accidentals_in_measures[current_measure-1] = measure_accidentals
            self.count_gracenotes_in_measures[current_measure-1] = measure_gracenotes
            self.count_rests_in_measures[current_measure-1] = measure_rests

            index = self.find_section(measure_analyse_indexes, self.measure_analyse_indexes_list, 0)
            if index == -1:
                self.measure_analyse_indexes_list.append(measure_analyse_indexes)
                index = len(self.measure_analyse_indexes_list)-1
                self.measure_analyse_indexes_dictionary[index] = [current_measure]
                self.measure_analyse_indexes_all[current_measure] = [index, 0]
            else:
                self.measure_analyse_indexes_dictionary[index].append(current_measure)
                self.measure_analyse_indexes_all[current_measure] = [index, len(self.measure_analyse_indexes_dictionary[index])-1]

            # measures with matching rhythm
            index = self.find_section(measure_analyse_indexes, self.measure_rhythm_analyse_indexes_list, 1)
            if index == -1:
                self.measure_rhythm_analyse_indexes_list.append(measure_analyse_indexes)
                index = len(self.measure_rhythm_analyse_indexes_list)-1
                self.measure_rhythm_analyse_indexes_dictionary[index] = [current_measure]
                self.measure_rhythm_analyse_indexes_all[current_measure] = [index, 0]
            else:
                self.measure_rhythm_analyse_indexes_dictionary[index].append(current_measure)
                self.measure_rhythm_analyse_indexes_all[current_measure] = [index, len(self.measure_rhythm_analyse_indexes_dictionary[index])-1]

            # measures with matching intervals
            if (self.does_section_contain_intervals(measure_analyse_indexes)):
                index = self.find_section(measure_analyse_indexes, self.measure_intervals_analyse_indexes_list, 2)
                if index == -1:
                    self.measure_intervals_analyse_indexes_list.append(measure_analyse_indexes)
                    index = len(self.measure_intervals_analyse_indexes_list)-1
                    self.measure_intervals_analyse_indexes_dictionary[index] = [current_measure]
                    self.measure_intervals_analyse_indexes_all[current_measure] = [index, 0]
                else:
                    self.measure_intervals_analyse_indexes_dictionary[index].append(current_measure)
                    self.measure_intervals_analyse_indexes_all[current_measure] = [index, len(self.measure_intervals_analyse_indexes_dictionary[index])-1]

        print("\n Done set_part() - note count = " + str(self.note_count) + " chord count = " + str(self.chord_count) + " rest count = " + str(self.rest_count) + "...")

        print("self.measure_analyse_indexes_all")
        print(self.measure_analyse_indexes_all)

        self.repeated_measures_lists = self.calculate_repeated_measures_lists(self.measure_analyse_indexes_dictionary, False)
        self.measure_groups_list = self.calculate_measure_groups(self.measure_analyse_indexes_all, self.measure_analyse_indexes_dictionary)
        self.repeated_measures_not_in_groups_dictionary = self.calculate_repeated_measures_not_in_groups(self.measure_analyse_indexes_dictionary.values(), self.measure_groups_list)

        self.repeated_measures_lists_rhythm = self.calculate_repeated_measures_lists(self.measure_rhythm_analyse_indexes_dictionary, True)
        self.measure_rhythm_not_full_match_groups_list = self.calculate_measure_groups(self.measure_rhythm_analyse_indexes_all, self.measure_rhythm_analyse_indexes_dictionary)
        self.repeated_rhythm_measures_not_full_match_not_in_groups_dictionary = self.calculate_repeated_measures_not_in_groups(self.repeated_measures_lists_rhythm, self.measure_rhythm_not_full_match_groups_list)

        self.repeated_measures_lists_intervals = self.calculate_repeated_measures_lists(self.measure_intervals_analyse_indexes_dictionary, True)
        self.repeated_intervals_measures_not_full_match_not_in_groups_dictionary = self.calculate_repeated_measures_not_in_groups(self.repeated_measures_lists_intervals, self.measure_intervals_not_full_match_groups_list)
        self.repeated_intervals_measures_not_full_match_not_in_groups_dictionary = self.calculate_repeated_measures_not_in_groups(self.repeated_measures_lists_intervals, self.measure_intervals_not_full_match_groups_list)

        # make lists of index and totals then sort by totals for eg most common pitch / rhythm etc
        self.count_pitches = self.count_dictionary(self.pitch_number_dictionary)
        self.count_pitch_names = self.count_dictionary(self.pitch_name_dictionary)
        self.count_intervals = self.count_dictionary(self.interval_dictionary)
        self.count_chord_common_names = self.count_dictionary(self.chord_common_name_dictionary)

        self.count_rhythm_note = self.count_dictionary(self.rhythm_note_dictionary)
        self.count_rhythm_rest = self.count_dictionary(self.rhythm_rest_dictionary)
        self.count_rhythm_chord = self.count_dictionary(self.rhythm_chord_dictionary)
        self.rename_count_list_keys(self.count_rhythm_note, self._DURATION_MAP)
        self.rename_count_list_keys(self.count_rhythm_rest, self._DURATION_MAP)
        self.rename_count_list_keys(self.count_rhythm_chord, self._DURATION_MAP)

        # dictionaries with list indexes as keys
        self.count_chord_pitches = self.count_dictionary(self.chord_pitches_dictionary)
        self.count_chord_intervals = self.count_dictionary(self.chord_intervals_dictionary)

    # count_list is like count_rhythm_note [[duration of individual note, count]] ordered by descending count.
    # duration is a decimal number of quarter notes ie 0.5 for an eight note -
    # swaps numeric duration for words

    def rename_count_list_keys(self, count_list, key_names):
        for item in count_list:
            if item[0] in key_names:
                item[0] = key_names.get(item[0])

    # d = {key, [list]} eg pitch_name_dictionary
    # returns eg [[C#, 5], [A,3]]
    def count_dictionary(self, d):
        sorted_list = []
        for k, v in d.items():
            sorted_list.append([k, len(v)])
        sorted_list.sort(reverse=True, key=lambda item: item[1])
        return sorted_list
