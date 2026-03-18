import math
import networkx as nx

class Node:
    def __init__(self, id, power=100):
        self.id = id
        self.power = power
        self.worthiness = 100
        self.timeSlot = 0

        self.childList = []
        self.neighbourList = []
        self.parent = None
        self.parentScore = None

        self.twait = 0

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

    for node in graph.nodes:
        neighbours = []
        x1 = graph.nodes[node]["x"]
        y1 = graph.nodes[node]["y"]

        for other in graph.nodes:
            # check that the node is not itself
            if node == other:
                continue

            x2 = graph.nodes[other]["x"]
            y2 = graph.nodes[other]["y"]

            # euclidean distance
            dist = math.sqrt((x1-x2)**2 + (y1-y2)**2)
            print("distance: ", dist)

            if dist <= Rc:
                neighbours.append((other, dist))

        graph.nodes[node]["neighbours"] = neighbours

    total = sum(len(graph.nodes[n]["neighbours"]) for n in graph.nodes)
    average = total / N
    print("average: ", average)

    # twait
    for node in graph.nodes:
        neighbours = graph.nodes[node]["neighbours"]
        NNi = len(neighbours)

        if NNi == 0:
            graph.nodes[node]["twait"] = float("inf")
            continue

        # icd compute
        total_dist = sum(dist for (_, dist) in neighbours)
        ICDi = total_dist / NNi
        print("ICDI: " ,ICDi)

        if NNi > average:
            twait = alpha * (ICDi / Rc) + (1 - alpha) * \
                (1 - (NNi / N)) * (1 - ((NNi - average) / N))
        else:
            twait = alpha * (ICDi / Rc) + (1 - alpha) * \
                (1 - (NNi / N))
        graph.nodes[node]["twait"] = twait

def routing(node):
    print("starting routing")
    # unsure how our live routing is going to work ...
    # using real time? wouldnt that use a lot of computing power?
    # ie during our loop, EVERY node has to check if its their time slot, transport, calculate trust score
    # and will time slots just be 'each iteration of a loop will be the new time slot?'

    # send packet to parent 
    # wait for ack 
    # if ack received:
    #     increase parents trust score
    # else:
    #     decrease parents trust score


G = nx.Graph()
G.add_node(0, x=10, y=20)
G.add_node(1, x=15, y=25)
G.add_node(2, x=100, y=100)
G.add_node(3, x=18, y=23)

initialSelection(G)

for n in G.nodes:
    print(
        "Node:", n,
        "Neighbours:", [x[0] for x in G.nodes[n]["neighbours"]],
        "Twait:", G.nodes[n]["twait"]
    )