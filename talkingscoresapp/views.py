from django import forms
from django.http import HttpResponse
from django.http import FileResponse
from django.template import loader
from django.shortcuts import redirect
from django.urls import reverse
import os
import sys
import json
import logging
import logging.handlers
import logging.config
from talkingscores.settings import BASE_DIR, MEDIA_ROOT
from lib.midiHandler import *

from talkingscoreslib import Music21TalkingScore

from talkingscoresapp.models import TSScore, TSScoreState

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

logger = logging.getLogger("TSScore")


class MusicXMLSubmissionForm(forms.Form):
    filename = forms.FileField(label='MusicXML file', widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
                               required=False)
    url = forms.URLField(label='URL to MusicXML file', widget=forms.URLInput(attrs={'class': 'form-control'}),
                         required=False)


class MusicXMLUploadForm(forms.Form):
    filename = forms.FileField(label='MusicXML file', widget=forms.ClearableFileInput(attrs={'class': 'form-control'}))


class TalkingScoreGenerationOptionsForm(forms.Form):
    chk_playAll = forms.BooleanField(required=False)
    chk_playSelected = forms.BooleanField(required=False)
    chk_playUnselected = forms.BooleanField(required=False)

    instruments = forms.CharField(widget=forms.SelectMultiple, required=False,)
    bars_at_a_time = forms.ChoiceField(choices=(('1', 1), ('2', 2), ('4', 4), ('8', 8)), initial=4,
                                       label="Bars at a time")

    pitch_description = forms.CharField(widget=forms.Select, required=False,)
    rhythm_description = forms.CharField(widget=forms.Select, required=False,)
    dot_position = forms.CharField(widget=forms.Select, required=False,)
    rhythm_announcement = forms.CharField(widget=forms.Select, required=False,)
    octave_description = forms.CharField(widget=forms.Select, required=False,)
    octave_position = forms.CharField(widget=forms.Select, required=False,)
    octave_announcement = forms.CharField(widget=forms.Select, required=False,)

    colour_position = forms.CharField(widget=forms.Select, required=False,)
    chk_colourPitch = forms.BooleanField(required=False)
    chk_colourRhythm = forms.BooleanField(required=False)
    chk_colourOctave = forms.BooleanField(required=False)


class NotifyEmailForm(forms.Form):
    notify_email = forms.EmailField()


def send_error_email(error_message):
    if ('EMAIL_PASSWORD' in os.environ):  # dont try do send an email from development environment
        msg = MIMEMultipart()
        password = os.environ['EMAIL_PASSWORD']  # in pythonanywhere this can be set in wsgi.py
        msg['From'] = "talkingscores@gmail.com"
        msg['To'] = "talkingscores@gmail.com"
        msg['Subject'] = "Talking Scores Error"

        msg.attach(MIMEText(error_message, 'plain'))
        server = smtplib.SMTP('smtp.gmail.com: 587')
        server.starttls()
        server.login(msg['From'], password)
        server.sendmail(msg['From'], msg['To'], msg.as_string())
        server.quit()


def process(request, id, filename):
    template = loader.get_template('processing.html')
    context = {'id': id, 'filename': filename}
    return HttpResponse(template.render(context, request))

# View for the a particular score
def score(request, id, filename):
    score = TSScore(id=id, filename=filename)

    if score.state() == TSScoreState.AWAITING_OPTIONS:
        return redirect('options', id, filename)
    elif score.state() == TSScoreState.FETCHING:
        return redirect('index')
        # elif score.state() == TSScoreState.AWAITING_PROCESSING:
        #     # FIXME - don't do this inline here, no really

        # context = RequestContext(request, {})
    else:
        try:
            html = score.html()
            return HttpResponse(html)
        except:
            logger.exception("Unable to process score:  http://%s%s " % (request.get_host(), reverse('score', args=[id, filename])))
            return redirect('error', id, filename)
            template = loader.get_template('error.html')
            context = {'id': id, 'filename': filename}

    return HttpResponse(template.render(context, request))

# View for midi files to serve with CORS header
# use GET query string to generate the correct midi file
def midi(request, id, filename):
    mh = MidiHandler(request.GET, id, filename)
    midiname = mh.get_or_make_midi_file()
    fr = FileResponse(open(os.path.join(BASE_DIR, "staticfiles", "data", id, midiname), "rb"))
    fr['Access-Control-Allow-Origin'] = '*'
    fr['X-Robots-Tag'] = "noindex"
    return fr

