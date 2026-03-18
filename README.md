# TEAM-C-Protocol_Simulation
COMP4203 Winter 2026 Group Project

Simulating a novel protocol, TEAM-C, in wireless sensor networks

# Requirements
- GUI
    - Pages
        1. Graph map setup
        2. Graph simulator with metric 
- Model
    - TEAM-C Protocol implementation
        - Actions in a time period 
        - Make the code run in rounds
        - Node classes (ordinary node, subcluster head, cluster heads) (Yuki)
            - Energy 
            - worthiness score (of itself, children, parent)
            - random destruction factor
            - packets per time period
            - coordinates
        - Base station (Yuki)
            - assume it never dies
            - coordinates
            - total packets delivered
        - manual destruction factor
        - initial cluster selection (amy)
            - parent and child fields
        - routing to parent (amy)
            - slotted TDMA
            - aggregation
            - worthiness calculation
        - CH updating (Isabella)
            - worthiness score is less than thresold
            - find new CH if old CH or S_CH died
            - CH initiates re-election 
                - update every child
                - new head updates its child list
                - new head creates TDMA timeslots
    - Metric tracking implementation
        - network lifetime
        - average throughput
        - end-to-end delay
        - total packets delivered
        - export CSV
    - 