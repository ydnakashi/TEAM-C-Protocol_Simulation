import math
import networkx as nx
from node import Node, Child, NodeType


# beginning clustering algorithm, to be run at the very start 

# pass in the networksx graph, the max distance of a what a node can hear (default is 20 for now, idk) and the constant used for twait (idk what the default should be)
def initialSelection(graph, Rc=1, alpha=0.5):
    print("stat")
    # the total amount of nodes in the graph
    N = graph.number_of_nodes()
    # dimensions of the graph, currently hardcoded for now ...
    x, y = 10, 10

    for ni in graph.nodes():      
        node = graph.nodes[ni]["node"]
        x1, y1 = node.coords
    
        for oi in graph.nodes():
            other = graph.nodes[oi]["node"]
            # check that the node is not itself
            if node == other :
                continue

            x2, y2 = other.coords

            # euclidean distance
            dist = math.sqrt((x1-x2)**2 + (y1-y2)**2)
            # print("distance: ", dist)

            if dist <= (3/2) * Rc:
                node.neighbourList[other.id] = other.coords
                node.neighbourListOrder.insert(0, other.id)

            # if dist <= Rc:
            #     node.neighbourList.append((other, dist))
            # only nodes that are within the multipled distance but outside of Rc are added
            # elif dist <= (3/2) * Rc:
            #     node.broadcastList.append((other, dist))
                

    # nodes to cluster ratio
    NC = x * y / (Rc) ** 2
    NNavg = N / NC

    # twait calculations
    for ni in graph.nodes():
        node = graph.nodes[ni]["node"]
        NNi = len(node.neighbourList)

        if NNi == 0:
            node.twait = 1000
            continue

        # icd compute
        total_dist = sum(dist for (_, dist) in node.neighbourList)
        ICDi = total_dist / NNi
        # print("ICDI: " ,ICDi)

        if NNi > NNavg:
            twait = alpha * (ICDi / Rc) + (1 - alpha) * \
                (1 - (NNi / N)) * (1 - ((NNi - NNavg) / N))
        else:
            twait = alpha * (ICDi / Rc) + (1 - alpha) * \
                (1 - (NNi / N))
        node.twait = twait
    # createClusters(graph)

def createClusters(graph):
    print("starting clusters")
    
    sortedNodes = sorted(graph.nodes(), key=lambda n: graph.nodes[n]["node"].twait)
    bsCoords = []
    # no broadcast received - send out a CH message
    for n in sortedNodes:
        node = graph.nodes[n]["node"]
        if node.state == NodeType.BASE_STATION: 
            print("bs")
            bsCoords = node.coords
            print(bsCoords)
            continue
        elif node.state == None:
            node.state = NodeType.CLUSTER_HEAD
            node.broadcast(message={
                "type": "STATE",
                "sender": node.id,
                "state": NodeType.CLUSTER_HEAD})
        elif node.state == NodeType.IRRESOLUTE:
            node.state = NodeType.CLUSTER_HEAD
            node.broadcast(message={
                "type": "STATE",
                "sender": node.id,
                "state": NodeType.IRRESOLUTE})

    for n in sortedNodes:
        node = graph.nodes[n]["node"]
        # find nearest CH to the BS to get CH to CH routing
        nodeList = []
        if node.state == NodeType.CLUSTER_HEAD:
            nodeList = [t for t in node.broadcastList if t[0] in node.formerIRList] if node.formerIRList else node.broadcastList
        else:
            nodeList = node.neighbourList
        
        # assuming BS is [0, 0]
        for ch in nodeList:
            newNode = graph.nodes[ch]["node"]
            newParentDist = math.sqrt((newNode.coords[0]-0)**2 + (newNode.coords[1] -0)**2)
            oldParentDist = None if node.parent == None else math.sqrt((node.oarent.coords[0]-0)**2 + (node.parent.coords[1]-0)**2)
            if newParentDist < oldParentDist or oldParentDist == None:
                node.parent = newNode
                node.broadcast(message = {
                    "type": "MEMBERJOIN",
                    "id": node.id,
                    "state": node.state,
                    "coords": node.coords
                })
    

# G = nx.Graph()
# node1 = Node(0, power=100, coords=[10,20])
# node2 = Node(1, power=100, coords=[15,25])
# node3 = Node(2, power=100, coords=[50,50])
# node4 = Node(3, power=100, coords=[18,23])

# G.add_node(node1)
# G.add_node(node2)
# G.add_node(node3)
# G.add_node(node4)

# # initialSelection(G)

# for node in G:
#     print(node.state)
# # createClusters(G)



