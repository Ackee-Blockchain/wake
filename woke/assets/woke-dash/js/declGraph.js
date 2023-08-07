// A lot of the code here is inspired by https://gojs.net/latest/samples/triStateCheckBoxTree.html

// Region helpers

// This button assumes data binding to the "checked" property.
go.GraphObject.defineBuilder("TriStateCheckBoxButton", args => {
    var button = /** @type {Panel} */ (
        go.GraphObject.make("Button",
            {
                "ButtonBorder.fill": "white",
                width: 14,
                height: 14,
                margin: new go.Margin(0, 5),
            },
            go.GraphObject.make(go.Shape,
                {
                    name: "ButtonIcon",
                    geometryString: 'M0 0 M0 8.85 L4.9 13.75 16.2 2.45 M16.2 16.2',  // a 'check' mark
                    strokeWidth: 2,
                    stretch: go.GraphObject.Fill,  // this Shape expands to fill the Button
                    geometryStretch: go.GraphObject.Uniform,  // the check mark fills the Shape without distortion
                    background: null,
                    visible: false  // visible set to false: not checked, unless data.checked is true
                },
                new go.Binding("visible", "checked", p => p === true || p === null),
                new go.Binding("stroke", "checked", p => p === null ? null : "black"),
                new go.Binding("background", "checked", p => p === null ? "gray" : null)
            )
        )
    );
    button.click = (e, button) => {
        if (!button.isEnabledObject()) return;
        var diagram = e.diagram;
        if (diagram === null || diagram.isReadOnly) return;
        if (diagram.model.isReadOnly) return;
        e.handled = true;
        var shape = button.findObject("ButtonIcon");
        diagram.startTransaction("checkbox");
        // Assume the name of the data property is "checked".
        var node = button.part;
        var oldval = node.data.checked;
        var newval = (oldval !== true);  // newval will always be either true or false, never null
        // Set this data.checked property and those of all its children to the same value
        updateCheckBoxesDown(node, newval);
        // Walk up the tree and update all of their checkboxes
        updateCheckBoxesUp(node, newval);
        // support extra side-effects without clobbering the click event handler:
        if (typeof button["_doClick"] === "function") button["_doClick"](e, button);
        // Update all target bindings, in case data.checked has changed
        window.mainGraph.updateAllTargetBindings("checked")
        diagram.commitTransaction("checkbox");
    };
    return button;

});

function updateCheckBoxesDown(node, newval) {
    // This function doesn't create a transaction
    node.diagram.model.setDataProperty(node.data, "checked", newval);

    node.findTreeChildrenNodes().each(child => updateCheckBoxesDown(child, newval))
}

function updateCheckBoxesUp(node, newval) {
    // This function doesn't create a transaction
    var parent = node.findTreeParentNode();
    if (parent !== null) {
        var anychecked = parent.findTreeChildrenNodes().any(n => n.data.checked !== false && n.data.checked !== undefined);
        var allchecked = parent.findTreeChildrenNodes().all(n => n.data.checked === true);
        node.diagram.model.setDataProperty(parent.data, "checked", (allchecked ? true : (anychecked ? null : false)));

        updateCheckBoxesUp(parent, newval);
    }
}

// Region diagram
window.myDeclGraph = $$(go.Diagram, "myDeclDiv", {
    allowMove: false,
    allowCopy: false,
    allowDelete: false,
    allowHorizontalScroll: false,
    layout:
        $$(go.TreeLayout,
            {
                alignment: go.TreeLayout.AlignmentStart,
                angle: 0,
                compaction: go.TreeLayout.CompactionNone,
                layerSpacing: 16,
                layerSpacingParentOverlap: 1,
                nodeIndentPastParent: 1.0,
                nodeSpacing: 0,
                setsPortSpot: false,
                setsChildPortSpot: false
            }),
    maxSelectionCount: 1,
    TreeCollapsed: function(e) {
        // Called within a transaction
        console.debug('TreeCollapsed', e.subject.key)
        const sister_node = window.mainGraph.findNodeForKey(e.subject.first().key);
        if (sister_node) {
            sister_node.collapseSubGraph();
        }
    },
    TreeExpanded: function(e) {
        // Called within a transaction
        console.debug('TreeExpanded', e.subject.key)
        const sister_node = window.mainGraph.findNodeForKey(e.subject.first().key);
        if (sister_node) {
            sister_node.expandSubGraph();
        }
    },

})

myDeclGraph.nodeTemplate =
    $$(go.Node,
        { // no Adornment: instead change panel background color by binding to Node.isSelected
            selectionAdorned: false,
            // a custom function to allow expanding/collapsing on double-click
            // this uses similar logic to a TreeExpanderButton
            doubleClick: (e, node) => {
                var cmd = myDiagram.commandHandler;
                if (node.isTreeExpanded) {
                    if (!cmd.canCollapseTree(node)) return;
                } else {
                    if (!cmd.canExpandTree(node)) return;
                }
                e.handled = true;
                if (node.isTreeExpanded) {
                    cmd.collapseTree(node);
                } else {
                    cmd.expandTree(node);
                }
            }
        },
        $$(
            "TreeExpanderButton",
            { // customize the button's appearance
                "_treeExpandedFigure": "LineDown",
                "_treeCollapsedFigure": "LineRight",
                "ButtonBorder.fill": "whitesmoke",
                "ButtonBorder.stroke": null,
                "_buttonFillOver": "rgba(0,128,255,0.25)",
                "_buttonStrokeOver": null
            }
        ),
        $$(
            go.Panel,
            "Horizontal",
            { position: new go.Point(18, 0) },
            new go.Binding("background", "isSelected", s => s ? "lightblue" : "white").ofObject(),

            $$("TriStateCheckBoxButton"),

            $$(go.TextBlock,
                // { font: '9pt Verdana, sans-serif', background: 'blue' },
                { font: '9pt Verdana, sans-serif', },
                new go.Binding("text", "", get_node_text),
                new go.Binding("background", "background")
            )
        )  // end Horizontal Panel
    );  // end Node

// Region link template
myDeclGraph.linkTemplate =
    $$(go.Link,
        {
            selectable: false,
            routing: go.Link.Orthogonal,
            fromEndSegmentLength: 4,
            toEndSegmentLength: 4,
            fromSpot: new go.Spot(0.001, 1, 7, 0),
            toSpot: go.Spot.Left
        },
        $$(go.Shape,
            { stroke: 'gray', strokeDashArray: [1, 2] }));


// Region helpers
function collapse_all() {
    myRefGraph.findTopLevelGroups().each(function(g) {
        g.collapseSubGraph();
        const sister_node = myDeclGraph.findNodeForKey(g.key)
        sister_node.collapseTree();
    });
}

function expand_all() {
    myRefGraph.findTopLevelGroups().each(function(g) {
        g.expandSubGraph();
        const sister_node = myDeclGraph.findNodeForKey(g.key)
        sister_node.expandTree();
    });
}

function get_node_text(node) {
    if (node.node_type === "contract") {
        return node.name;
    }
    else if (node.node_type === "function") {
        return node.name_with_params;
    }
    else if (node.node_type === "folder") {
        return node.name;
    }
    else if (node.node_type === "file") {
        return node.name;
    }
    else {
        console.warning("Unknown node with key " + node.key)
        return node.key;
    }
}

// Region model
const decl_graph_nodes = folders.concat(files).concat(contracts).concat(functions)
window.myDeclGraph.model = new go.TreeModel(decl_graph_nodes)

