from collections import defaultdict

def get_active_business_id(request):
    """
    Gets the active business ID from session.
    Uses 'current_business_id' to match org app's select_business view.
    """
    return request.session.get("current_business_id")

def build_account_tree(accounts):
    """
    accounts: queryset/list of Account objects with .id and .parent_id
    returns list of root nodes: [{"obj": account, "children": [...]}]
    """
    children_map = defaultdict(list)
    node_map = {}

    for a in accounts:
        node_map[a.id] = {"obj": a, "children": []}
        children_map[a.parent_id].append(a.id)

    def attach(parent_id):
        nodes = []
        for child_id in sorted(children_map.get(parent_id, []), key=lambda i: node_map[i]["obj"].name.lower()):
            node = node_map[child_id]
            node["children"] = attach(child_id)
            nodes.append(node)
        return nodes

    return attach(None)
