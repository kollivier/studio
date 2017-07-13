import json
import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, SuspiciousOperation
from django.db.models import Q, Case, When, Value, IntegerField
from django.core.urlresolvers import reverse_lazy
from django.template.loader import render_to_string
from rest_framework.renderers import JSONRenderer
from contentcuration.api import check_supported_browsers
from contentcuration.models import Channel, User, Invitation
from contentcuration.serializers import AdminChannelListSerializer, AdminUserListSerializer, CurrentUserSerializer
from rest_framework.authentication import SessionAuthentication, BasicAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.decorators import api_view, authentication_classes, permission_classes


def send_custom_email(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        try:
            subject = render_to_string('registration/custom_email_subject.txt', {'subject': data["subject"]})
            message = render_to_string('registration/custom_email.txt', {'message': data["message"]})
            recipients = User.objects.filter(email__in=data["emails"]).distinct()

            for recipient in recipients:
                recipient.email_user(subject, message, settings.DEFAULT_FROM_EMAIL, )

        except KeyError:
            raise ObjectDoesNotExist("Missing attribute from data: {}".format(data))

        return HttpResponse(json.dumps({"success": True}))

@login_required
@authentication_classes((SessionAuthentication, BasicAuthentication, TokenAuthentication))
@permission_classes((IsAdminUser,))
def administration(request):
    # Check if browser is supported
    if not check_supported_browsers(request.META['HTTP_USER_AGENT']):
        return redirect(reverse_lazy('unsupported_browser'))

    channel_list = Channel.objects.distinct().annotate(can_edit=Case(When(editors=request.user, then=Value(1)), default=Value(0), output_field=IntegerField()))
    channel_serializer = AdminChannelListSerializer(channel_list, many=True)

    user_list = User.objects.prefetch_related('editable_channels').prefetch_related('view_only_channels')
    user_serializer = AdminUserListSerializer(user_list, many=True)

    return render(request, 'administration.html', {
                                                 "channels": JSONRenderer().render(channel_serializer.data),
                                                 "current_user": JSONRenderer().render(CurrentUserSerializer(request.user).data),
                                                 "users": JSONRenderer().render(user_serializer.data),
                                                 "default_sender": settings.DEFAULT_FROM_EMAIL
                                                })

@login_required
@authentication_classes((SessionAuthentication, BasicAuthentication, TokenAuthentication))
@permission_classes((IsAdminUser,))
def make_editor(request):
    if request.method == 'POST':
        data = json.loads(request.body)

        try:
            user = User.objects.get(pk=data["user_id"])
            channel = Channel.objects.get(pk=data["channel_id"])

            channel.viewers.remove(user)                                        # Remove view-only access
            channel.editors.add(user)                                           # Add user as an editor
            channel.save()

            Invitation.objects.filter(invited=user, channel=channel).delete()   # Delete any invitations for this user

            return HttpResponse(json.dumps({"success": True}))
        except ObjectDoesNotExist:
            return HttpResponseNotFound('Channel with id {} not found'.format(channel_id))
