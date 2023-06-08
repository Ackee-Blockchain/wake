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

myRefGraph.nodeTemplate =
    new go.Node("Auto")  // the Shape will go around the TextBlock
        .add(new go.TextBlock({ font: '13pt sans-serif', margin: 8 }) // Specify a margin to add some room around the text
            .bind("text", "", get_node_text)
            .bind("background", "background")
        )
        .bind("visible", "visible")

// Set the Diagram's link template
myCallGraph.linkTemplate =
    $$(go.Link,  // This creates a Link
        $$(go.Shape,  // This creates a Shape for the Link
            { stroke: "lightgrey", strokeWidth: 1 }),  // Set the Shape's stroke color to grey and stroke width to 2
        $$(go.Shape,  // the arrowhead
            { toArrow: "Standard", stroke: "grey" })
    );

