"""URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.8/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Add an import:  from blog import urls as blog_urls
    2. Add a URL to urlpatterns:  url(r'^blog/', include(blog_urls))
"""
import django_js_reverse.views as django_js_reverse_views
from django.conf import settings
from django.conf.urls import include
from django.conf.urls import url
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.core.urlresolvers import reverse_lazy
from django.db.models import Q
from rest_framework import permissions
from rest_framework import routers
from rest_framework import viewsets
from rest_framework.exceptions import MethodNotAllowed
from rest_framework_bulk.generics import BulkModelViewSet
from rest_framework_bulk.routes import BulkRouter

import contentcuration.serializers as serializers
import contentcuration.views.admin as admin_views
import contentcuration.views.base as views
import contentcuration.views.channels as channel_views
import contentcuration.views.files as file_views
import contentcuration.views.internal as internal_views
import contentcuration.views.nodes as node_views
import contentcuration.views.public as public_views
import contentcuration.views.settings as settings_views
import contentcuration.views.users as registration_views
import contentcuration.views.zip as zip_views
from contentcuration.celery import app
from contentcuration.forms import ForgotPasswordForm
from contentcuration.forms import LoginForm
from contentcuration.forms import ResetPasswordForm
from contentcuration.models import AssessmentItem
from contentcuration.models import Channel
from contentcuration.models import ChannelSet
from contentcuration.models import ContentKind
from contentcuration.models import ContentNode
from contentcuration.models import ContentTag
from contentcuration.models import File
from contentcuration.models import FileFormat
from contentcuration.models import FormatPreset
from contentcuration.models import Invitation
from contentcuration.models import Language
from contentcuration.models import License
from contentcuration.models import Task
from contentcuration.models import User


def get_channel_tree_ids(user):
    channels = Channel.objects.select_related('trash_tree').select_related('main_tree').filter(Q(editors=user) | Q(viewers=user) | Q(public=True))
    trash_tree_ids = channels.values_list('trash_tree__tree_id', flat=True).distinct()
    main_tree_ids = channels.values_list('main_tree__tree_id', flat=True).distinct()
    return [user.clipboard_tree.tree_id] + list(trash_tree_ids) + list(main_tree_ids)


class LicenseViewSet(viewsets.ModelViewSet):
    queryset = License.objects.all()

    serializer_class = serializers.LicenseSerializer


class LanguageViewSet(viewsets.ModelViewSet):
    queryset = Language.objects.all()

    serializer_class = serializers.LanguageSerializer


class ChannelViewSet(viewsets.ModelViewSet):
    queryset = Channel.objects.all()
    serializer_class = serializers.ChannelSerializer

    def get_queryset(self):
        if self.request.user.is_admin:
            return Channel.objects.all()
        return Channel.objects.filter(Q(editors=self.request.user) | Q(viewers=self.request.user) | Q(public=True)).distinct()


class ChannelSetViewSet(viewsets.ModelViewSet):
    queryset = ChannelSet.objects.all()
    serializer_class = serializers.ChannelSetSerializer

    def get_queryset(self):
        if self.request.user.is_admin:
            return ChannelSet.objects.all()
        return ChannelSet.objects.filter(Q(editors=self.request.user) | Q(public=True)).distinct()


class FileViewSet(BulkModelViewSet):
    queryset = File.objects.all()
    serializer_class = serializers.FileSerializer

    def get_queryset(self):
        if self.request.user.is_admin:
            return File.objects.all()
        tree_ids = get_channel_tree_ids(self.request.user)
        return File.objects.select_related('contentnode').filter(contentnode__tree_id__in=tree_ids).distinct()


class FileFormatViewSet(viewsets.ModelViewSet):
    queryset = FileFormat.objects.all()
    serializer_class = serializers.FileFormatSerializer


class FormatPresetViewSet(viewsets.ModelViewSet):
    queryset = FormatPreset.objects.all()
    serializer_class = serializers.FormatPresetSerializer


