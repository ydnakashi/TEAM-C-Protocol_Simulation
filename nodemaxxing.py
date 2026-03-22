import math
import networkx as nx

class Node:
    def __init__(self, id, power=100, coords=None):
        self.id = id
        self.state = None
        self.power = power
        self.coords = coords if coords is not None else [0, 0]
        self.worthiness = 100
        self.timeSlot = 0

        self.childList = []
        self.neighbourList = []
        # twait is effected by neighbours within the RC, but broadcast messages can reach 3/2 x RC 
        self.broadcastList = []
        self.parent = None
        self.parentScore = None

        self.twait = 0

    def broadcast (self, message):
        # print(f"Node {self.id} received:", message)

        # get all nodes within the Rc distance
        if(message['type'] == "BROADCAST"):
            for neighbour, dist in self.neighbourList:
                neighbour.receive(self, message, 0)

            for neighbour, dist in self.broadcastList:
                neighbour.receive(self, message, 1)
        if(message['type'] == "MEMBERJOIN"):
            self.parent.receive(self, message, -1)

    def receive(self, sender, message, neighbourType):
        # direct neighbour
        if message["type"] == "BROADCAST" and neighbourType == 0:
            self.parent = sender
            # makes it a SubCH
            if message['state'] == 1:
                self.state = 2
            else:
                # ordinary node
                self.state = 3
        
         # in broadcast range, no parent
        if message["type"] == "BROADCAST" and neighbourType == 1 and self.state == None:
            # IR state
            self.parent = sender
            self.state = 4

        if message["type"] == "MEMBERJOIN":
            self.childList.append([message['id'], message['state'], message['coords']])

        
    def addNeighbour(self, node):
        self.neighbourList.append(node)

    def neighbourCount(self):
        return len(self.neighbourList)

    # icd used to calcualte twait time
    # euclidan distance of all the nodes in its neighbour array
    def calculateICD(self, distance_matrix):
        if not self.neighbourList:
            return 0

        total = 0
        for neighbour in self.neighbourList:
            total += distance_matrix[self.id][neighbour.id]

        return total / len(self.neighbourList)
    
    def calculateWorthiness(self):
        print('test')



# beginning clustering algorithm, to be run at the very start 

# pass in the networksx graph, the max distance of a what a node can hear (default is 20 for now, idk) and the constant used for twait (idk what the default should be)
def initialSelection(graph, Rc=20, alpha=0.5):
    print("stat")
    # the total amount of nodes in the graph
    N = graph.number_of_nodes()
    # dimensions of the graph, currently hardcoded for now ...
    x, y = 100, 100

    for ni in graph.nodes():      
        node = ni["node"]
        x1, y1 = node.coords
    
        for other in graph.nodes:
            # check that the node is not itself
            if node == other:
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
    for node in graph.nodes:
        NNi = len(node.neighbourList)

        if NNi == 0:
            node.twait = 1000
            continue

        # icd compute
        total_dist = sum(dist for (_, dist) in node.neighbourList)
        ICDi = total_dist / NNi
        print("ICDI: " ,ICDi)

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
    sortedNodes = sorted(graph.nodes(), key=lambda n: n.twait)

    # no broadcast received - send out a CH message
    for node in sortedNodes:
        if(node.parent == None):
            node.broadcast(message={
                "type": "BROADCAST",
                "sender": node.id,
                "state": 1})
        # already has a CH parent, making it a SubCH
        elif (node.parent.state != None):
            node.broadcast(message={
                "type": "BROADCAST",
                "state": 2})
     
    for node in sortedNodes:
        # if it is still an IR at the end, make it a CH
        if node.state == 4:
            node.state = 1
        # make it a CH if it still has no parent
        elif node.state == None: 
            node.state = 1

        if node.parent != None:
            node.broadcast(message = {
                "type": "MEMBERJOIN",
                "id": node.id,
                "state": node.state,
                "coords": node.coords
            })
        

G = nx.Graph()
node1 = Node(0, power=100, coords=[10,20])
node2 = Node(1, power=100, coords=[15,25])
node3 = Node(2, power=100, coords=[50,50])
node4 = Node(3, power=100, coords=[18,23])

G.add_node(node1)
G.add_node(node2)
G.add_node(node3)
G.add_node(node4)

initialSelection(G)

for node in G:
    print(node.state)
# createClusters(G)



