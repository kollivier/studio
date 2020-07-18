import datetime
import gettext
import re

import pycountry
from django import forms
from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.forms import UserCreationForm
from django.core import signing
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _
from le_utils.constants import exercises
from le_utils.constants import licenses

from contentcuration.models import Language
from contentcuration.models import User
from contentcuration.utils.policies import get_latest_policies

REGISTRATION_SALT = getattr(settings, 'REGISTRATION_SALT', 'registration')


def get_sorted_countries(language="en"):
    """
    Gets the list of countries sorted by localized name.

    NOTE: If we start adding more localization code, we should probably consolidate that code into a localization module.

    :param language: Language to localize into and sort
    :return: list of countries sorted by localized language
    """
    translator = gettext.translation(
        domain='iso3166',
        localedir=pycountry.LOCALES_DIR,
        languages=[language],
        codeset='utf-8',
        fallback=True,
    )

    return sorted([(c.name, translator.gettext(c.name)) for c in list(pycountry.countries)], key=lambda x: x[1])


class ExtraFormMixin(object):

    def check_field(self, field, error):
        if not self.cleaned_data.get(field):
            self.errors[field] = self.error_class()
            self.add_error(field, error)
            return False
        return self.cleaned_data.get(field)


class RegistrationForm(forms.Form, ExtraFormMixin):
    first_name = forms.CharField(widget=forms.TextInput(attrs={"dir": "auto"}), label=_('First Name'), required=True)
    last_name = forms.CharField(widget=forms.TextInput(attrs={"dir": "auto"}), label=_('Last Name'), required=True)
    email = forms.CharField(widget=forms.TextInput(attrs={"dir": "auto"}), label=_('Email'), required=True)
    password1 = forms.CharField(widget=forms.PasswordInput(render_value=True, attrs={"dir": "auto"}), label=_('Password'), required=True,)
    password2 = forms.CharField(widget=forms.PasswordInput(render_value=True, attrs={"dir": "auto"}), label=_('Password (again)'), required=True)

    def clean_email(self):
        email = self.cleaned_data['email'].strip()
        if not re.match(r"[^@]+@[^@\.]+\.[^@]+", email):
            self.add_error('email', _('Email is invalid.'))
        elif User.objects.filter(email__iexact=email, is_active=True).exists():
            self.add_error('email', _('Email already exists.'))
        return email

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'password1', 'password2')

    def clean(self):
        super(RegistrationForm, self).clean()

        # For some reason, email sometimes doesn't remain in cleaned data
        self.cleaned_data['email'] = self.data.get('email')

        self.check_field('email', _('Email is required.'))
        self.check_field('first_name', _('First name is required.'))
        self.check_field('last_name', _('Last name is required.'))

        if self.check_field('password1', _('Password is required.')):
            if 'password2' not in self.cleaned_data or self.cleaned_data['password1'] != self.cleaned_data['password2']:
                self.errors['password2'] = self.error_class()
                self.add_error('password2', _('Passwords don\'t match.'))
        else:
            self.errors['password2'] = self.error_class()

        return self.cleaned_data


USAGES = [
    ('organization and alignment', _("Organizing or aligning existing materials")),
    ('finding and adding content', _("Finding and adding additional content sources")),
    ('sequencing', _("Sequencing materials using prerequisites")),
    ('exercise creation', _("Creating exercises")),
    ('sharing', _("Sharing materials publicly")),
    ('storage', _("Storing materials for private or local use")),
    ('tagging', _("Tagging content sources for discovery")),
    ('other', _("Other")),
]

SOURCES = [
    ('organization', _("Organization")),
    ('website', _("Learning Equality Website")),
    ('newsletter', _("Learning Equality Newsletter")),
    ('community forum', _("Learning Equality Community Forum")),
    ('github', _("Learning Equality GitHub")),
    ('social media', _("Social Media")),
    ('conference', _("Conference")),
    ('conversation', _("Conversation with Learning Equality")),
    ('demo', _("Personal Demo")),
    ('other', _("Other")),
]


