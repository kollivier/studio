var Vue = require('vue');
var Models = require("edit_channel/models");

function fetchChannelRoots() {
  return window.current_channel.get_accessible_channel_roots();
}

/** Given an Array of ContentNode Objects, create a ContentNodeCollection
 * @param {Array<ContentNode>} contentNodes
 * @returns {ContentNodeCollection}
 */
function createContentNodeCollection(contentNodes) {
    return new Models.ContentNodeCollection(contentNodes);
}

/**
 * Given an Array of ContentNode IDs, return an Array of the corresponding ContentNode Objects
 * @param {Array<string>} nodeIds
 * @returns {Promise<Array<ContentNode>>}
 */
function fetchContentNodesById(nodeIds) {
    var collection = new Models.ContentNodeCollection();
    return collection.get_all_fetch_simplified(nodeIds)
    .then(function(nodeCollection) {
        return nodeCollection.toJSON();
    });
}

function updateCounts(totals, node) {
    var counts = node.metadata;
    // if a leaf node
    if (node.kind !== 'topic') {
        return {
            resourceCount: totals.resourceCount + 1,
            topicCount: totals.topicCount,
        };
    }
    // if a topic node
    return {
        resourceCount: totals.resourceCount + counts.resource_count,
        topicCount: totals.topicCount + counts.total_count - counts.resource_count + 1,
    };
}

// $options include onConfirmImport and baseViewModel
var ImportListStore = Vue.extend({
    data: function() {
        return {
            itemsToImport: [],
            totalImportSize: 0,
            pageState: {
                type: 'search_results',
                data: {
                    searchTerm: 'top',
                }
            }
            // pageState: {
            //     type: 'tree_view',
            //     data: {},
            // },
        };
    },
    computed: {
        resourceCounts: function() {
            return this.itemsToImport.reduce(updateCounts, {
                resourceCount: 0,
                topicCount: 0,
            });
        },
        eventTypes: function() {
            return {
                START_IMPORT: 'start_import',
                FINISH_IMPORT: 'finish_import',
                SHOW_RELATED_CONTENT_WARNING: 'show_related_content_warning',
            };
        },
    },
    watch: {
        itemsToImport: function(newVal) {
            this.getImportSize(newVal)
            .then(function(size) {
                this.totalImportSize = size;
            }.bind(this));
        },
    },
    methods: {
        goToSearchResults: function(searchTerm) {
            this.itemsToImport = [],
            this.pageState = {
                type: 'search_results',
                data: {
                    searchTerm: searchTerm,
                },
            };
        },
        goToTreeViewPage: function() {
            this.itemsToImport = [],
            this.pageState = {
                type: 'tree_view',
                data: {},
            };
        },
        goToPreviousPage() {
            if(this.pageState.type === 'search_results') {
                return this.goToTreeViewPage();
            }
        },
        getCurrentChannelId() {
            return window.current_channel.get('id');
        },
        fetchItemSearchResults(searchTerm) {
            return new Promise(function(resolve, reject) {
                $.ajax({
                    method:"GET",
                    // omitting slash results in 301
                    url: '/api/search/items/',
                    success: resolve,
                    error: reject,
                    data: {
                        q: searchTerm,
                        exclude_channel: this.getCurrentChannelId() || '',
                    },
                });
            }.bind(this));
        },
        fetchTopicSearchResults(searchTerm) {
            return new Promise(function(resolve, reject) {
                $.ajax({
                    method:"GET",
                    url: '/api/search/topics/',
                    success: resolve,
                    error: reject,
                    data: {
                        q: searchTerm,
                        exclude_channel: this.getCurrentChannelId() || '',
                    },
                });
            }.bind(this));
        },
        fetchContentNodesById: fetchContentNodesById,
        createContentNodeCollection: createContentNodeCollection,
        fetchChannelRoots: fetchChannelRoots,
        addItemToImport: function(contentNode) {
            this.itemsToImport.push(contentNode);
        },
        removeItemToImport: function(nodeId) {
            this.itemsToImport = this.itemsToImport.filter(function(node) {
                return node.id !== nodeId;
            }.bind(this));
        },
        getImportCollection: function() {
            return this.createContentNodeCollection(this.itemsToImport);
        },
        // takes an array of ContentNodes, and returns their size in bytes
        getImportSize: function(contentNodes) {
            var collection = this.createContentNodeCollection(contentNodes);
            return collection.calculate_size()
        },
        commitImport: function() {
            var importCollection = this.getImportCollection();
            if (importCollection.has_related_content()) {
                this.$emit(
                    this.eventTypes.SHOW_RELATED_CONTENT_WARNING,
                    this._commitImport.bind(this)
                );
            } else {
                this._commitImport();
            }
        },
        _commitImport: function() {
            // event for ImportModalView
            this.$emit(this.eventTypes.START_IMPORT);
            this.getImportCollection()
            .duplicate(this.$options.baseViewModel)
            .then(function(collection) {
                // event for ImportModalView
                this.$options.onConfirmImport(collection);
                this.$emit(this.eventTypes.FINISH_IMPORT);
            }.bind(this));
        }
    },
});

module.exports = ImportListStore;
