import networkx as nx
import math
import copy

from node import Child

# FOR CH AND S_CH
# if W < t, re-elect

# FOR CHILD NODE TO CHECK IF PARENT WENT DOWN
    # check overall score, if less than ?, find closest ch

# FOR PARENT TO RE-ELECT A CHILD
    # normal way (replacing itself)
    # non-normal way (electing new guy)

####### STATE VARIABLE EQUIVALENTS ########
# 0 = BS, 1 = CH, 2 = S_CH, 3 = ON

####### UPDATE_HEAD MESSAGE FORMAT ########
# newHead: node ID elected as new head
# chdList: dictionary of the old head's children and their TDMA slots (-1 for not chosen)
# oldHead: node ID of the old head
# oldParent: node ID of the old head's parent
# type: type of message (UPDATE_HEAD)
###########################################

###### UPDATE_NOHEAD MESSAGE FORMAT #######
# chdList: list of the old head's children
# newHead: node ID of the new head
# oldHead: node ID of the old head
# type: type of message (UPDATE_NOHEAD)


# NOTES
# send message after new TDMA schedule? how do i do that
# not sure how to find closest CH


def dist(a, b):
    x1, y1 = a["pos"]
    x2, y2 = b["pos"]
    return math.sqrt((x1-x2)**2 + (y1-y2)**2)

# Current CH or S_CH enters the head update phase
def elect_new_head(G, ni, Eth):
    node = G.nodes[ni]["node"]
    state = node.state
    energy = node.energy

    # CHANGE THIS TO OVERALL SCORE??
    if (energy > Eth): return  # do not update if energy is still high

    children = node.chdList

    # Choose a node within the children that fit the criteria
    candidates = [
        G.nodes[child] for child in children
        if G.nodes[child]["node"].state == state+1 and G.nodes[child]["node"].energy > Eth
    ]

    if candidates:
        new_head = min(candidates, key= lambda c: dist(node, c))  # elect smallest distance node
        
        # send UPDATE_HEAD with ID of new head, ChdList, ID of this node, parent ID, type of msg
        UPDATE_HEAD = {
            "newHead": G.nodes[new_head]["nodes"].id,
            "chdList": node.chdList,
            "oldHead": node.id,
            "oldParent": node.parent,
            "type": "UPDATE_HEAD"
        }

        # delete chdList
        node.chdList = {}
        # update parent to new head
        node.parent = new_head
        # update state
        node.state += 1

        return UPDATE_HEAD, new_head

    # send UPDATE_NOHEAD with ChdList and parent ID, NodeID, type
    UPDATE_NOHEAD = {
        "chdList": node.chdList,
        "oldHead": node.id,
        "newHead": node.parent,
        "type": "UPDATE_NOHEAD"
    }
    # delete ChdList
    node.chdList = {}

    return UPDATE_NOHEAD, None  # no possible candidates

# Elect new head within orphaned nodes
def elect_new_head_orphans(G, ni, msg, Eth):
    node = G.nodes[ni]["node"]
    # Choose a node within the children that fit the criteria
    candidates = [
        G.nodes[child] for child in msg["chdList"]
        if G.nodes[child]["node"].state == (node.state)+1 and G.nodes[child]["node"].energy > Eth
    ]

    if candidates:
        new_head = min(candidates, key= lambda c: dist(node, c))  # elect smallest distance node
        
        # send UPDATE_HEAD_ORPHAN with ID of new head, ChdList, ID of this node, parent ID, type of msg
        UPDATE_HEAD_ORPHAN = {
            "newHead": G.nodes[new_head]["node"].id,
            "chdList": msg["chdList"],
            "oldHead": node.id,
            "oldParent": node.parent,
            "type": "UPDATE_HEAD_ORPHAN"
        }

        # add the new head to chdList
        node.chdList[G.nodes[new_head]["node"].id] = Child(state=G.nodes[new_head]["node"].state)
        # TDMA schedule (use the one from network model)
        node = create_TDMA_schedule(node)

        return UPDATE_HEAD_ORPHAN, new_head

    # else, keep them all as children
    node.chdList.update(msg["chdList"])
    # TDMA schedule
    node = create_TDMA_schedule(node)

    # Send message to confirm to children that they are the new parent?

    return None  # no possible candidates

