from django import forms
from django.http import HttpResponse
from django.http import FileResponse
from django.template import loader
from django.shortcuts import redirect
from django.urls import reverse
import os
import sys
import json
import logging, logging.handlers, logging.config
from talkingscores.settings import BASE_DIR, MEDIA_ROOT
from talkingscoreslib import Music21TalkingScore

from talkingscoresapp.models import TSScore, TSScoreState

logger = logging.getLogger(__name__)

class MusicXMLSubmissionForm(forms.Form):
    filename = forms.FileField(label='MusicXML file', widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
                               required=False)
    url = forms.URLField(label='URL to MusicXML file', widget=forms.URLInput(attrs={'class': 'form-control'}),
                         required=False)


class MusicXMLUploadForm(forms.Form):
    filename = forms.FileField(label='MusicXML file', widget=forms.ClearableFileInput(attrs={'class': 'form-control'}))


class TalkingScoreGenerationOptionsForm(forms.Form):
    # selected_instruments = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple, label="Selected instruments")
    bars_at_a_time = forms.ChoiceField(choices=(('1', 1), ('2', 2), ('4', 4), ('8', 8)), initial=4,
                                       label="Bars at a time")


class NotifyEmailForm(forms.Form):
    notify_email = forms.EmailField()


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
            context = {'id':id,'filename':filename}

    return HttpResponse(template.render(context, request))

# View for midi files to serve with CORS header
def midi(request, id, filename):
    fr = FileResponse(open("staticfiles/data/" + id + "/" + filename, "rb"))
    fr['Access-Control-Allow-Origin'] = '*'
    return fr

# View for a particular score
def error(request, id, filename):
    template = loader.get_template('error.html')

    if request.method == 'POST':
        form = NotifyEmailForm(request.POST)
        if form.is_valid():
            # This should get picked up by the SMTP logging and emailed to me, but perhaps it should be sent
            # specifically rather than use the logging mechanism
            logger.error("Notifications about score http://%s%s should go to %s" % (
            request.get_host(), reverse('score', args=[id, filename]), form.cleaned_data['notify_email']))
        else:
            logger.warn(str(form.errors))
    else:
        form = NotifyEmailForm()

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
    score = TSScore(id=id, filename=filename)
    data_path = score.get_data_file_path()
    options_path = data_path + '.opts'
    logger.info("Reading score %s" % data_path)
    score_info = score.info()

    if request.method == 'POST':
        form = TalkingScoreGenerationOptionsForm(request.POST)
        if form.is_valid():
            # Write out the options
            options = {"bars_at_a_time": int(form.cleaned_data["bars_at_a_time"])}
            with open(options_path, "w") as options_fh:
                json.dump(options, options_fh)
            return redirect('process', id, filename)
        else:
            logger.warn("Invalid form..." + str(form.errors))
    else:
        form = TalkingScoreGenerationOptionsForm()

    score_info['options_form'] = form

    template = loader.get_template('options.html')
    return HttpResponse(template.render(score_info, request))


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
