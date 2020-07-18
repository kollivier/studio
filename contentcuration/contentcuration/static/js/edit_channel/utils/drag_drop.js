const WorkspaceManager = require('./workspace_manager');
var Models = require('edit_channel/models');
var stringHelper = require('edit_channel/utils/string_helper');
var dialog = require('edit_channel/utils/dialog');

/* handleDrop: adds dropping ability to a certain container
 *   Parameters:
 *       container: container to add dropping ability to
 */
function addSortable(element, selected_class, callback) {
  var selectedClass = selected_class;

  element.$el
    .find('.content-list')
    .sortable({
      revert: false,
      placeholder: 'sorting-placeholder',
      forcePlaceholderSize: true,
      scroll: true,
      scrollSpeed: 10,
      connectWith: '.content-list',
      tolerance: 'pointer',
      delay: 100,
      distance: 5,
      cursor: 'move',
      cancel: '.current_topic, .default-item, #preview li',
      containment: '#channel-edit-sortable-boundary',
      appendTo: 'body',
      bodyClass: 'dragging',
      // helper:"clone",
      helper: function(e, item) {
        if (!item.hasClass(selectedClass)) item.addClass(selectedClass);
        var elements = $('.' + selectedClass)
          .not('.current_topic')
          .clone();
        var helper = $('<ul class="list-unstyled ui-sorting-list" id="drag-list"/>');
        item
          .siblings('.' + selectedClass)
          .not('.current_topic')
          .addClass('hidden');
        return helper.append(elements);
      },
      start: function(e, ui) {
        var elements = $('.' + selectedClass + '.hidden')
          .not('.current_topic')
          .not('.sorting-placeholder');
        ui.item.data('items', elements);

        // TODO(davidhu): Should send an event that the clipboard listens and
        // responds to instead.
        var queue = WorkspaceManager.get_queue_view();
        if (!queue.is_pinned()) {
          queue.close_queue();
        }

        $('body').addClass('dragging');
      },
      receive: function(e, ui) {
        ui.item.before(ui.item.data('items'));
      },
      stop: function(e, ui) {
        ui.item.siblings('.' + selectedClass).removeClass('hidden');
        $('.' + selectedClass + " input[type='checkbox']").prop('checked', false);
        $('.' + selectedClass).removeClass(selectedClass);
        $('body').removeClass('dragging');
      },
      beforeStop: function(event, ui) {
        if ($(event.target).parent('#queue_content') && $('#queue').hasClass('closed')) {
          ui.item.siblings('.' + selectedClass).removeClass('hidden');
          $('.' + selectedClass + " input[type='checkbox']").prop('checked', false);
          $('.' + selectedClass).removeClass(selectedClass);
        }
        var parent = $(ui.placeholder);
        if (!parent.length || !parent[0].parentNode) {
          $('body').removeClass('dragging');
          $('.content-list').sortable('cancel');
          $('.content-list').sortable('enable');
          $('.content-list').sortable('refresh');
        }
      },
      update: function(event, ui) {
        if ($('.drop-topic-hover').length === 0) {
          var view = WorkspaceManager.get(ui.item.context.id);
          if (view) {
            var order = [];
            var selected_items = new Models.ContentNodeCollection();
            var current_node = view.node.model;
            $('.content-list').sortable('disable');
            element.$el
              .find('.queue-list-wrapper >.content-list >li, >.content-list >li')
              .each(function(e, list_item) {
                if (
                  $(list_item).attr('id') &&
                  !$(list_item)
                    .attr('id')
                    .includes('default_item')
                ) {
                  var node = WorkspaceManager.get($(list_item).attr('id')).node.model;
                  order.push(node);
                }
              });
            var appended_items = new Models.ContentNodeCollection(); //Items from another container
            if (ui.item.data('items')) {
              ui.item.data('items').each(function() {
                var view = WorkspaceManager.get(this.id);
                if (view) {
                  var node = view.node.model;
                  if (
                    !selected_items.contains(current_node) &&
                    current_node.get('parent') == node.get('parent') &&
                    current_node.get('sort_order') < node.get('sort_order')
                  ) {
                    selected_items.push(current_node);
                  }
                  current_node.get('parent') === node.get('parent')
                    ? selected_items.push(node)
                    : appended_items.push(node);
                }
              });
            }

            if (!selected_items.contains(current_node)) {
              selected_items.push(current_node);
            }

            selected_items.add(appended_items.models, { at: selected_items.length });
            $('#saving-spinner').css('display', 'block');
            callback(current_node, selected_items, order)
              .then(function() {
                $('.content-list').sortable('enable');
                $('.content-list').sortable('refresh');
                $('#saving-spinner').css('display', 'none');
              })
              .catch(function(error) {
                // eslint-disable-next-line no-console
                console.error(error);
                $('body').removeClass('dragging');
                $('.content-list').sortable('cancel');
                $('.content-list').sortable('enable');
                $('.content-list').sortable('refresh');
                $('#saving-spinner').css('display', 'none');
              });
          }
        }
      },
    })
    .droppable({
      items: 'li',
      cancel: '.current_topic, .default-item, #preview, #queue',
    })
    .disableSelection();
}

