function select_next_node(node) {
    if (!node.isTreeLeaf && node.isTreeExpanded) {
        node.findTreeChildrenNodes().first().isSelected = true;
    } else {
        let parent = node.findTreeParentNode();
        let found = false;
        while (!found) {
            const arr = iterator_to_array(parent.findTreeChildrenNodes())
            for (let i = 0; i < arr.length - 1; i++) {
                if (arr[i].key === node.key) {
                    arr[i + 1].isSelected = true;
                    e.diagram.commandHandler.scrollToPart(arr[i + 1])
                    found = true;
                    break
                }
            }
            node = parent
            parent = parent.findTreeParentNode();

        }
    }

}


// Region keyboard shortcuts
myDeclGraph.commandHandler.doKeyDown = function() {
    const e = this.diagram.lastInput;
    console.debug('doKeyDown event', e.key)

    // selectedNodes is a set: https://gojs.net/latest/api/symbols/Set.html
    const selectedNodes = myDeclGraph.selection.toArray()
    const firstSelNode = selectedNodes[0]
    selectedNodes.forEach(function(node) {
        node.isSelected = false;
    })

    // myDeclGraph.selection.first().isSelected = true;

    if (e.event.key === 'Control' || e.event.key === 'Alt' || e.event.key === 'Meta' || e.event.key === 'Shift') {
        console.debug('doKeyDown modifier', e.event.key)
        firstSelNode.isSelected = true;
    }

    // First, handle j, k
    if (e.key === 'K' || e.key === 'Up') {
        select_previous_node(firstSelNode)
    }

    if (e.key === 'J' || e.key === 'Down') {
        select_next_node(firstSelNode)
        return;
    }

}