class ContentKindViewSet(viewsets.ModelViewSet):
    queryset = ContentKind.objects.all()
    serializer_class = serializers.ContentKindSerializer


class ContentNodeViewSet(BulkModelViewSet):
    queryset = ContentNode.objects.all()
    serializer_class = serializers.ContentNodeCompleteSerializer

    def get_queryset(self):
        if self.request.user.is_admin:
            return ContentNode.objects.all()

        # Set up eager loading to avoid N+1 selects
        tree_ids = get_channel_tree_ids(self.request.user)
        return ContentNode.objects.prefetch_related('children').prefetch_related('files') \
                                  .prefetch_related('assessment_items').filter(tree_id__in=tree_ids).distinct()


class TagViewSet(viewsets.ModelViewSet):
    queryset = ContentTag.objects.all()

    serializer_class = serializers.TagSerializer

    def get_queryset(self):
        if self.request.user.is_admin:
            return ContentTag.objects.all()
        return ContentTag.objects.filter(Q(channel__editors=self.request.user) | Q(channel__viewers=self.request.user) | Q(channel__public=True)).distinct()


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()

    serializer_class = serializers.UserSerializer

    def get_queryset(self):
        if self.request.user.is_admin:
            return User.objects.all()
        channel_list = list(self.request.user.editable_channels.values_list('pk', flat=True))
        channel_list.extend(list(self.request.user.view_only_channels.values_list('pk', flat=True)))
        return User.objects.filter(Q(pk=self.request.user.pk) |
                                   Q(editable_channels__pk__in=channel_list) |
                                   Q(view_only_channels__pk__in=channel_list)).distinct()


class InvitationViewSet(viewsets.ModelViewSet):
    queryset = Invitation.objects.all()

    serializer_class = serializers.InvitationSerializer

    def get_queryset(self):
        if self.request.user.is_admin:
            return Invitation.objects.all()
        return Invitation.objects.filter(Q(invited=self.request.user) |
                                         Q(sender=self.request.user) |
                                         Q(channel__editors=self.request.user) |
                                         Q(channel__viewers=self.request.user)).distinct()


class AssessmentItemViewSet(BulkModelViewSet):
    queryset = AssessmentItem.objects.all()

    serializer_class = serializers.AssessmentItemSerializer

    def get_queryset(self):
        if self.request.user.is_admin:
            return AssessmentItem.objects.all()
        tree_ids = get_channel_tree_ids(self.request.user)
        return AssessmentItem.objects.select_related('contentnode').filter(contentnode__tree_id__in=tree_ids).distinct()


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all()
    serializer_class = serializers.TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    # task creation and updates are handled by the Celery async task, so forbid them via API
    def create(self, validated_data):
        raise MethodNotAllowed('POST')

    def update(self, *args, **kwargs):
        raise MethodNotAllowed('PUT')

    def perform_destroy(self, instance):
        # TODO: Add logic to delete the Celery task using app.control.revoke(). This will require some extensive
        # testing to ensure terminating in-progress tasks will not put the db in an indeterminate state.
        app.control.revoke(instance.task_id, terminate=True)
        instance.delete()

    def get_queryset(self):
        queryset = Task.objects.none()
        channel_id = self.request.query_params.get('channel_id', None)
        if channel_id is not None:
            user = self.request.user
            channel = Channel.objects.filter(pk=channel_id).first()
            if channel:
                has_access = channel.editors.filter(pk=user.pk).exists() or \
                         channel.viewers.filter(pk=user.pk).exists() or \
                         user.is_admin
                if has_access:
                    queryset = Task.objects.filter(metadata__affects__channels__contains=[channel_id])
                else:
                    # If the user doesn't have channel access permissions, they can still perform certain
                    # operations, such as copy. So show them the status of any operation they started.
                    queryset = Task.objects.filter(user=user, metadata__affects__channels__contains=[channel_id])
                # If we're getting a list of channel tasks, exclude finished tasks for now, as
                # currently we only use this call to determine if there's a current or pending task.
                # TODO: revisit this when we start displaying channel task history
                if self.action == 'list':
                    queryset = queryset.exclude(status__in=['SUCCESS', 'FAILURE'])
        else:
            queryset = Task.objects.filter(user=self.request.user)

        return queryset


