var _ = require('underscore');
var BaseViews = require('edit_channel/views');
var Models = require('edit_channel/models');
var stringHelper = require('edit_channel/utils/string_helper');
require('modal-styles.less');
const Constants = require('edit_channel/constants/index');

var NAMESPACE = 'preview';
var MESSAGES = {
  show_fullscreen: 'Show Fullscreen',
  hide_fullscreen: 'Hide Fullscreen',
  select_file: 'Select a format to preview.',
  preview_exercise: 'Preview this exercise on the source website',
  video_error: 'Your browser does not support the video tag.',
  image_error: 'Image failed to load',
};

var PreviewModalView = BaseViews.BaseModalView.extend({
  template: require('./hbtemplates/preview_modal.handlebars'),
  modal: true,
  initialize: function() {
    _.bindAll(this, 'close_preview');
    this.render(this.close_preview, { node: this.model.toJSON() });
    this.preview_view = new PreviewView({
      model: this.model,
      el: this.$('.modal-body'),
    });
    this.preview_view.switch_preview(this.model);
  },
  close_preview: function() {
    this.remove();
  },
});

var PreviewView = BaseViews.BaseView.extend({
  name: NAMESPACE,
  $trs: MESSAGES,
  tabs_template: require('./hbtemplates/preview_templates/tabs.handlebars'),
  template: require('./hbtemplates/preview_dialog.handlebars'),
  initialize: function() {
    _.bindAll(
      this,
      'select_preview',
      'toggle_fullscreen',
      'load_preview',
      'exit_fullscreen',
      'render_preview'
    );
    this.current_preview = null;
    this.render();
  },
  events: {
    'click .preview_btn_tab': 'select_preview',
    'click .view_fullscreen': 'toggle_fullscreen',
  },
  render: function() {
    this.load_preview();
    this.$el.html(
      this.template(
        {
          file: this.current_preview,
        },
        {
          data: this.get_intl_data(),
        }
      )
    );
    this.load_preset_dropdown();
    this.render_preview();
  },
  render_preview: function() {
    if (this.current_preview) {
      this.$('.preview_format_switch').text(stringHelper.translate(this.current_preview.preset.id));
      this.generate_preview(true);
    }
  },
  load_preview: function() {
    if (this.model) {
      this.load_default_value();
      this.load_preset_dropdown();
    }
  },
  load_default_value: function() {
    this.current_preview = null;
    var preview_files = _.filter(this.model.get('files'), function(f) {
      return f.preset.display;
    });
    if (preview_files.length) {
      this.current_preview = _.min(preview_files, function(file) {
        return file.preset.order;
      });
    }
  },
  load_presets: function() {
    return new Models.FormatPresetCollection(
      _.where(_.pluck(this.model.get('files'), 'preset'), { display: true, subtitle: false })
    );
  },
  load_preset_dropdown: function() {
    this.$('#preview_tabs_dropdown').html(
      this.tabs_template({
        presets: this.load_presets().toJSON(),
      })
    );
  },
  select_preview: function(event) {
    // called internally
    var selected_preview = _.find(this.model.get('files'), function(file) {
      return file.preset.id === event.target.getAttribute('value');
    });
    this.current_preview = selected_preview;
    this.render_preview();
    var self = this;
    _.defer(function() {
      self.$('iframe').prop('src', function() {
        return $(this).data('src');
      });
    });
  },
  switch_preview: function(model) {
    // called from outside sources
    this.model = model;
    this.render();
  },
  generate_preview: function(force_load) {
    if (this.current_preview) {
      _.defer(
        render_preview,
        this.$('#preview_window'),
        this.current_preview,
        this.get_subtitles(),
        force_load && this.model.get('kind') === 'video',
        this.model.get('thumbnail_encoding') && this.model.get('thumbnail_encoding').base64,
        this.get_intl_data()
      );
    }
  },
  pause: function() {
    switch (this.model.get('kind')) {
      case 'video':
        this.$('video')
          .get(0)
          .pause();
        break;
      case 'audio':
        this.$('audio')
          .get(0)
          .pause();
        break;
    }
  },
  play: function() {
    switch (this.model.get('kind')) {
      case 'html5':
        this.$('iframe').prop('src', this.$('iframe').data('src'));
        break;
    }
  },
  get_subtitles: function() {
    var subtitles = [];
    this.model.get('files').forEach(function(file) {
      var file_json = file.attributes ? file.attributes : file;
      var preset_id =
        file_json.preset && file_json.preset.name ? file_json.preset.name : file_json.preset;
      var current_preset = Constants.FormatPresets.find(preset => preset.id === preset_id);
      if (current_preset && current_preset.subtitle) {
        subtitles.push(file_json);
      }
    });
    return subtitles;
  },
  toggle_fullscreen: function() {
    var elem = document.getElementById('preview_content_main');

    if (!this.check_fullscreen()) {
      this.$('#preview_content_main').addClass('preview_on');
      this.$('.view_fullscreen')
        .html(this.get_translation('hide_fullscreen'))
        .attr('title', this.get_translation('hide_fullscreen'));
      if (elem.requestFullscreen) {
        elem.requestFullscreen();
      } else if (elem.msRequestFullscreen) {
        elem.msRequestFullscreen();
      } else if (elem.mozRequestFullScreen) {
        elem.mozRequestFullScreen();
      } else if (elem.webkitRequestFullscreen) {
        elem.webkitRequestFullscreen();
      }
      $(document).on('webkitfullscreenchange', this.exit_fullscreen);
      $(document).on('mozfullscreenchange', this.exit_fullscreen);
      $(document).on('fullscreenchange', this.exit_fullscreen);
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
      } else if (document.mozCancelFullScreen) {
        document.mozCancelFullScreen();
      } else if (document.msExitFullscreen) {
        document.msExitFullscreen();
      }
    }
  },
  exit_fullscreen: function() {
    if (!this.check_fullscreen()) {
      this.$('#preview_content_main').removeClass('preview_on');
      this.$('.view_fullscreen')
        .html(this.get_translation('show_fullscreen'))
        .attr('title', this.get_translation('show_fullscreen'));
      $(document).off('webkitfullscreenchange');
      $(document).off('mozfullscreenchange');
      $(document).off('fullscreenchange');
      $(document).off('MSFullscreenChange');
    }
  },
  check_fullscreen: function() {
    return !(
      (document.fullScreenElement !== undefined && document.fullScreenElement === null) ||
      (document.msFullscreenElement !== undefined && document.msFullscreenElement === null) ||
      (document.mozFullScreen !== undefined && !document.mozFullScreen) ||
      (document.webkitIsFullScreen !== undefined && !document.webkitIsFullScreen)
    );
  },
});

