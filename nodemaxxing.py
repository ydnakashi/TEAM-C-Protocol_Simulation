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

            if dist <= Rc:
                node.neighbourList.append((other, dist))
            # only nodes that are within the multipled distance but outside of Rc are added
            elif dist <= (3/2) * Rc:
                node.broadcastList.append((other, dist))
                

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
    createClusters(graph)

def createClusters(graph):
    print("starting clusters")
    
    sortedNodes = sorted(graph.nodes(), key=lambda n: graph.nodes[n]["node"].twait)
    bsCoords = []
    # no broadcast received - send out a CH message
    for n in sortedNodes:
        node = graph.nodes[n]["node"]
        if(node.state == "BASE_STATION"): 
            print("bs")
            bsCoords = node.coords
            print(bsCoords)
            continue
        if(node.parent == None):
            node.broadcast(message={
                "type": "BROADCAST",
                "sender": node.id,
                "state": NodeType.CLUSTER_HEAD})
        # already has a CH parent, making it a SubCH
        elif (node.parent.state != None):
            node.broadcast(message={
                "type": "BROADCAST",
                "state": NodeType.SUBCLUSTER_HEAD})
     
    for n in sortedNodes:
        node = graph.nodes[n]["node"]
        # if it is still an IR at the end, make it a CH
        if node.state == NodeType.IRRESOLUTE:
            node.state = NodeType.CLUSTER_HEAD
        # make it a CH if it still has no parent
        elif node.state == None: 
            node.state = NodeType.CLUSTER_HEAD

    
        # find nearest CH to the BS to get CH to CH routing

        if node.state == NodeType.CLUSTER_HEAD:
            # assuming BS is [0, 0]

            bsDist = math.sqrt((node.coords[0]-0)**2 + (node.coords[1] -0)**2)
            node.broadcast(message={
                "type": "CHROUTE",
                "distance" : bsDist})

        if node.parent != None:
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