class RegistrationInformationForm(UserCreationForm, ExtraFormMixin):
    use = forms.ChoiceField(required=False, widget=forms.CheckboxSelectMultiple, label=_(
        'How do you plan to use Kolibri Studio? (check all that apply)'), choices=USAGES)
    other_use = forms.CharField(required=False, widget=forms.TextInput(attrs={"dir": "auto"}))
    storage = forms.CharField(required=False, widget=forms.TextInput(
        attrs={"placeholder": _("e.g. 500MB"), "dir": "auto"}), label=_("How much storage do you need?"))

    source = forms.ChoiceField(required=False, widget=forms.Select, label=_('How did you hear about us?'), choices=SOURCES)
    organization = forms.CharField(required=False, widget=forms.TextInput(attrs={"dir": "auto"}), label=_("Name of Organization"))
    conference = forms.CharField(required=False, widget=forms.TextInput(attrs={"dir": "auto"}), label=_("Name of Conference"))
    other_source = forms.CharField(required=False, widget=forms.TextInput(attrs={"dir": "auto"}), label=_("Please describe"))
    accepted_policy = forms.BooleanField(widget=forms.CheckboxInput())

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super(RegistrationInformationForm, self).__init__(*args, **kwargs)

        countries = get_sorted_countries(self.request.LANGUAGE_CODE)
        self.fields['location'] = forms.ChoiceField(required=True, widget=forms.SelectMultiple, label=_(
            'Where do you plan to use Kolibri? (select all that apply)'), choices=countries)

    def clean_email(self):
        email = self.cleaned_data['email'].strip()
        return email

    def clean(self):  # noqa: C901
        super(RegistrationInformationForm, self).clean()

        # Lots of fields get incorrectly processed, so manually validate form
        self.errors.clear()

        # Get data from cache
        for field in RegistrationForm.Meta.fields:
            self.cleaned_data.update({field: self.request.session.get(field, None)})

        # Check uses is set, making sure space needed is indicated if storage is selected
        uses = self.request.POST.getlist('use')
        if "other" in uses:
            if self.check_field('other_use', _("Describe your 'other' use(s) for Kolibri Studio")):
                uses.append(self.cleaned_data['other_use'])
                uses.remove("other")

        if "storage" in uses:
            self.check_field('storage', _("Please indicate how much storage you intend to use"))

        # Set cleaned_data as a string (will be blank if none are selected)
        self.cleaned_data["use"] = ", ".join(uses)
        self.cleaned_data["location"] = ", ".join(self.request.POST.getlist('location'))

        self.check_field('use', _('Please indicate how you intend to use Kolibri Studio'))
        self.check_field('location', _('Please select where you plan to use Kolibri'))

        # Check "How did you hear about us?" has extra information if certain options are selected
        source = self.check_field('source', _('Please indicate how you heard about us'))
        if source:
            if source == 'organization':
                if self.cleaned_data.get('organization'):
                    self.cleaned_data['source'] = "{} (organization)".format(self.cleaned_data['organization'])
            elif source == 'conference':
                if self.cleaned_data.get('conference'):
                    self.cleaned_data['source'] = "{} (conference)".format(self.cleaned_data['conference'])
            elif source == 'other' and self.check_field('other_source', _('Please indicate how you heard about us')):
                self.cleaned_data['source'] = self.cleaned_data['other_source']

        self.check_field('accepted_policy', _('Please accept our Privacy Policy'))

        return self.cleaned_data

    def save(self, commit=True):
        user, _new = User.objects.get_or_create(email=self.cleaned_data["email"])
        user.set_password(self.cleaned_data["password1"])
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.information = {
            "uses": self.cleaned_data['use'].split(','),
            "locations": self.cleaned_data['location'].split(','),
            "space_needed": self.cleaned_data['storage'],
            "heard_from": self.cleaned_data['source'],
        }

        latest_policies = get_latest_policies()
        user.policies = {k: datetime.datetime.now().strftime("%d/%m/%y %H:%M") for k, v in latest_policies.items()}

        if commit:
            user.save()

        return user

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'password1', 'password2')


