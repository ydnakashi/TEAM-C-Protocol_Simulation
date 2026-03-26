import math
import networkx as nx
from node import Node, Child, NodeType


# beginning clustering algorithm, to be run at the very start 

# pass in the networksx graph, the max distance of a what a node can hear (default is 20 for now, idk) and the constant used for twait (idk what the default should be)
def twaitCalculation(graph, Rc=2, alpha=0.5):
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

            # if dist <= (3/2) * Rc:
            #     node.neighbourList[other.id] = other
            #     node.neighbourListOrder.append(other.id)

            if dist <= Rc:
                node.neighbourList.append((other, dist))
            # only nodes that are within the multipled distance but outside of Rc are added
            elif dist <= (3/2) * Rc:
                node.broadcastList.append((other, dist))
            elif dist <= 3 * Rc:
                node.relayList.append((other, dist))
                

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

def stateSelection(graph):    
    sortedNodes = sorted(graph.nodes(), key=lambda n: graph.nodes[n]["node"].twait)
    # State setting based on twait
    for n in sortedNodes:
        node = graph.nodes[n]["node"]
        if node.coords == (0, 0):
            node.state = NodeType.BASE_STATION
        elif node.state == None or node.state == NodeType.IRRESOLUTE:
            node.state = NodeType.CLUSTER_HEAD
            node.broadcast(message={
                "type": "STATE",
                "sender": node.id,
                "state": NodeType.CLUSTER_HEAD
                })
        elif node.state == NodeType.IRRESOLUTE:
            node.state = NodeType.CLUSTER_HEAD
            node.broadcast(message={
                "type": "STATE",
                "sender": node.id,
                "state": NodeType.IRRESOLUTE
                })

def clusterCreation(graph, baseStationId):
    print("starting clusters")
    sortedNodes = sorted(graph.nodes(), key=lambda n: graph.nodes[n]["node"].twait)
    bsNode = graph.nodes[baseStationId]['node']

    # parent selection
    for n in sortedNodes:
        node = graph.nodes[n]["node"]
        if node.state == NodeType.BASE_STATION:
            continue

        # get list of possible parent nodes
        if node.state == NodeType.CLUSTER_HEAD:
            node.parent.node = bsNode
            nodeList = [t[0] for t in node.relayList + node.broadcastList if t[0].state == NodeType.CLUSTER_HEAD]
            if nodeList:
                # assuming BS is [0, 0], get list of nodes to distance to base station
                distanceList = [(no, math.sqrt((no.coords[0]-0)**2 + (no.coords[1]-0)**2)) for no in nodeList]
                
                # get their own distance to base station
                BSdist = math.sqrt((node.coords[0]-0)**2 + (node.coords[1]-0)**2)

                # get neighbour node closest to base station
                minNode, minDist = min(distanceList, key=lambda t: t[1])
                
                if minDist < BSdist:
                    node.parent.node = minNode
        else:
            nodeList = node.neighbourList
            node.parent.node = min(nodeList, key=lambda t:t[1])[0]
        
        node.broadcast(message = {
                    "type": "MEMBERJOIN",
                    "id": node.id,
                    "state": node.state,
                })
