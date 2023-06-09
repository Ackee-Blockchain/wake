// Region keyboard shortcuts
myDeclGraph.commandHandler.doKeyDown = function() {
    const e = this.diagram.lastInput;
    console.debug('doKeyDown event', e.key)
    const firstSelNode = myDeclGraph.selection.first();

    // myDeclGraph.selection.first().isSelected = true;

    if (e.event.key === 'Control' || e.event.key === 'Alt' || e.event.key === 'Meta' || e.event.key === 'Shift') {
        firstSelNode.isSelected = true;
    }

    // if (e.)
}
 