class PolicyAcceptForm(forms.Form):
    accepted = forms.BooleanField(widget=forms.CheckboxInput())
    policy_names = forms.CharField(widget=forms.HiddenInput())

    class Meta:
        model = User
        fields = ('accepted', 'policy_names')

    def save(self, user):
        user.policies = user.policies or {}
        policies = self.cleaned_data['policy_names'].rstrip(",").split(",")
        for policy in policies:
            user.policies.update({policy: datetime.datetime.now().strftime("%d/%m/%y %H:%M")})
        user.save()
        return user


class ProfileSettingsForm(UserChangeForm):
    first_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control setting_input', 'dir': 'auto'}))
    last_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control setting_input', 'dir': 'auto'}))

    class Meta:
        model = User
        fields = ('first_name', 'last_name')
        exclude = ('password', 'email')

    def clean_password(self):
        pass

    def clean(self):
        super(ProfileSettingsForm, self).clean()

        if 'first_name' not in self.cleaned_data:
            self.errors['first_name'] = self.error_class()
            self.add_error('first_name', _('First name is required.'))

        if 'last_name' not in self.cleaned_data:
            self.errors['last_name'] = self.error_class()
            self.add_error('last_name', _('Last name is required.'))
        return self.cleaned_data

    def save(self, user):
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.save()
        return user


class PreferencesSettingsForm(forms.Form):
    # TODO: Add language, audio thumbnail, document thumbnail, exercise thumbnail, html5 thumbnail once implemented
    author = forms.CharField(required=False, label=_('Author'), widget=forms.TextInput(attrs={'class': 'form-control setting_input', 'dir': 'auto'}))
    aggregator = forms.CharField(required=False, label=_('Aggregator'), widget=forms.TextInput(attrs={'class': 'form-control setting_input', 'dir': 'auto'}))
    provider = forms.CharField(required=False, label=_('Provider'), widget=forms.TextInput(attrs={'class': 'form-control setting_input', 'dir': 'auto'}))
    copyright_holder = forms.CharField(required=False, label=_('Copyright Holder'), widget=forms.TextInput(
        attrs={'class': 'form-control setting_input', 'dir': 'auto'}))
    license_description = forms.CharField(required=False, label=_('License Description'),
                                          widget=forms.TextInput(attrs={'class': 'form-control setting_input', 'dir': 'auto'}))

    m_value = forms.IntegerField(required=False, widget=forms.NumberInput(attrs={'class': 'form-control setting_input setting_change'}), label=_("M"))
    n_value = forms.IntegerField(required=False, widget=forms.NumberInput(attrs={'class': 'form-control setting_input setting_change'}), label=_("N"))
    auto_derive_video_thumbnail = forms.BooleanField(initial=True, required=False, widget=forms.CheckboxInput(attrs={
                                                     'class': 'setting_change'}), label=_("Videos"))
    auto_derive_audio_thumbnail = forms.BooleanField(initial=True, required=False, widget=forms.CheckboxInput(attrs={
                                                     'class': 'setting_change'}), label=_("Audio"))
    auto_derive_document_thumbnail = forms.BooleanField(initial=True, required=False, widget=forms.CheckboxInput(attrs={
                                                        'class': 'setting_change'}), label=_("Documents"))
    auto_derive_html5_thumbnail = forms.BooleanField(initial=True, required=False, widget=forms.CheckboxInput(attrs={
                                                     'class': 'setting_change'}), label=_("HTML Apps"))
    auto_randomize_questions = forms.BooleanField(initial=True, required=False, widget=forms.CheckboxInput(attrs={'class': 'setting_change'}))

    def __init__(self, *args, **kwargs):
        super(PreferencesSettingsForm, self).__init__(*args, **kwargs)
        class_attrs = {'class': 'form-control setting_change'}

        language_options = [(l['id'], _(l['readable_name'])) for l in Language.objects.values('id', 'readable_name').order_by('readable_name')]
        language_options.insert(0, (None, _("No language selected")))  # Add default option if no language is selected
        self.fields['language'] = forms.ChoiceField(required=False, widget=forms.Select(attrs=class_attrs), label=_('Language'), choices=language_options)

        mastery_options = tuple([(k, _(v)) for k, v in [t for t in exercises.MASTERY_MODELS] if k != "skill_check"])
        self.fields['mastery_model'] = forms.ChoiceField(widget=forms.Select(attrs=class_attrs), choices=mastery_options, label=_("Mastery at"))

        license_options = ((None, _("No license selected")),) + licenses.choices
        self.fields['license'] = forms.ChoiceField(required=False, widget=forms.Select(attrs=class_attrs), label=_('License'), choices=license_options)

    class Meta:
        model = User
        fields = ('author', 'copyright_holder', 'license', 'license_description', 'language', 'mastery_model',
                  'm_value', 'n_value', 'auto_derive_video_thumbnail', 'auto_randomize_questions')

    def save(self, user):
        user.content_defaults = {
            'author': self.cleaned_data["author"] or "",
            'aggregator': self.cleaned_data["aggregator"] or "",
            'provider': self.cleaned_data["provider"] or "",
            'copyright_holder': self.cleaned_data["copyright_holder"],
            'license': self.cleaned_data["license"],
            'license_description': self.cleaned_data['license_description'] if self.cleaned_data['license'] == 'Special Permissions' else None,
            'mastery_model': self.cleaned_data["mastery_model"],
            'auto_randomize_questions': self.cleaned_data["auto_randomize_questions"],
            'auto_derive_video_thumbnail': self.cleaned_data["auto_derive_video_thumbnail"],
            'auto_derive_audio_thumbnail': self.cleaned_data["auto_derive_audio_thumbnail"],
            'auto_derive_document_thumbnail': self.cleaned_data["auto_derive_document_thumbnail"],
            'auto_derive_html5_thumbnail': self.cleaned_data["auto_derive_html5_thumbnail"],
            'm_value': self.cleaned_data["m_value"],
            'n_value': self.cleaned_data["n_value"],
            'language': self.cleaned_data['language'],
        }
        user.save()
        return user


