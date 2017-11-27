# -*- coding: utf-8 -*-

import html

from common_helper_files import human_readable_file_size
from flask import jsonify, render_template

from helperFunctions.file_tree import get_correct_icon_for_mime, FileTreeNode
from helperFunctions.web_interface import ConnectTo
from intercom.front_end_binding import InterComFrontEndBinding
from storage.db_interface_compare import CompareDbInterface
from storage.db_interface_frontend import FrontEndDbInterface
from web_interface.components.component_base import ComponentBase
from web_interface.filter import encode_base64_filter, bytes_to_str_filter


class AjaxRoutes(ComponentBase):
    def _init_component(self):
        self._app.add_url_rule('/ajax_tree/<uid>', 'ajax_tree/<uid>', self._ajax_get_tree_children)
        self._app.add_url_rule('/ajax_root/<uid>', 'ajax_root/<uid>', self._ajax_get_tree_root)
        self._app.add_url_rule('/compare/ajax_tree/<compare_id>/<root_uid>/<uid>', 'compare/ajax_tree/<compare_id>/<root_uid>/<uid>',
                               self._ajax_get_tree_children)
        self._app.add_url_rule('/compare/ajax_common_files/<compare_id>/<feature_id>/', 'compare/ajax_common_files/<compare_id>/<feature_id>/',
                               self._ajax_get_common_files_for_compare)
        self._app.add_url_rule('/ajax_get_binary/<mime_type>/<uid>', 'ajax_get_binary/<type>/<uid>', self._ajax_get_binary)

    def _get_exclusive_files(self, compare_id, root_uid):
        if compare_id is None or root_uid is None:
            return None
        with ConnectTo(CompareDbInterface, self._config) as sc:
            result = sc.get_compare_result(compare_id)
        try:
            exclusive_files = result['plugins']['File_Coverage']['exclusive_files'][root_uid]
        except KeyError:
            exclusive_files = []
        return exclusive_files

    def _ajax_get_tree_children(self, uid, root_uid=None, compare_id=None):
        exclusive_files = self._get_exclusive_files(compare_id, root_uid)
        children = []
        root = FileTreeNode(None)
        with ConnectTo(FrontEndDbInterface, self._config) as sc:
            child_uids = sc.get_specific_fields_of_db_entry(uid, {'files_included': 1})['files_included']
            for child_uid in child_uids:
                if not exclusive_files or child_uid in exclusive_files:
                    for node in sc.generate_file_tree_node(child_uid, uid, whitelist=exclusive_files):
                        root.add_child_node(node)
        for child_node in root.get_list_of_child_nodes():
            child = self._generate_jstree_node(child_node)
            children.append(child)
        return jsonify(children)

    def _ajax_get_tree_root(self, uid):
        root = list()
        with ConnectTo(FrontEndDbInterface, self._config) as sc:
            for node in sc.generate_file_tree_node(uid, uid):  # only a single item in this 'iterable'
                root = [self._generate_jstree_node(node)]
        return jsonify(root)

    @staticmethod
    def _get_jstree_node_contents(text, a_attr, li_attr, icon):
        return {
            'text': text,
            'a_attr': {'href': a_attr},
            'li_attr': {'href': li_attr},
            'icon': icon
        }

    def _get_virtual_jstree_node_contents(self, node):
        return self._get_jstree_node_contents('{}'.format(node.name), '#', '#', '/static/file_icons/folder.png')

    def _get_not_analyzed_jstree_node_contents(self, node):
        return self._get_jstree_node_contents(
            '{}'.format(node.name), '/analysis/{}'.format(node.uid), '/analysis/{}'.format(node.uid), '/static/file_icons/not_analyzed.png'
        )

    def _get_analyzed_jstree_node_contents(self, node):
        result = self._get_jstree_node_contents(
            '<b>{}</b> (<span style="color:gray;">{}</span>)'.format(node.name, human_readable_file_size(node.size)),
            '/analysis/{}'.format(node.uid), '/analysis/{}'.format(node.uid), get_correct_icon_for_mime(node.type)
        )
        result['data'] = {'uid': node.uid}
        return result

    def _get_jstree_child_nodes(self, node):
        child_nodes = node.get_list_of_child_nodes()
        if not child_nodes:
            return True
        result = []
        for child in child_nodes:
            result_child = self._generate_jstree_node(child)
            if result_child is not None:
                result.append(result_child)
        return result

    def _generate_jstree_node(self, node):
        '''
        converts a file tree node to a json dict that can be rendered by jstree
        :param node: the file tree node
        :return: a json-compatible dict containing the jstree data
        '''
        if node.virtual:
            result = self._get_virtual_jstree_node_contents(node)
        elif node.not_analyzed:
            result = self._get_not_analyzed_jstree_node_contents(node)
        else:
            result = self._get_analyzed_jstree_node_contents(node)
        if node.has_children:
            result['children'] = self._get_jstree_child_nodes(node)
        return result

    def _ajax_get_common_files_for_compare(self, compare_id, feature_id):
        with ConnectTo(CompareDbInterface, self._config) as sc:
            result = sc.get_compare_result(compare_id)
        feature, key = feature_id.split('___')
        uid_list = result['plugins']['File_Coverage'][feature][key]
        return self._get_nice_uid_list_html(uid_list)

    def _get_nice_uid_list_html(self, input_data):
        with ConnectTo(FrontEndDbInterface, self._config) as sc:
            included_files = sc.get_data_for_nice_list(input_data, None)
        number_of_unanalyzed_files = len(input_data) - len(included_files)
        return render_template(
            'generic_view/nice_fo_list.html',
            fo_list=included_files,
            number_of_unanalyzed_files=number_of_unanalyzed_files,
            omit_collapse=True
        )

    def _ajax_get_binary(self, mime_type, uid):
        mime_type = mime_type.replace('_', '/')
        div = '<div style="display: block; border: 1px solid; border-color: #dddddd; padding: 5px; text-align: center">'
        with ConnectTo(InterComFrontEndBinding, self._config) as sc:
            binary = sc.get_binary_and_filename(uid)[0]
        if 'text/' in mime_type:
            return '<pre style="white-space: pre-wrap">{}</pre>'.format(html.escape(bytes_to_str_filter(binary)))
        elif 'image/' in mime_type:
            return '{}<img src="data:image/{} ;base64,{}" style="max-width:100%"></div>'.format(div, mime_type[6:], encode_base64_filter(binary))
        return None