# View for a particular score
def error(request, id, filename):
    template = loader.get_template('error.html')

    if request.method == 'POST':
        form = NotifyEmailForm(request.POST)
        if form.is_valid():
            logger.error("Notifications about score http://%s%s should go to %s" % (
                request.get_host(), reverse('score', args=[id, filename]), form.cleaned_data['notify_email']))
            send_error_email(
                "Notifications about score http://%s%s should go to %s" % (
                    request.get_host(), reverse('score', args=[id, filename]),
                    form.cleaned_data['notify_email']))
        else:
            logger.warn(str(form.errors))
    else:
        form = NotifyEmailForm()
        send_error_email(
            "Exception processing score http://%s%s " % (
                request.get_host(), reverse('score', args=[id, filename])))

    context = {'id': id, 'filename': filename, 'form': form}
    return HttpResponse(template.render(context, request))

# View for change-log
def change_log(request):
    template = loader.get_template('change-log.html')
    context = {}
    return HttpResponse(template.render(context, request))


# View for contact-us
def contact_us(request):
    template = loader.get_template('contact-us.html')
    context = {}
    return HttpResponse(template.render(context, request))

# View for privacy-policy
def privacy_policy(request):
    template = loader.get_template('privacy-policy.html')
    context = {}
    return HttpResponse(template.render(context, request))


# View for the a particular score
def options(request, id, filename):
    try:
        score = TSScore(id=id, filename=filename)
        data_path = score.get_data_file_path()
        options_path = data_path + '.opts'
        logger.info("Reading score %s" % data_path)
        score_info = score.info()
    except:
        logger.exception("Unable to process score (before options screen!):  http://%s%s " % (request.get_host(), reverse('score', args=[id, filename])))
        return redirect('error', id, filename)

    if request.method == 'POST':
        form = TalkingScoreGenerationOptionsForm(request.POST)
        if (form.is_valid() and form.cleaned_data["instruments"] != ''):
            instruments = list(map(int, eval(form.cleaned_data["instruments"])))
            # Write out the options
            options = {}
            options["bars_at_a_time"] = int(form.cleaned_data["bars_at_a_time"])
            options["play_all"] = form.cleaned_data["chk_playAll"]
            options["play_selected"] = form.cleaned_data["chk_playSelected"]
            options["play_unselected"] = form.cleaned_data["chk_playUnselected"]
            options["instruments"] = instruments

            options["pitch_description"] = form.cleaned_data["pitch_description"]
            options["rhythm_description"] = form.cleaned_data["rhythm_description"]
            options["dot_position"] = form.cleaned_data["dot_position"]
            options["rhythm_announcement"] = form.cleaned_data["rhythm_announcement"]
            options["octave_description"] = form.cleaned_data["octave_description"]
            options["octave_position"] = form.cleaned_data["octave_position"]
            options["octave_announcement"] = form.cleaned_data["octave_announcement"]

            options["colour_position"] = form.cleaned_data["colour_position"]
            options["colour_pitch"] = form.cleaned_data["chk_colourPitch"]
            options["colour_rhythm"] = form.cleaned_data["chk_colourRhythm"]
            options["colour_octave"] = form.cleaned_data["chk_colourOctave"]

            with open(options_path, "w") as options_fh:
                json.dump(options, options_fh)
            return redirect('process', id, filename)
        else:
            logger.warn("Invalid form..." + str(form.errors))
            print(str(form.errors))
            if form.cleaned_data["instruments"] == '':
                form.add_error("instruments", "Please select at least one instrument to describe...")

    else:
        form = TalkingScoreGenerationOptionsForm()

    template = loader.get_template('options.html')
    context = {'form': form, 'score_info': score_info}
    return HttpResponse(template.render(context, request))


# View for the main page
def index(request):
    err = " "
    if request.method == 'POST':
        form = MusicXMLSubmissionForm(request.POST)
        if form.is_valid():

            score = None
            try:
                if 'filename' in request.FILES:
                    score = TSScore.from_uploaded_file(request.FILES['filename'])
                elif form.cleaned_data.get('url', '') != '':
                    score = TSScore.from_url(form.cleaned_data['url'])

                if score is not None:
                    # Redirect to score
                    return redirect('score', score.id, score.filename)

            except Exception as ex:
                err = ex

        # If we get this far, there's a problem
        form.add_error(None, "An error has occurred...  " + str(err))

    else:
        form = MusicXMLSubmissionForm()

    example_scores = []
    for datafile in os.listdir(os.path.join(BASE_DIR, 'talkingscoresapp', 'static', 'data')):
        if datafile.endswith('.html'):
            example_scores.append(os.path.basename(datafile))

    template = loader.get_template('index.html')
    context = {'form': form, 'example_scores': example_scores}
    return HttpResponse(template.render(context, request))