router = routers.DefaultRouter(trailing_slash=False)
router.register(r'license', LicenseViewSet)
router.register(r'language', LanguageViewSet)
router.register(r'channel', ChannelViewSet)
router.register(r'channelset', ChannelSetViewSet)
router.register(r'fileformat', FileFormatViewSet)
router.register(r'preset', FormatPresetViewSet)
router.register(r'tag', TagViewSet)
router.register(r'contentkind', ContentKindViewSet)
router.register(r'task', TaskViewSet)
router.register(r'user', UserViewSet)
router.register(r'invitation', InvitationViewSet)

bulkrouter = BulkRouter(trailing_slash=False)
bulkrouter.register(r'assessmentitem', AssessmentItemViewSet)
bulkrouter.register(r'contentnode', ContentNodeViewSet)
bulkrouter.register(r'file', FileViewSet)

urlpatterns = [
    url(r'^$', views.base, name='base'),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^api/', include(router.urls)),
    url(r'^api/', include(bulkrouter.urls)),
    url(r'^api/publish_channel/$', views.publish_channel, name='publish_channel'),
    url(r'^api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    url(r'^channels/$', views.channel_list, name='channels'),
    url(r'^(?P<channel_id>[^/]+)/edit', views.redirect_to_channel_edit, name='redirect_to_channel_edit'),
    url(r'^(?P<channel_id>[^/]+)/view', views.redirect_to_channel_view, name='redirect_to_channel_view'),
    url(r'^channels/(?P<channel_id>[^/]{32})/?$', views.redirect_to_channel, name='redirect_to_channel'),
    url(r'^channels/(?P<channel_id>[^/]{32})/edit', views.channel, name='channel'),
    url(r'^channels/(?P<channel_id>[^/]{32})/view', views.channel_view_only, name='channel_view_only'),
    url(r'^channels/(?P<channel_id>[^/]{32})/staging', views.channel_staging, name='channel_staging'),
    url(r'^accessible_channels/(?P<channel_id>[^/]{32})$', views.accessible_channels, name='accessible_channels'),
    url(r'^get_user_channels/$', views.get_user_channels, name='get_user_channels'),
    url(r'^get_user_bookmarked_channels/$', views.get_user_bookmarked_channels, name='get_user_bookmarked_channels'),
    url(r'^get_user_edit_channels/$', views.get_user_edit_channels, name='get_user_edit_channels'),
    url(r'^get_user_view_channels/$', views.get_user_view_channels, name='get_user_view_channels'),
    url(r'^get_user_public_channels/$', views.get_user_public_channels, name='get_user_public_channels'),
    url(r'^get_user_pending_channels/$', views.get_user_pending_channels, name='get_user_pending_channels'),
    url(r'^get_user_channel_sets/$', views.get_user_channel_sets, name='get_user_channel_sets'),
    url(r'^get_channels_by_token/(?P<token>[^/]+)$', views.get_channels_by_token, name='get_channels_by_token'),
    url(r'^accept_channel_invite/$', views.accept_channel_invite, name='accept_channel_invite'),
    url(r'^api/activate_channel$', views.activate_channel_endpoint, name='activate_channel'),
    url(r'^api/get_staged_diff_endpoint$', views.get_staged_diff_endpoint, name='get_staged_diff'),
    url(r'^healthz$', views.health, name='health'),
    url(r'^stealthz$', views.stealth, name='stealth'),
    url(r'^api/search/', include('search.urls'), name='search'),
    url(r'^api/add_bookmark/$', views.add_bookmark, name='add_bookmark'),
    url(r'^api/remove_bookmark/$', views.remove_bookmark, name='remove_bookmark'),
    url(r'^api/set_channel_priority/$', views.set_channel_priority, name='set_channel_priority'),
    url(r'^api/download_channel_content_csv/(?P<channel_id>[^/]{32})$', views.download_channel_content_csv, name='download_channel_content_csv'),
    url(r'^api/probers/get_prober_channel', views.get_prober_channel, name='get_prober_channel'),
]

# if activated, turn on django prometheus urls
if "django_prometheus" in settings.INSTALLED_APPS:
    urlpatterns += [
        url('', include('django_prometheus.urls')),
    ]


# Add public api endpoints
urlpatterns += [
    url(r'^api/public/channel/(?P<channel_id>[^/]+)', public_views.get_channel_name_by_id, name='get_channel_name_by_id'),
    url(r'^api/public/(?P<version>[^/]+)/channels$', public_views.get_public_channel_list, name='get_public_channel_list'),
    url(r'^api/public/(?P<version>[^/]+)/channels/lookup/(?P<identifier>[^/]+)', public_views.get_public_channel_lookup, name='get_public_channel_lookup'),
    url(r'^api/public/info', public_views.InfoViewSet.as_view({'get': 'list'}), name='info'),
]

# Add channel endpoints
urlpatterns += [
    url(r'^api/channels/get_pdf/(?P<channel_id>[^/]+)', channel_views.get_channel_details_pdf_endpoint, name='get_channel_details_pdf_endpoint'),
    url(r'^api/channels/get_ppt/(?P<channel_id>[^/]+)', channel_views.get_channel_details_ppt_endpoint, name='get_channel_details_ppt_endpoint'),
    url(r'^api/channels/get_csv/(?P<channel_id>[^/]+)', channel_views.get_channel_details_csv_endpoint, name='get_channel_details_csv_endpoint'),
]


# Add node api enpoints
urlpatterns += [
    url(r'^api/get_nodes_by_ids/(?P<ids>[^/]*)$', node_views.get_nodes_by_ids, name='get_nodes_by_ids'),
    url(r'^api/get_total_size/(?P<ids>[^/]*)$', node_views.get_total_size, name='get_total_size'),
    url(r'^api/duplicate_nodes/$', node_views.duplicate_nodes, name='duplicate_nodes'),
    url(r'^api/move_nodes/$', node_views.move_nodes, name='move_nodes'),
    url(r'^api/get_nodes_by_ids_simplified/(?P<ids>[^/]*)$', node_views.get_nodes_by_ids_simplified, name='get_nodes_by_ids_simplified'),
    url(r'^api/get_nodes_by_ids_complete/(?P<ids>[^/]*)$', node_views.get_nodes_by_ids_complete, name='get_nodes_by_ids_complete'),
    url(r'^api/create_new_node$', node_views.create_new_node, name='create_new_node'),
    url(r'^api/get_node_diff/(?P<channel_id>[^/]{32})$', node_views.get_node_diff, name='get_node_diff'),
    url(r'^api/internal/sync_nodes$', node_views.sync_nodes, name='sync_nodes'),
    url(r'^api/internal/sync_channel$', node_views.sync_channel_endpoint, name='sync_channel'),
    url(r'^api/get_prerequisites/(?P<get_postrequisites>[^/]+)/(?P<ids>[^/]*)$', node_views.get_prerequisites, name='get_prerequisites'),
    url(r'^api/get_node_path/(?P<topic_id>[^/]+)/(?P<tree_id>[^/]+)/(?P<node_id>[^/]*)$', node_views.get_node_path, name='get_node_path'),
    url(r'^api/duplicate_node_inline$', node_views.duplicate_node_inline, name='duplicate_node_inline'),
    url(r'^api/delete_nodes$', node_views.delete_nodes, name='delete_nodes'),
    url(r'^api/get_topic_details/(?P<contentnode_id>[^/]*)$', node_views.get_topic_details, name='get_topic_details'),
]

# Add file api enpoints
urlpatterns += [
    url(r'^api/thumbnail_upload/', file_views.thumbnail_upload, name='thumbnail_upload'),
    url(r'^api/exercise_image_upload/', file_views.exercise_image_upload, name='exercise_image_upload'),
    url(r'^api/image_upload/', file_views.image_upload, name='image_upload'),
    url(r'^api/multilanguage_file_upload/', file_views.multilanguage_file_upload, name='multilanguage_file_upload'),
    url(r'^zipcontent/(?P<zipped_filename>[^/]+)/(?P<embedded_filepath>.*)', zip_views.ZipContentView.as_view(), {}, "zipcontent"),
    url(r'^api/file_upload/', file_views.file_upload, name="file_upload"),
    url(r'^api/file_create/', file_views.file_create, name="file_create"),
    url(r'^api/generate_thumbnail/(?P<contentnode_id>[^/]*)$', file_views.generate_thumbnail, name='generate_thumbnail'),
]

# Add account/registration endpoints
urlpatterns += [
    url(r'^accounts/login/$', auth_views.login, {'template_name': 'registration/login.html', 'authentication_form': LoginForm}, name='login'),
    url(r'^accounts/logout/$', auth_views.logout, {'template_name': 'registration/logout.html'}, name='logout'),
    url(
        r'^accounts/password/reset/$',
        registration_views.custom_password_reset,
        {'post_reset_redirect': reverse_lazy('auth_password_reset_done'),
         'email_template_name': 'registration/password_reset_email.txt', 'password_reset_form': ForgotPasswordForm},
        name='auth_password_reset'
    ),
    url(r'^accounts/password/reset/confirm/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',
        auth_views.password_reset_confirm,
        {'post_reset_redirect': reverse_lazy('auth_password_reset_complete'), 'set_password_form': ResetPasswordForm},
        name='auth_password_reset_confirm'),
    url(r'^accounts/register/$', registration_views.UserRegistrationView.as_view(), name='registration_register'),
    url(r'^accounts/register-information/$', registration_views.InformationRegistrationView.as_view(), name='registration_information'),
    url(r'^accounts/', include('registration.backends.hmac.urls')),
    url(r'^activate/(?P<activation_key>[-:\w]+)/$', registration_views.UserActivationView.as_view(), name='registration_activate'),
    url(r'^api/send_invitation_email/$', registration_views.send_invitation_email, name='send_invitation_email'),
    url(r'^new/accept_invitation/(?P<user_id>[^/]+)/', registration_views.new_user_redirect, name="accept_invitation_and_registration"),
    url(r'^new/finish_registration/(?P<user_id>[^/]+)/$', registration_views.new_user_redirect, name="reset_password_registration"),
]

# Add settings endpoints
urlpatterns += [
    url(r'^settings/$', settings_views.settings, name='settings'),
    url(r'^settings/profile', settings_views.ProfileView.as_view(), name='profile_settings'),
    url(r'^settings/preferences', settings_views.PreferencesView.as_view(), name='preferences_settings'),
    url(r'^settings/account$', settings_views.account_settings, name='account_settings'),
    url(r'^api/delete_user_account/(?P<user_email>[^/]+)/$', settings_views.delete_user_account, name='delete_user_account'),
    url(r'^api/export_user_data/(?P<user_email>[^/]+)/$', settings_views.export_user_data, name='export_user_data'),
    url(r'^settings/account/deleted', settings_views.account_deleted, name='account_deleted'),
    url(r'^settings/tokens', settings_views.tokens_settings, name='tokens_settings'),
    url(r'^settings/storage', settings_views.StorageSettingsView.as_view(), name='storage_settings'),
    url(r'^settings/issues', settings_views.IssuesSettingsView.as_view(), name='issues_settings'),
    url(r'^settings/policies', settings_views.policies_settings, name='policies_settings'),
    url(r'^policies/update', settings_views.PolicyAcceptView.as_view(), name='policy_update'),
]

# Add internal endpoints
urlpatterns += [
    url(r'^api/internal/authenticate_user_internal$', internal_views.authenticate_user_internal, name="authenticate_user_internal"),
    url(r'^api/internal/check_version$', internal_views.check_version, name="check_version"),
    url(r'^api/internal/file_diff$', internal_views.file_diff, name="file_diff"),
    url(r'^api/internal/file_upload$', internal_views.api_file_upload, name="api_file_upload"),
    url(r'^api/internal/publish_channel$', internal_views.api_publish_channel, name="api_publish_channel"),
    url(r'^api/internal/get_staged_diff_internal$', internal_views.get_staged_diff_internal, name='get_staged_diff_internal'),
    url(r'^api/internal/activate_channel_internal$', internal_views.activate_channel_internal, name='activate_channel_internal'),
    url(r'^api/internal/check_user_is_editor$', internal_views.check_user_is_editor, name='check_user_is_editor'),
    url(r'^api/internal/get_tree_data$', internal_views.get_tree_data, name='get_tree_data'),
    url(r'^api/internal/get_node_tree_data$', internal_views.get_node_tree_data, name='get_node_tree_data'),
    url(r'^api/internal/create_channel$', internal_views.api_create_channel_endpoint, name="api_create_channel"),
    url(r'^api/internal/add_nodes$', internal_views.api_add_nodes_to_tree, name="api_add_nodes_to_tree"),
    url(r'^api/internal/finish_channel$', internal_views.api_commit_channel, name="api_finish_channel"),
    url(r'^api/internal/get_channel_status_bulk$', internal_views.get_channel_status_bulk, name="get_channel_status_bulk"),
]

# Add admin endpoints
urlpatterns += [
    url(r'^administration/', admin_views.administration, name='administration'),
    url(r'^api/make_editor/$', admin_views.make_editor, name='make_editor'),
    url(r'^api/remove_editor/$', admin_views.remove_editor, name='remove_editor'),
    url(r'^api/get_editors/(?P<channel_id>[^/]+)$', admin_views.get_editors, name='get_editors'),
    url(r'^api/send_custom_email/$', admin_views.send_custom_email, name='send_custom_email'),
    # url(r'^api/get_all_channels/$', admin_views.get_all_channels, name='get_all_channels'),
    # url(r'^api/get_all_users/$', admin_views.get_all_users, name='get_all_users'),
    url(r'^api/get_users/$', admin_views.AdminUserListView.as_view(), name='get_users'),
    url(r'^api/get_channels/$', admin_views.AdminChannelListView.as_view(), name='get_channels'),
    url(r'^api/download_channel_csv/$', admin_views.download_channel_csv, name='download_channel_csv'),
    url(r'^api/download_channel_pdf/$', admin_views.download_channel_pdf, name='download_channel_pdf'),
    url(r'^api/get_channel_kind_count/(?P<channel_id>[^/]+)$', admin_views.get_channel_kind_count, name='get_channel_kind_count'),
]

urlpatterns += [url(r'^jsreverse/$', django_js_reverse_views.urls_js, name='js_reverse')]

# I18N Endpoints
js_info_dict = {
    'packages': ('your.app.package',),
}

urlpatterns += [
    url(r'^i18n/', include('django.conf.urls.i18n')),
]

if settings.DEBUG:
    # static files (images, css, javascript, etc.)
    urlpatterns += [
        url(r'^' + settings.STORAGE_URL[1:] + '(?P<path>.*)$', file_views.debug_serve_file, name='debug_serve_file'),
        url(r'^' + settings.CONTENT_DATABASE_URL[1:] + '(?P<path>.*)$', file_views.debug_serve_content_database_file, name='content_database_debug_serve_file'),
        url(r'^' + settings.CSV_URL[1:] + '(?P<path>.*)$', file_views.debug_serve_file, name='csv_debug_serve_file'),
        url(r'^sandbox/$', views.SandboxView.as_view()),
    ]

    try:
        import debug_toolbar
        urlpatterns += [
            url(r'^__debug__/', include(debug_toolbar.urls)),
        ]
    except ImportError:
        pass