class StorageRequestForm(forms.Form, ExtraFormMixin):
    # Nature of content
    storage = forms.CharField(required=True, widget=forms.TextInput(attrs={"placeholder": _("e.g. 1GB"), "class": "short-field", "dir": "auto"}))
    kind = forms.CharField(required=True, widget=forms.TextInput(attrs={"placeholder": _("Mostly high resolution videos, some pdfs, etc."),
                                                                        "class": "long-field", "dir": "auto"}))
    resource_count = forms.CharField(required=True, widget=forms.TextInput(attrs={"class": "short-field", "dir": "auto"}))
    resource_size = forms.CharField(required=False, widget=forms.TextInput(attrs={"placeholder": _("e.g. 10MB"), "class": "short-field", "dir": "auto"}))
    creators = forms.CharField(required=True, widget=forms.TextInput(attrs={"class": "long-field", "dir": "auto"}))
    sample_link = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "long-field", "dir": "auto"}))

    # How are you using your content
    license = forms.MultipleChoiceField(required=True, widget=forms.CheckboxSelectMultiple(), choices=licenses.choices)
    audience = forms.CharField(required=True, widget=forms.TextInput(attrs={"placeholder": _(
        "In-school learners, adult learners, teachers, etc."), "class": "long-field", "dir": "auto"}))
    import_count = forms.CharField(required=True, widget=forms.TextInput(attrs={"class": "short-field", "dir": "auto"}))

    # Tell us more about your use of Kolibri
    org_or_personal = forms.ChoiceField(required=True, widget=forms.RadioSelect, choices=[
        ('Organization', _("I am uploading content on behalf of")),
        ('Not Affiliated', _("I am not affiliated with an organization for this work")),
    ])
    organization = forms.CharField(required=False, widget=forms.TextInput(attrs={"placeholder": _("Organization or Institution"),
                                                                                 "dir": "auto",
                                                                                 "class": "other-textbox",
                                                                                 "data-checkbox": "input[name='org_or_personal'][value='Organization']"}))
    organization_type = forms.ChoiceField(required=False, widget=forms.RadioSelect, choices=(
        ("Grassroots and/or volunteer initiative", _("Grassroots and/or volunteer initiative")),
        ("Small NGO with annual budget < $25K", _("Small NGO with annual budget < $25K")),
        ("Medium-sized NGO with budget < $500K", _("Medium-sized NGO with budget < $500K")),
        ("Larger INGO or other international agency", _("Larger INGO or other international agency")),
        ("For-profit or social enterprise company", _("For-profit or social enterprise company")),
        ("Other", _("Other")),
    ))
    organization_other = forms.CharField(required=False, widget=forms.TextInput(attrs={"dir": "auto",
                                                                                       "class": "other-textbox",
                                                                                       "data-checkbox": "input[name='organization_type'][value='Other']"}))

    # Use case
    time_constraint = forms.ChoiceField(required=False, widget=forms.RadioSelect, choices=(
        ("1 week", _("1 week")),
        ("2-4 weeks", _("2-4 weeks")),
        ("1-2 months", _("1-2 months")),
        ("3-6 months", _("3-6 months")),
        ("6+ months", _("6+ months")),
        ("Unknown", _("Unknown")),
    ))
    message = forms.CharField(required=True, widget=forms.Textarea(attrs={"rows": 4, "dir": "auto"}))

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        channels = kwargs.pop('channel_choices', None)
        super(StorageRequestForm, self).__init__(*args, **kwargs)

        self.fields['public'] = forms.MultipleChoiceField(required=False, widget=forms.SelectMultiple(attrs={"class": "multi-select-field"}), choices=channels)

        countries = get_sorted_countries(self.request.LANGUAGE_CODE)
        self.fields['location'] = forms.ChoiceField(required=False, widget=forms.SelectMultiple(attrs={"class": "multi-select-field"}), choices=countries)

    class Meta:
        fields = ("storage", "kind", "video_type", "resource_count", "resource_size", "license", "public", "audience", "org_or_personal", "organization")

    def clean(self):
        super(StorageRequestForm, self).clean()
        self.errors.clear()

        self.check_field('storage', _("Please indicate how much storage you need"))
        self.check_field('kind', _("Please indicate what kind of content you are uploading"))
        self.check_field('creators', _("Please indicate the author, curator, and/or aggregator of your content"))
        self.check_field('resource_count', _("Please indicate approximately how many resources you are planning to upload"))

        self.cleaned_data["license"] = ", ".join(self.cleaned_data.get('license') or [])
        self.check_field('license', _("Please indicate the licensing for your content"))
        self.check_field('audience', _("Please indicate your target audience"))
        self.check_field('import_count', _("Please indicate how many times this content will be imported into Kolibri per month"))

        self.check_field('org_or_personal', _("Please indicate for whom you are uploading your content"))
        if self.cleaned_data.get("org_or_personal") == "Organization":
            self.check_field('organization', _("Please indicate your organization or institution"))
            self.check_field('organization_type', _("Please indicate your organization type"))
        if self.cleaned_data.get("organization_type") == "Other":
            self.check_field('organization_other', _("Please indicate the type of your organization or group"))

        self.check_field('message', _("Please write a paragraph explaining your use case for Studio"))

        self.cleaned_data['public'] = ",".join(self.cleaned_data.get('public') or [])
        self.cleaned_data['location'] = ",".join(self.cleaned_data.get('location') or [])

        return self.cleaned_data


