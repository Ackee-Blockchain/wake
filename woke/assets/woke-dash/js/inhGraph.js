window.myInhGraph = $$(go.Diagram, "myInhDiv", {
  layout: new go.CircularLayout({
    sorting: go.CircularLayout.Ascending,
  }),
});

// window.myInhGraph.linkTemplate =
// window.myInhGraph.nodeTemplate =

myInhGraph.model = new go.GraphLinksModel(contracts, links.contract_inheritance);