function addDroppableArea(element, dropCallback, messages) {
  element.$('.button_drop, .queue-interior').droppable({
    items: 'li',
    revert: false,
    revertDuration: 0,
    cursor: 'move',
    hoverClass: 'droppable-area-hover',
    drop: function(event, ui) {
      var selected_items = new Models.ContentNodeCollection();
      var current_view = WorkspaceManager.get(ui.draggable.context.id);
      var current_node = current_view.node.model;
      $('.content-list').sortable('disable');

      var appended_items = new Models.ContentNodeCollection(); //Items from another container
      $('#drag-list li').each(function(index, item) {
        var view = WorkspaceManager.get(item.id);
        if (view) {
          var node = view.node.model;
          if (
            !selected_items.contains(current_node) &&
            current_node.get('parent') == node.get('parent') &&
            current_node.get('sort_order') < node.get('sort_order')
          ) {
            selected_items.push(current_node);
          }
          current_node.get('parent') === node.get('parent')
            ? selected_items.push(node)
            : appended_items.push(node);
          $('.content-list #' + item.id).remove();
        }
      });

      if (!selected_items.contains(current_node)) {
        selected_items.push(current_node);
      }
      selected_items.add(appended_items.models, { at: selected_items.length });

      // Check for related content and display warning if found
      if (selected_items.has_related_content()) {
        dialog.dialog(
          stringHelper.get_translation(messages, 'related_content'),
          stringHelper.get_translation(messages, 'related_content_warning', selected_items.length),
          {
            [stringHelper.get_translation(messages, 'cancel')]: function() {
              $('.content-list').sortable('cancel');
              $('.content-list').sortable('enable');
              $('.content-list').sortable('refresh');
              $('#saving-spinner').css('display', 'none');
            },
            [stringHelper.get_translation(messages, 'continue')]: function() {
              dropCallback(selected_items).then(function() {
                $(ui.draggable.context).remove();
                $('.content-list').sortable('enable');
                $('.content-list').sortable('refresh');
                $('#saving-spinner').css('display', 'none');
              });
            },
          },
          null
        );
      } else {
        dropCallback(selected_items).then(function() {
          $(ui.draggable.context).remove();
          $('.content-list').sortable('enable');
          $('.content-list').sortable('refresh');
          $('#saving-spinner').css('display', 'none');
        });
      }
    },
    out: function() {
      $('.sorting-placeholder').css('display', 'block');
    },
    over: function() {
      $('.sorting-placeholder').css('display', 'none');
    },
  });
}

function addTopicDragDrop(element, hoverCallback, dropCallback) {
  var hoverInterval = 2000;
  element.$el.droppable({
    items: 'li',
    revert: false,
    revertDuration: 0,
    cursor: 'move',
    hoverClass: 'drop-topic-hover',
    drop: function(event, ui) {
      if ($(event.target).find('.drop-topic-hover').length === 0) {
        if ($('.sorting-placeholder').css('display') === 'none') {
          var selected_items = new Models.ContentNodeCollection();
          var current_view = WorkspaceManager.get(ui.draggable.context.id);
          var current_node = current_view.node.model;
          this.hoverOnItem = null;
          $('.content-list').sortable('disable');

          var appended_items = new Models.ContentNodeCollection(); //Items from another container
          $('#drag-list li').each(function(index, item) {
            var view = WorkspaceManager.get(item.id);
            if (view) {
              var node = view.node.model;
              if (
                !selected_items.contains(current_node) &&
                current_node.get('parent') == node.get('parent') &&
                current_node.get('sort_order') < node.get('sort_order')
              ) {
                selected_items.push(current_node);
              }
              current_node.get('parent') === node.get('parent')
                ? selected_items.push(node)
                : appended_items.push(node);
              $('.content-list #' + item.id).remove();
            }
          });

          if (!selected_items.contains(current_node)) {
            selected_items.push(current_node);
          }
          selected_items.add(appended_items.models, { at: selected_items.length });
          dropCallback(selected_items).then(function() {
            $(ui.draggable.context).remove();
            $('.content-list').sortable('enable');
            $('.content-list').sortable('refresh');
          });
        }
      }
    },
    out: function() {
      $('.sorting-placeholder').css('display', 'block');
      this.hoverOnItem = null;
    },
    over: function(event, ui) {
      this.hoverOnItem = $(this)[0];
      if (
        !$(this.hoverOnItem)
          .find('#menu_toggle_' + this.hoverOnItem.id)
          .hasClass('glyphicon-menu-down')
      ) {
        $('.sorting-placeholder').css('display', 'none');
        var hoverItem = $(this)[0];
        var self = this;
        setTimeout(function() {
          if (
            self.hoverOnItem === hoverItem &&
            WorkspaceManager.get(ui.draggable.context.id).node
          ) {
            hoverCallback(event);
          }
        }, hoverInterval);
      }
    },
  });
}

function removeDragDrop(element) {
  element.$el.removeClass('droppable_container');
  // element.$el.find("ul.content-list").sortable("destroy");
}

module.exports = {
  addSortable: addSortable,
  removeDragDrop: removeDragDrop,
  addTopicDragDrop: addTopicDragDrop,
  addDroppableArea: addDroppableArea,
};