function render_preview(el, file_model, subtitles, force_load, encoding, intl_data) {
  var preview_template;
  var source = file_model.storage_url;
  switch (file_model.file_format) {
    case 'png':
    case 'jpg':
    case 'jpeg':
      source = encoding || source;
      preview_template = require('./hbtemplates/preview_templates/image.handlebars');
      break;
    case 'pdf':
    case 'PDF':
    case 'vtt':
    case 'srt':
      preview_template = require('./hbtemplates/preview_templates/document.handlebars');
      break;
    case 'mp3':
      preview_template = require('./hbtemplates/preview_templates/audio.handlebars');
      break;
    case 'mp4':
      preview_template = require('./hbtemplates/preview_templates/video.handlebars');
      break;
    case 'perseus':
      preview_template = require('./hbtemplates/preview_templates/exercise.handlebars');
      break;
    case 'zip':
      preview_template = require('./hbtemplates/preview_templates/html5.handlebars');
      break;
    case 'json':
      preview_template = require('./hbtemplates/preview_templates/slideshow.handlebars');
      break;
    default:
      preview_template = require('./hbtemplates/preview_templates/default.handlebars');
  }
  el.html(
    preview_template(
      {
        source: source,
        extension: file_model.mimetype,
        checksum: file_model.checksum,
        subtitles: subtitles,
      },
      {
        data: intl_data,
      }
    )
  );
  if (force_load) {
    el.find('video').load();
  }
}

module.exports = {
  PreviewModalView: PreviewModalView,
  PreviewView: PreviewView,
  render_preview: render_preview,
};
