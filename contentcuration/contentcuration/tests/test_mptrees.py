from contentcuration import models

from base import StudioTestCase
from testdata import channel, mp_tree_json, node


class MPTreeTestCase(StudioTestCase):
    def test_create(self):
        node_data = {
            'kind_id': 'topic',
            'node_id': 'root_beer',
            'title': 'Why root beer is awesome: A ten part series',
            'children': []  # you can't always trust the title!
        }
        content_node = node(node_data)
        tree_root = models.ChannelTreeNode.add_root(sort_order=0, content_node=content_node)
        assert tree_root == tree_root.get_root()
        assert tree_root.content_node == content_node


class ChannelTreeTestCase(StudioTestCase):
    def test_create_from_json(self):
        tree_json = mp_tree_json()
        my_channel = channel()

        new_tree = models.ChannelTree.load_channel_tree(my_channel, tree_json)
        assert new_tree.channel == my_channel