# Nodes update themselves when receiving UPDATE_HEAD or UPDATE_HEAD_ORPHANED message
def child_update_new_head(G, ni, msg):
    node = G.nodes[ni]["node"]
    # If this is the new head, update itself as parent
    if (node.id == msg["newHead"]):
        # update state to new state
        node.state -= 1
        # if chdList is not empty, update the children state to state-1
        chdList = node.chdList
        if (len(chdList) > 0):
            for child in chdList:
                G.nodes[child]["node"].state -= 1
            # then add the chdList from the message to its own list
            node.chdList.update(copy.deepcopy(msg["chdList"]))
            del node.chdList[node.id]
            # create new TDMA schedule
            node = create_TDMA_schedule(node)

        # if ChdList is empty, add ChdList
        else:
            node.chdList = copy.deepcopy(msg["chdList"])
            del node.chdList[node.id]

        # Update parent of itself to parent in the message only if not orphaned
        if (msg["type"] != "UPDATE_HEAD_ORPHAN"): node.parent = msg["oldParent"]

    elif(node.id == msg["oldParent"]):
        # Take out old head and add new head to chdList
        old_slot = node.chdList[msg["oldHead"]]
        del node.chdList[msg["oldHead"]]
        node.chdList[msg["newHead"]] = old_slot  # use the time slot of the old head

    # If this is a child, update its parent to new head
    else:
        node.parent = msg["newHead"]

    return node

# Any node that receives UPDATE_NOHEAD message udpates itself
def update_no_head(G, ni, msg):
    node = G.nodes[ni]["node"]
    # if node is one of the children from the message, update its parent to the parent in the message
    if(node.id in msg["chdList"]):
        node.parent = msg["newHead"]
        if(node.state == 3): node.state -= 1  # move state one down if ON

    # if the node is the parent in the message, add the children to its chdList
    elif(node.id == msg["newHead"]):
        node.chdList.update(msg["chdList"].copy())
        # Create new TDMA schedule
        node = create_TDMA_schedule(node)
        # Broadcast MEMBERACK

    # if the node is the old head, empty the child list --> already done in the election?
    # elif(node["id"] == msg["oldHead"]):
    #     node["chdList"] = {}

    return node

# Observe if parent is still viable during election phase
def observe_parent_potential(G, ni, Oth):
    node = G.nodes[ni]["node"]
    # Check if parent overall score is greater than a threshold
    if(G.nodes[node.parent]["node"].overall_score > Oth): return

    # Parent is dead, move to closest CH
    closest_CH = find_closest_CH(node)

    # Set parent to closest_CH
    node.parent = closest_CH

    # Send REQUEST_PARENT message to new parent
    REQUEST_PARENT = {
        "child": node,
        "type": "REQUEST_PARENT"
    }

    return REQUEST_PARENT

# Find closest CH when parent is destroyed or dead
def find_closest_CH(node):
    pass

# Create new TDMA schedule for children
def create_TDMA_schedule(node):
    slot = 0

    for child in node["chdList"]:
        node["chdList"][child] = slot
        slot+=1

    return node

# G = nx.Graph()
# G.add_node(100, id=100, parent=-1, chdList={0:1}, state=1, energy=10, pos=[1,0])
# G.add_node(0, id=0, parent=100, chdList={1:-1, 2:-1, 3:-1}, state=1, energy=20, pos=[0,0])

# G.add_node(1, id=1, parent=0, chdList={}, state=2, energy=60, pos=[1,2])
# G.add_node(2, id=2, parent=0, chdList={}, state=2, energy=20, pos=[3,3])
# G.add_node(3, id=3, parent=0, chdList={}, state=2, energy=50, pos=[0,1])

# G.add_edge(0, 100)
# G.add_edge(0, 1)
# G.add_edge(0, 2)
# G.add_edge(0, 3)

# update_head_msg = (elect_new_head(G.nodes[0], 70))
# # update_head_orphan_msg = elect_new_head_orphans(G.nodes[0], {"chdList": {1:-1, 2:-1, 3:-1}}, 30)
# print(update_head_msg)
# print(G.nodes[0])
# # updated_node = child_update_new_head(G.nodes[update_head_orphan_msg[0]["newHead"]], update_head_orphan_msg[0])
# # print(updated_node)
# if(update_head_msg[0]["type"] == "UPDATE_HEAD"):
#     for n in update_head_msg[0]["chdList"]:
#         updated_node = child_update_new_head(G.nodes[n], update_head_msg[0])
#         print(updated_node)
# else:
#     for n in update_head_msg[0]["chdList"]:
#         updated_node = update_no_head(G.nodes[n], update_head_msg[0])
#         print(updated_node)

# updated_node = update_no_head(G.nodes[100], update_head_msg[0])
# print(updated_node)

