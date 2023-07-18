function get_node_text(node) {
    if (node.node_type === "contract") {
        return node.name;
    }
    else if (node.node_type === "function") {
        return node.name_with_params;
    }
    else {
        console.warning("Unknown node with key " + node.key)
        return node.key;
    }
}

window.myRefGraph = new go.Diagram("myRefDiv", {
    maxSelectionCount: 1,
    SubGraphCollapsed: function(e) {
        console.debug('SubGraphCollapsed', e.subject.key)
        window.myDeclGraph.findNodeForKey(e.subject.first().key).collapseTree();
    },
    SubGraphExpanded: function(e) {
        console.debug('SubGraphExpanded', e.subject.key)
        window.myDeclGraph.findNodeForKey(e.subject.first().key).expandTree();
    },
    "undoManager.isEnabled": true,
    layout: new go.CircularLayout({
        sorting: go.CircularLayout.Ascending,
    }),
});

myRefGraph.nodeTemplate =
    new go.Node("Auto")  // the Shape will go around the TextBlock
        .add(new go.TextBlock({ font: '13pt sans-serif', margin: 8 }) // Specify a margin to add some room around the text
            .bind("text", "", get_node_text)
            .bind("background", "background")
        )
        .bind("visible", "visible")

// Set the Diagram's link template
myRefGraph.linkTemplate =
    $$(go.Link,  // This creates a Link
        $$(go.Shape,  // This creates a Shape for the Link
            { stroke: "lightgrey", strokeWidth: 1 }),  // Set the Shape's stroke color to grey and stroke width to 2
        $$(go.Shape,  // the arrowhead
            { toArrow: "Standard", stroke: "grey" })
    );


myRefGraph.groupTemplate = $$(go.Group, "Auto", {
    layout: $$(go.CircularLayout, {
        "sorting": go.CircularLayout.Ascending,
    }),
    isSubGraphExpanded: false,
},
    $$(go.Shape, "RoundedRectangle", // surrounds everything
        { parameter1: 10, fill: "rgba(128,128,128,0.33)" }),
    $$(go.Panel, "Vertical",  // position header above the subgraph
        { defaultAlignment: go.Spot.Left },
        $$(go.Panel, "Horizontal",  // the header
            { defaultAlignment: go.Spot.Top },
            $$("SubGraphExpanderButton"),  // this Panel acts as a Button
            $$(go.TextBlock,     // group title near top, next to button
                { font: "Bold 12pt Sans-Serif" },
                new go.Binding("text", "", get_node_text)),
        ),
        $$(go.Placeholder,     // represents area for all member parts
            { padding: new go.Margin(0, 10), background: "white" })
    ),
    new go.Binding("visible", "checked")
);

const ref_graph_nodes = contracts.concat(functions)
// const ref_graph_links = links.function_references.slice(0,90).concat([{
//         from: "/Users/dteiml/p/hacker-dom/single-collateral-dai/auth.sol/DSAuth.constructor()",
//         to: "/Users/dteiml/p/hacker-dom/single-collateral-dai/auth.sol/DSAuthority.canCall(address,address,bytes4)"
// }])
const ref_graph_links = links.function_references
myRefGraph.model = new go.GraphLinksModel(
    // functions.slice(0,10),
    ref_graph_nodes,
    ref_graph_links,
    {
        nodeGroupKeyProperty: "parent"
    }
)
console.log(ref_graph_links.length)
console.log(functions.slice(0,10))
console.log(ref_graph_links)
// myRefGraph.model = new go.GraphLinksModel(
//     [
//         { key: "foo" },
//         { key: "bar" },
//     ],
//     [
//         { from: "foo", to: "bar" }
//     ]
// )
