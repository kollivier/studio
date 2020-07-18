var Models = require('../models');
var createContentNodeCollection = require('./vuex/importUtils').createContentNodeCollection;

exports.hasRelatedContent = function(contentNodes) {
  var collection = createContentNodeCollection(contentNodes);
  return collection.has_related_content();
};

/**
 * Given an Array of ContentNode IDs, return an Array of the corresponding ContentNode Objects
 * @param {Array<string>} nodeIds
 * @returns {Promise<Array<ContentNode>>}
 */
exports.fetchContentNodesById = function(nodeIds) {
  var collection = new Models.ContentNodeCollection();
  return collection.get_all_fetch_simplified(nodeIds).then(function(nodeCollection) {
    return nodeCollection.toJSON();
  });
};

function fetchItemSearchResults(searchTerm, currentChannelId) {
  return new Promise(function(resolve, reject) {
    $.ajax({
      method: 'GET',
      // omitting slash results in 301
      url: '/api/search/items/',
      success: resolve,
      error: reject,
      data: {
        q: searchTerm,
        exclude_channel: currentChannelId || '',
      },
    });
  });
}

function fetchTopicSearchResults(searchTerm, currentChannelId) {
  return new Promise(function(resolve, reject) {
    $.ajax({
      method: 'GET',
      url: '/api/search/topics/',
      success: resolve,
      error: reject,
      data: {
        q: searchTerm,
        exclude_channel: currentChannelId || '',
      },
    });
  });
}

exports.fetchSearchResults = function(searchTerm, currentChannelId) {
  return Promise.all([
    fetchItemSearchResults(searchTerm, currentChannelId),
    fetchTopicSearchResults(searchTerm, currentChannelId),
  ]).then(function(results) {
    return {
      searchTerm: searchTerm,
      itemResults: results[0],
      topicResults: results[1],
    };
  });
};

exports.getIconClassForKind = function(kind) {
  switch (kind) {
    case 'topic':
      return 'folder';
    case 'video':
      return 'theaters';
    case 'audio':
      return 'headset';
    case 'image':
      return 'image';
    case 'exercise':
      return 'star';
    case 'document':
      return 'description';
    case 'html5':
      return 'widgets';
    case 'slideshow':
      return 'photo_library';
    default:
      return 'error';
  }
};