class AccountSettingsForm(PasswordChangeForm):
    old_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control setting_input', 'dir': 'auto'}))
    new_password1 = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control setting_input', 'dir': 'auto'}))
    new_password2 = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control setting_input', 'dir': 'auto'}))

    class Meta:
        model = User
        fields = ('old_password', 'new_password1', 'new_password2')

    def clean(self):
        super(AccountSettingsForm, self).clean()

        self.check_field('old_password', _('Current password is incorrect.'))

        if self.check_field('new_password1', _('New password is required.')):
            if 'new_password2' not in self.cleaned_data or self.cleaned_data['new_password1'] != self.cleaned_data['new_password2']:
                self.errors['new_password2'] = self.error_class()
                self.add_error('new_password2', _('New passwords don\'t match.'))
        else:
            self.errors['new_password2'] = self.error_class()

        return self.cleaned_data

    def check_field(self, field, error):
        if field not in self.cleaned_data:
            self.errors[field] = self.error_class()
            self.add_error(field, error)
            return False
        return True


class ForgotPasswordForm(PasswordResetForm):
    email = forms.EmailField(label=_("Email"), max_length=254, widget=forms.TextInput(attrs={"dir": "auto"}))

    def save(self, request=None, extra_email_context=None, **kwargs):
        """
        Generate a one-use only link for resetting password and send it to the
        user.
        """
        email = self.cleaned_data["email"]

        users = User.objects.filter(email=email)
        inactive_users = users.filter(is_active=False)
        if inactive_users.exists() and inactive_users.count() == users.count():  # all matches are inactive
            for user in inactive_users:
                if not user.password:
                    context = {
                        'site': extra_email_context.get('site'),
                        'user': user,
                        'domain': extra_email_context.get('domain'),
                    }
                    subject = render_to_string('registration/password_reset_subject.txt', context)
                    subject = ''.join(subject.splitlines())
                    message = render_to_string('registration/registration_needed_email.txt', context)
                    user.email_user(subject, message, settings.DEFAULT_FROM_EMAIL, )
                else:
                    activation_key = self.get_activation_key(user)
                    context = {
                        'activation_key': activation_key,
                        'expiration_days': settings.ACCOUNT_ACTIVATION_DAYS,
                        'site': extra_email_context.get('site'),
                        'user': user,
                        'domain': extra_email_context.get('domain'),
                    }
                    subject = render_to_string('registration/password_reset_subject.txt', context)
                    subject = ''.join(subject.splitlines())
                    message = render_to_string('registration/activation_needed_email.txt', context)
                    user.email_user(subject, message, settings.DEFAULT_FROM_EMAIL, )
        else:
            super(ForgotPasswordForm, self).save(request=request, extra_email_context=extra_email_context, **kwargs)

    def get_activation_key(self, user):
        """
        Generate the activation key which will be emailed to the user.
        """
        return signing.dumps(
            obj=getattr(user, user.USERNAME_FIELD),
            salt=REGISTRATION_SALT
        )


