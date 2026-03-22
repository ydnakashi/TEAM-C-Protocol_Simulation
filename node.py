from dataclasses import dataclass

@dataclass
class Child:
    """A node that sends packets to its parent. Seen from the view of the parent."""
    tdma_slot: int = -1    # -1 means no slot given
    received: bool = False
    overall_score: float = 0

class Node:
    def __init__(self, id, power=100, coords=[0,0]):
        self.id = id
        self.state = None
        self.power = power
        self.coords = coords
        self.worthiness = 100
        self.timeSlot = 0

        self.chdList = {}
        self.neighbourList = []
        # twait is effected by neighbours within the RC, but broadcast messages can reach 3/2 x RC 
        self.broadcastList = []
        self.parent = None
        self.parentScore = None

        self.twait = 0

        self.label=f"Node {self.id}"
      
        self.sent = False
        self.p_rcvd = False
        self.timer = 0
        self.tdmaSlot = -1  # Default to -1 to represent no slot
        self.totalSlots = -1  # Default to -1 to represent no slot
        self.waiting = 0

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