class ResetPasswordForm(SetPasswordForm):
    new_password1 = forms.CharField(label=_("New password"),
                                    widget=forms.PasswordInput(attrs={"dir": "auto"}),
                                    strip=False,
                                    help_text=password_validation.password_validators_help_text_html())
    new_password2 = forms.CharField(label=_("New password confirmation"),
                                    strip=False,
                                    widget=forms.PasswordInput(attrs={"dir": "auto"}))


class LoginForm(AuthenticationForm):
    username = forms.CharField(max_length=254, widget=forms.TextInput(attrs={"dir": "auto"}))
    password = forms.CharField(label=_("Password"), strip=False, widget=forms.PasswordInput(attrs={"dir": "auto"}))


class IssueReportForm(forms.Form, ExtraFormMixin):
    operating_system = forms.CharField(required=True, widget=forms.TextInput(attrs={"dir": "auto", "placeholder": _("e.g. Windows, MacOS, Linux")}))
    browser = forms.CharField(required=True, widget=forms.TextInput(attrs={"dir": "auto", "placeholder": _("e.g. Chrome, Firefox, Safari")}))
    channel = forms.CharField(required=True, widget=forms.TextInput(attrs={"dir": "auto", "placeholder": _("Name of the channel you were working on")}))
    description = forms.CharField(required=True, widget=forms.Textarea(attrs={"rows": 17, "dir": "auto",
                                                                              "placeholder": _("A description of the steps you took, and what error "
                                                                                               "message(s) you received, if any. \n\nFor example: \n"
                                                                                               "I ran into an issue while copying content from the "
                                                                                               "clipboard into the Algebra topic of my Math Grade 10 "
                                                                                               "channel. I selected the \"Algebra basics\" topic from "
                                                                                               "from the Khan Academy channel in the Math topic, added "
                                                                                               "it into my clipboard, and then opened my channel, went "
                                                                                               "to the Algebra topic, then opened the clipboard and dragged"
                                                                                               " the \"Algebra basics\" topic into it. It appeared to be "
                                                                                               "copying for a while, but then I received an error message "
                                                                                               "that said \"500 HTTP Internal Server Error\".")}))

    class Meta:
        fields = ("operating_system", "browser", "channel", "description")
